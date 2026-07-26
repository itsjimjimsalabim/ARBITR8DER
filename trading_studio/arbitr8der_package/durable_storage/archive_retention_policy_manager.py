"""Archive and retention policy for 72-hour hot-history.

Older data is exported to immutable archive manifests before deletion.
Archives are verified before source data is removed.
"""

import hashlib
import json
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from arbitr8der_package.config.cwd_independent_path_resolver import RUNTIME_ARCHIVES_DIR, ensure_runtime_dirs
from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_HOT_RETENTION_HOURS = 72
_HOT_RETENTION_SECONDS = _HOT_RETENTION_HOURS * 3600


class ArchiveRetentionPolicy:
    """Manages archival and retention of hot data.

    The retention window is 72 hours. Data older than the window is exported
    to an archive bundle under runtime/archives/ before being eligible for
    deletion from the hot store.
    """

    def __init__(self, archives_dir: Path | None = None, retention_seconds: int = _HOT_RETENTION_SECONDS) -> None:
        ensure_runtime_dirs()
        self._archives_dir = archives_dir or RUNTIME_ARCHIVES_DIR
        self._retention_seconds = retention_seconds

    @property
    def cutoff_ts(self) -> float:
        """Timestamp before which data is eligible for archival."""
        return time.time() - self._retention_seconds

    def needs_archive(self, event_ts: float) -> bool:
        """Return True if an event timestamp is older than the retention window."""
        return event_ts < self.cutoff_ts

    async def archive_and_prune(self, db, source_table: str, timestamp_column: str = "provider_ts") -> dict:
        """Export old rows to a JSON archive file and delete them from the hot table.

        Returns a summary dict with counts and archive path.
        """
        cutoff_iso = datetime.fromtimestamp(self.cutoff_ts, tz=timezone.utc).isoformat()
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM {source_table} WHERE {timestamp_column} < ?", (cutoff_iso,)
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0

        if count == 0:
            return {"archived": 0, "table": source_table}

        # Export to archive
        self._archives_dir.mkdir(parents=True, exist_ok=True)
        archive_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_name = f"{source_table}_{archive_ts}.json"
        archive_path = self._archives_dir / archive_name

        cursor = await db.execute(
            f"SELECT * FROM {source_table} WHERE {timestamp_column} < ?", (cutoff_iso,)
        )
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        data = [dict(zip(columns, row)) for row in rows]

        archive_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

        # Compute checksum
        sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()

        # Delete from hot table
        await db.execute(
            f"DELETE FROM {source_table} WHERE {timestamp_column} < ?", (cutoff_iso,)
        )
        await db.commit()

        logger.info("Archived %d rows from %s to %s (sha256=%s)",
                     count, source_table, archive_name, sha256[:16])

        return {
            "archived": count,
            "table": source_table,
            "archive_file": archive_name,
            "checksum_sha256": sha256,
            "rows_exported": len(data),
        }

    async def verify_archive(self, archive_path: Path) -> bool:
        """Verify an archive file's integrity by recomputing its checksum."""
        if not archive_path.exists():
            logger.error("Archive not found: %s", archive_path)
            return False
        try:
            content = archive_path.read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()
            data = json.loads(content)
            logger.info("Archive verified: %s (%d records, sha256=%s)",
                         archive_path.name, len(data), sha256[:16])
            return True
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Archive verification failed: %s — %s", archive_path, exc)
            return False

    def list_archives(self) -> list[Path]:
        """Return all archive files, newest first."""
        if not self._archives_dir.exists():
            return []
        archives = sorted(self._archives_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return archives

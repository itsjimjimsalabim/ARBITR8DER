import json
import os
import time
from pathlib import Path
from typing import TextIO

from kalshi_desk_package.config.cwd_independent_path_resolver import LEASE_FILE_PATH
from kalshi_desk_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None
    import msvcrt

_LEASE_TTL_SECONDS = 5 * 60  # 5 minutes


def _lock_exclusive_nonblocking(f: TextIO) -> bool:
    fd = f.fileno()
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except IOError:
            return False
    # Windows: msvcrt locks relative to the current file pointer and requires
    # the locked byte range to exist. Ensure a byte exists and seek to 0.
    if os.fstat(fd).st_size == 0:
        f.write("\n")
        f.flush()
    f.seek(0)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _unlock(f: TextIO) -> None:
    fd = f.fileno()
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    try:
        f.seek(0)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


class RuntimeLease:
    """File-backed lease ensuring only one process owns a stream at a time.

    Uses atomic POSIX file locking (fcntl) to safely read-modify-write lease state.
    """

    def __init__(self, lease_file: Path | None = None, ttl: int = _LEASE_TTL_SECONDS) -> None:
        self._lease_file = lease_file or LEASE_FILE_PATH
        self._ttl = ttl

    def acquire(self, owner_id: str) -> bool:
        """Try to acquire the lease atomically. Returns True if acquired, False if held by another active owner."""
        self._lease_file.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        
        with open(self._lease_file, "a+") as f:
            if not _lock_exclusive_nonblocking(f):
                logger.warning("Lease file locked by another process — cannot acquire for %s", owner_id)
                return False
                
            try:
                f.seek(0)
                content = f.read()
                try:
                    existing = json.loads(content) if content.strip() else None
                except json.JSONDecodeError:
                    existing = None
                
                if existing and existing.get("expires_at", 0) > now:
                    if existing.get("owner") != owner_id:
                        logger.warning("Lease held by %s until %.0f — cannot acquire for %s",
                                       existing.get("owner"), existing.get("expires_at"), owner_id)
                        return False
                    logger.info("Lease refreshed by %s", owner_id)
                else:
                    logger.info("Lease acquired by %s (expires in %ds)", owner_id, self._ttl)

                data = {"owner": owner_id, "acquired_at": now, "expires_at": now + self._ttl}
                f.seek(0)
                f.truncate()
                f.write(json.dumps(data, indent=2))
                f.flush()
                return True
            finally:
                _unlock(f)

    def release(self, owner_id: str) -> bool:
        """Release the lease atomically."""
        if not self._lease_file.exists():
            return False
        with open(self._lease_file, "a+") as f:
            if not _lock_exclusive_nonblocking(f):
                return False
            try:
                f.seek(0)
                content = f.read()
                existing = json.loads(content) if content.strip() else None
                if not existing or existing.get("owner") != owner_id:
                    return False
                f.seek(0)
                f.truncate()
                f.write("{}")
                f.flush()
                logger.info("Lease released by %s", owner_id)
                return True
            finally:
                _unlock(f)

    def current_owner(self) -> str | None:
        """Return the current lease owner, or None if expired/absent."""
        if not self._lease_file.exists():
            return None
        try:
            content = self._lease_file.read_text(encoding="utf-8")
            existing = json.loads(content) if content.strip() else None
            if not existing or existing.get("expires_at", 0) <= time.time():
                return None
            return existing.get("owner")
        except (json.JSONDecodeError, KeyError):
            return None

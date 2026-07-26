"""Runtime lease for single-process stream ownership.

Prevents two instances from claiming the same data stream simultaneously.
Uses a file-based lock with a timeout so stale leases auto-expire.
"""

import json
import time
from pathlib import Path

from arbitr8der_package.config.cwd_independent_path_resolver import LEASE_FILE_PATH
from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_LEASE_TTL_SECONDS = 5 * 60  # 5 minutes


class RuntimeLease:
    """File-backed lease ensuring only one process owns a stream at a time.

    The lease file stores a JSON blob with an owner ID and an expiry timestamp.
    If the lease is expired or absent, any caller may acquire it.
    """

    def __init__(self, lease_file: Path | None = None, ttl: int = _LEASE_TTL_SECONDS) -> None:
        self._lease_file = lease_file or LEASE_FILE_PATH
        self._ttl = ttl

    def acquire(self, owner_id: str) -> bool:
        """Try to acquire the lease. Returns True if acquired, False if held by another active owner."""
        now = time.time()
        existing = self._read()
        if existing and existing["expires_at"] > now:
            if existing["owner"] != owner_id:
                logger.warning("Lease held by %s until %.0f — cannot acquire for %s",
                               existing["owner"], existing["expires_at"], owner_id)
                return False
            # Same owner re-acquiring — refresh
            logger.info("Lease refreshed by %s", owner_id)
        else:
            logger.info("Lease acquired by %s (expires in %ds)", owner_id, self._ttl)

        self._write({"owner": owner_id, "acquired_at": now, "expires_at": now + self._ttl})
        return True

    def release(self, owner_id: str) -> bool:
        """Release the lease. Returns True if released, False if not the current owner."""
        existing = self._read()
        if not existing or existing["owner"] != owner_id:
            return False
        self._lease_file.unlink(missing_ok=True)
        logger.info("Lease released by %s", owner_id)
        return True

    def current_owner(self) -> str | None:
        """Return the current lease owner, or None if expired/absent."""
        existing = self._read()
        if not existing or existing["expires_at"] <= time.time():
            return None
        return existing["owner"]

    def _read(self) -> dict | None:
        if not self._lease_file.exists():
            return None
        try:
            return json.loads(self._lease_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None

    def _write(self, data: dict) -> None:
        self._lease_file.parent.mkdir(parents=True, exist_ok=True)
        self._lease_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

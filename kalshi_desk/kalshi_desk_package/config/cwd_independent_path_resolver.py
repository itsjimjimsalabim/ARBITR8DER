"""CWD-independent path resolution for kalshi_desk runtime directories.

All runtime paths resolve relative to the package location, not the caller's
current working directory. This prevents accidental writes to the wrong location
when launching the studio from the repo root, from `kalshi_desk/`, or from
pytest running out of `tests/`.
"""

from pathlib import Path

# kalshi_desk/ is the package root (parent of kalshi_desk_package/)
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent

RUNTIME_DIR = _PACKAGE_ROOT / "runtime"
RUNTIME_DATA_DIR = RUNTIME_DIR / "data"
RUNTIME_STATE_DIR = RUNTIME_DIR / "state"
RUNTIME_LOGS_DIR = RUNTIME_DIR / "logs"
RUNTIME_ARCHIVES_DIR = RUNTIME_DIR / "archives"
SQLITE_DB_PATH = RUNTIME_DATA_DIR / "arbitr8der.db"
VESSEL_STATE_PATH = RUNTIME_STATE_DIR / "vessel_state.json"
LEASE_FILE_PATH = RUNTIME_STATE_DIR / "stream_lease.json"

# Streams directory holds credentials like the Kalshi RSA private key.
STREAMS_DIR = _PACKAGE_ROOT / "streams"


def ensure_runtime_dirs() -> None:
    """Create all runtime directories if they do not exist."""
    for directory in [RUNTIME_DIR, RUNTIME_DATA_DIR, RUNTIME_STATE_DIR, RUNTIME_LOGS_DIR, RUNTIME_ARCHIVES_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def get_package_root() -> Path:
    """Return the absolute path to the kalshi_desk/ directory."""
    return _PACKAGE_ROOT


def get_repository_root() -> Path:
    """Return the absolute path to the ARBITR8DER/ directory (parent of kalshi_desk/)."""
    return _PACKAGE_ROOT.parent


def resolve_streams_path(relative_or_absolute: str) -> Path:
    """Resolve a streams path to an absolute Path.

    Relative inputs are resolved against ``kalshi_desk/streams/`` (not CWD).
    Absolute inputs are returned unchanged. If the file does not exist, the
    resolved path is still returned — callers can decide how to react.

    Handles legacy values like ``streams/kalshi_private.pem`` by stripping the
    leading ``streams/`` prefix before resolving against STREAMS_DIR.
    """
    candidate = Path(relative_or_absolute)
    if candidate.is_absolute():
        return candidate
    # Strip leading "streams/" if present (legacy .env values)
    parts = candidate.parts
    if parts and parts[0] == "streams":
        candidate = Path(*parts[1:]) if len(parts) > 1 else Path(".")
    return STREAMS_DIR / candidate

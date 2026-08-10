"""Vessel state machine for ARBITR8DER trading studio.

Manages the lifecycle of the trading vessel:
  Full_Stop  -> Battery -> Full_Forward
  Any state  -> Full_Stop (operator action, error, or startup)

Full_Stop is always the default on startup. No live trading is possible
until the operator explicitly transitions through Battery to Full_Forward.
"""

import json
import time
from enum import StrEnum
from pathlib import Path
from typing import Any

from kalshi_desk_package.config.cwd_independent_path_resolver import VESSEL_STATE_PATH, ensure_runtime_dirs
from kalshi_desk_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_AUTO_STOP_SECONDS = 30 * 60  # 30 minutes of inactivity


class VesselState(StrEnum):
    """Operating states for the trading vessel."""

    FULL_STOP = "full_stop"
    BATTERY = "battery"
    FULL_FORWARD = "full_forward"


# Allowed transitions: source -> set of valid destinations
_VALID_TRANSITIONS: dict[VesselState, set[VesselState]] = {
    VesselState.FULL_STOP: {VesselState.BATTERY},
    VesselState.BATTERY: {VesselState.FULL_FORWARD, VesselState.FULL_STOP},
    VesselState.FULL_FORWARD: {VesselState.FULL_STOP},
}


class IllegalTransitionError(Exception):
    """Raised when a state transition is not permitted."""

    def __init__(self, from_state: VesselState, to_state: VesselState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Illegal transition: {from_state.value} -> {to_state.value}")


class VesselStateMachine:
    """Manages vessel state with persistence and audit trail.

    On every instantiation with read_only=False (default), state is forced
    to Full_Stop and persisted — the safe default for a new session owner.

    Use read_only=True for inspection-only callers (e.g. ``arbitr8der status``)
    that must NEVER overwrite the state of a running session. In read_only mode
    the state file is loaded for display but _persist() is never called.

    Use the classmethod ``read_state_from_disk()`` for the lightest possible
    read — no instantiation side-effects at all.
    """

    def __init__(self, state_file: Path | None = None, read_only: bool = False) -> None:
        ensure_runtime_dirs()
        self._state_file = state_file or VESSEL_STATE_PATH
        self._read_only = read_only
        self._current_state = VesselState.FULL_STOP
        self._last_activity_ts = time.time()
        self._audit_log: list[dict[str, Any]] = []
        if read_only:
            self._load_state_for_display()
        else:
            self._load_and_force_stop()

    @classmethod
    def read_state_from_disk(cls, state_file: Path | None = None) -> dict[str, Any]:
        """Read persisted state from disk with zero side-effects.

        Safe to call from any process at any time — does not instantiate the
        state machine, does not persist anything, does not force Full_Stop.
        Returns a dict with 'vessel_state', 'last_activity_ts', 'audit_log'.
        """
        path = state_file or VESSEL_STATE_PATH
        if not path.exists():
            return {"vessel_state": VesselState.FULL_STOP.value, "last_activity_ts": 0.0, "audit_log": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return {"vessel_state": VesselState.FULL_STOP.value, "last_activity_ts": 0.0, "audit_log": []}

    @property
    def current_state(self) -> VesselState:
        if self._is_timed_out():
            self._force_stop("auto-stop: inactivity timeout")
        return self._current_state

    def transition(self, to_state: VesselState, reason: str = "") -> VesselState:
        """Attempt a state transition. Raises IllegalTransitionError if invalid."""
        current = self.current_state
        valid = _VALID_TRANSITIONS.get(current, set())
        if to_state not in valid:
            raise IllegalTransitionError(current, to_state)

        self._record_transition(current, to_state, reason)
        self._current_state = to_state
        self._last_activity_ts = time.time()
        self._persist()
        logger.info("Vessel transition: %s -> %s (reason: %s)", current.value, to_state.value, reason or "operator")
        return self._current_state

    def get_state(self) -> dict[str, Any]:
        """Return the current state as a dict for CLI/JSON output."""
        return {
            "vessel_state": self.current_state.value,
            "last_activity_ts": self._last_activity_ts,
            "audit_log": self._audit_log[-10:],  # last 10 entries
        }

    def _force_stop(self, reason: str) -> None:
        """Force the vessel to Full_Stop. Called on startup and errors."""
        self._record_transition(self._current_state, VesselState.FULL_STOP, reason)
        self._current_state = VesselState.FULL_STOP
        self._last_activity_ts = time.time()
        if not self._read_only:
            self._persist()
        logger.warning("Vessel forced to Full_Stop: %s", reason)

    def _load_and_force_stop(self) -> None:
        """Load persisted state (for audit trail), then force stop."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                self._audit_log = data.get("audit_log", [])
                previous = data.get("vessel_state", "full_stop")
                logger.info("Loaded previous state: %s (forcing Full_Stop)", previous)
            except (json.JSONDecodeError, KeyError):
                logger.warning("Corrupt vessel state file, starting fresh")
        self._force_stop("startup: forced full stop")

    def _load_state_for_display(self) -> None:
        """Load persisted state for read-only display. Never calls _persist()."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                self._audit_log = data.get("audit_log", [])
                state_str = data.get("vessel_state", VesselState.FULL_STOP.value)
                try:
                    self._current_state = VesselState(state_str)
                except ValueError:
                    self._current_state = VesselState.FULL_STOP
                self._last_activity_ts = data.get("last_activity_ts", time.time())
                logger.info("Read-only load: vessel_state=%s", self._current_state.value)
            except (json.JSONDecodeError, KeyError):
                logger.warning("Corrupt vessel state file, reporting full_stop")

    def _is_timed_out(self) -> bool:
        return (time.time() - self._last_activity_ts) > _AUTO_STOP_SECONDS

    def _record_transition(self, from_state: VesselState, to_state: VesselState, reason: str) -> None:
        self._audit_log.append({
            "from": from_state.value,
            "to": to_state.value,
            "reason": reason or "operator",
            "ts": time.time(),
        })

    def _persist(self) -> None:
        if self._read_only:
            logger.error("BUG: _persist() called on read-only VesselStateMachine — skipping write")
            return
        data = {
            "vessel_state": self._current_state.value,
            "last_activity_ts": self._last_activity_ts,
            "audit_log": self._audit_log,
        }
        self._state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

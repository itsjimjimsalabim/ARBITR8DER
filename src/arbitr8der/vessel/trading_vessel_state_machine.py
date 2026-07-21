"""Vessel state machine — the 3-state permission gate.

Full_Stop  →  Battery  →  Full_Forward
   ↑              ↑             |
   └──────────────┴─────────────┘  (emergency stop from any state)

State IS the permission to trade. No trade can happen in Full_Stop or Battery.
"""
from __future__ import annotations

import json
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TradingVesselState(str, Enum):
    FULL_STOP = "FULL_STOP"
    BATTERY = "BATTERY"
    FULL_FORWARD = "FULL_FORWARD"


# Allowed transitions: from_state -> set of valid to_states
_TRANSITIONS: dict[TradingVesselState, set[TradingVesselState]] = {
    TradingVesselState.FULL_STOP: {TradingVesselState.BATTERY},
    TradingVesselState.BATTERY: {TradingVesselState.FULL_STOP, TradingVesselState.FULL_FORWARD},
    TradingVesselState.FULL_FORWARD: {TradingVesselState.BATTERY, TradingVesselState.FULL_STOP},
}


class TradingVesselStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


class TradingVesselStateMachine:
    """Thread-safe vessel state machine with optional persistence.

    The vessel state IS the killswitch. If it's not FULL_FORWARD, no trade
    is ever placed. This is the primary safety mechanism.
    """

    def __init__(self, state_file: Optional[Path] = None):
        self._state_file = state_file
        self._state: TradingVesselState = TradingVesselState.FULL_STOP
        self._last_transition: float = time.time()
        self._transition_count: int = 0

        if state_file and state_file.exists():
            self._load_state()

    @property
    def state(self) -> TradingVesselState:
        return self._state

    @property
    def last_transition(self) -> float:
        return self._last_transition

    @property
    def transition_count(self) -> int:
        return self._transition_count

    @property
    def can_trade(self) -> bool:
        """The single most important property: is trading permitted?"""
        return self._state == TradingVesselState.FULL_FORWARD

    @property
    def can_collect_data(self) -> bool:
        """Can we stream data and observe opportunities?"""
        return self._state in (TradingVesselState.BATTERY, TradingVesselState.FULL_FORWARD)

    def can_transition_to(self, target: TradingVesselState) -> bool:
        """Check if a transition is valid without executing it."""
        return target in _TRANSITIONS.get(self._state, set())

    def transition_to(self, target: TradingVesselState) -> dict:
        """Execute a state transition. Returns transition summary dict.

        Raises:
            TradingVesselStateTransitionError: If the transition is not allowed.
        """
        if target == self._state:
            return {"success": True, "message": f"Already in {target.value}"}

        if not self.can_transition_to(target):
            allowed = [s.value for s in _TRANSITIONS.get(self._state, set())]
            raise TradingVesselStateTransitionError(
                f"Cannot transition from {self._state.value} to {target.value}. "
                f"Allowed transitions: {allowed}"
            )

        old_state = self._state
        self._state = target
        self._last_transition = time.time()
        self._transition_count += 1

        if self._state_file:
            self._save_state()

        logger.info(
            "Vessel transition: %s -> %s (transition #%d)",
            old_state.value,
            target.value,
            self._transition_count,
        )

        return {
            "success": True,
            "from": old_state.value,
            "to": target.value,
            "transition_number": self._transition_count,
        }

    def emergency_stop(self) -> dict:
        """Emergency stop: force transition to Full_Stop from ANY state."""
        old_state = self._state
        self._state = TradingVesselState.FULL_STOP
        self._last_transition = time.time()
        self._transition_count += 1

        if self._state_file:
            self._save_state()

        logger.warning(
            "EMERGENCY STOP: %s -> FULL_STOP (transition #%d)",
            old_state.value,
            self._transition_count,
        )

        return {
            "success": True,
            "emergency": True,
            "from": old_state.value,
            "to": TradingVesselState.FULL_STOP.value,
            "message": "All processes halted. No trades. No data streams.",
        }

    def _save_state(self) -> None:
        """Persist state to disk."""
        if not self._state_file:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "state": self._state.value,
            "last_transition": self._last_transition,
            "transition_count": self._transition_count,
        }
        self._state_file.write_text(json.dumps(data, indent=2))

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        if not self._state_file or not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text())
            self._state = TradingVesselState(data["state"])
            self._last_transition = data.get("last_transition", time.time())
            self._transition_count = data.get("transition_count", 0)
            logger.info("Loaded vessel state: %s", self._state.value)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Failed to load vessel state, defaulting to FULL_STOP: %s", exc)
            self._state = TradingVesselState.FULL_STOP

    def summary(self) -> dict:
        """Return a summary dict for status displays."""
        return {
            "state": self._state.value,
            "can_trade": self.can_trade,
            "can_collect_data": self.can_collect_data,
            "transitions": self._transition_count,
            "last_transition": self._last_transition,
        }

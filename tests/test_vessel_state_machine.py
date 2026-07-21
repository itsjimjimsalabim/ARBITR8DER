"""Tests for the vessel state machine — the permission gate."""
import json
import tempfile
from pathlib import Path

import pytest

from arbitr8der.vessel.trading_vessel_state_machine import (
    TradingVesselState,
    TradingVesselStateTransitionError,
    TradingVesselStateMachine,
)


class TestVesselStateBasicTransitions:
    """Core transition logic tests."""

    def test_starts_in_full_stop(self):
        vessel_state_machine = TradingVesselStateMachine()
        assert vessel_state_machine.state == TradingVesselState.FULL_STOP
        assert not vessel_state_machine.can_trade
        assert not vessel_state_machine.can_collect_data

    def test_transition_to_battery(self):
        vessel_state_machine = TradingVesselStateMachine()
        result = vessel_state_machine.transition_to(TradingVesselState.BATTERY)
        assert result["success"]
        assert result["from"] == "FULL_STOP"
        assert result["to"] == "BATTERY"
        assert vessel_state_machine.can_collect_data
        assert not vessel_state_machine.can_trade

    def test_transition_to_forward_from_battery(self):
        vessel_state_machine = TradingVesselStateMachine()
        vessel_state_machine.transition_to(TradingVesselState.BATTERY)
        result = vessel_state_machine.transition_to(TradingVesselState.FULL_FORWARD)
        assert result["success"]
        assert vessel_state_machine.can_trade
        assert vessel_state_machine.can_collect_data

    def test_direct_stop_to_forward_rejected(self):
        vessel_state_machine = TradingVesselStateMachine()
        with pytest.raises(TradingVesselStateTransitionError):
            vessel_state_machine.transition_to(TradingVesselState.FULL_FORWARD)

    def test_same_state_is_noop(self):
        vessel_state_machine = TradingVesselStateMachine()
        result = vessel_state_machine.transition_to(TradingVesselState.FULL_STOP)
        assert result["success"]
        assert "Already" in result["message"]

    def test_emergency_stop_from_any_state(self):
        vessel_state_machine = TradingVesselStateMachine()
        vessel_state_machine.transition_to(TradingVesselState.BATTERY)
        vessel_state_machine.transition_to(TradingVesselState.FULL_FORWARD)
        result = vessel_state_machine.emergency_stop()
        assert result["emergency"]
        assert result["to"] == "FULL_STOP"
        assert not vessel_state_machine.can_trade

    def test_forward_to_battery(self):
        vessel_state_machine = TradingVesselStateMachine()
        vessel_state_machine.transition_to(TradingVesselState.BATTERY)
        vessel_state_machine.transition_to(TradingVesselState.FULL_FORWARD)
        vessel_state_machine.transition_to(TradingVesselState.BATTERY)
        assert vessel_state_machine.state == TradingVesselState.BATTERY
        assert not vessel_state_machine.can_trade

    def test_forward_to_stop(self):
        vessel_state_machine = TradingVesselStateMachine()
        vessel_state_machine.transition_to(TradingVesselState.BATTERY)
        vessel_state_machine.transition_to(TradingVesselState.FULL_FORWARD)
        vessel_state_machine.transition_to(TradingVesselState.FULL_STOP)
        assert vessel_state_machine.state == TradingVesselState.FULL_STOP
        assert not vessel_state_machine.can_trade

    def test_battery_to_stop(self):
        vessel_state_machine = TradingVesselStateMachine()
        vessel_state_machine.transition_to(TradingVesselState.BATTERY)
        vessel_state_machine.transition_to(TradingVesselState.FULL_STOP)
        assert vessel_state_machine.state == TradingVesselState.FULL_STOP


class TestVesselStatePersistence:
    """State persistence to disk tests."""

    def test_save_and_load_state(self, tmp_path):
        state_file = tmp_path / "vessel_state.json"
        sm1 = TradingVesselStateMachine(state_file=state_file)
        sm1.transition_to(TradingVesselState.BATTERY)
        sm1.transition_to(TradingVesselState.FULL_FORWARD)

        sm2 = TradingVesselStateMachine(state_file=state_file)
        assert sm2.state == TradingVesselState.FULL_FORWARD
        assert sm2.transition_count == 2

    def test_load_corrupt_file_defaults_to_full_stop(self, tmp_path):
        state_file = tmp_path / "vessel_state.json"
        state_file.write_text("not valid json {{{")
        vessel_state_machine = TradingVesselStateMachine(state_file=state_file)
        assert vessel_state_machine.state == TradingVesselState.FULL_STOP

    def test_load_missing_file_defaults_to_full_stop(self, tmp_path):
        state_file = tmp_path / "does_not_exist.json"
        vessel_state_machine = TradingVesselStateMachine(state_file=state_file)
        assert vessel_state_machine.state == TradingVesselState.FULL_STOP


class TestVesselStateSummary:
    """Summary output tests."""

    def test_summary_contains_all_fields(self):
        vessel_state_machine = TradingVesselStateMachine()
        s = vessel_state_machine.summary()
        assert "state" in s
        assert "can_trade" in s
        assert "can_collect_data" in s
        assert "transitions" in s
        assert "last_transition" in s

    def test_transition_count_increments(self):
        vessel_state_machine = TradingVesselStateMachine()
        assert vessel_state_machine.transition_count == 0
        vessel_state_machine.transition_to(TradingVesselState.BATTERY)
        assert vessel_state_machine.transition_count == 1
        vessel_state_machine.transition_to(TradingVesselState.FULL_FORWARD)
        assert vessel_state_machine.transition_count == 2

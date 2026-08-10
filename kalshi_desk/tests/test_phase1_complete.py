"""Comprehensive unit tests for Phase 1 — Safe Runnable Foundation.

Tests cover:
  - Package import and version
  - CWD-independent path resolver
  - Typed configuration settings
  - Vessel state machine transitions, forced stop, timeout, audit trail
  - Runtime lease acquisition, release, expiry
  - CLI commands via Typer test runner
"""

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kalshi_desk_package import __version__
from kalshi_desk_package.cli.cli_application_entrypoint_main import app
from kalshi_desk_package.config.cwd_independent_path_resolver import (
    RUNTIME_DIR,
    RUNTIME_DATA_DIR,
    RUNTIME_LOGS_DIR,
    RUNTIME_STATE_DIR,
    SQLITE_DB_PATH,
    VESSEL_STATE_PATH,
    ensure_runtime_dirs,
    get_package_root,
)
from kalshi_desk_package.config.stream_provider_runtime_lease_file_lock import RuntimeLease
from kalshi_desk_package.config.typed_configuration_settings_module import load_settings
from kalshi_desk_package.core.vessel_state_machine import (
    IllegalTransitionError,
    VesselState,
    VesselStateMachine,
)

runner = CliRunner()


# =========================================================================
# Package basics
# =========================================================================

class TestPackageBasics:
    def test_version(self):
        assert __version__ == "0.1.0"

    def test_importable(self):
        import kalshi_desk_package
        assert hasattr(kalshi_desk_package, "__version__")


# =========================================================================
# Path resolver
# =========================================================================

class TestPathResolver:
    def test_package_root_points_to_kalshi_desk(self) -> None:
        root = get_package_root()
        assert root.name == "kalshi_desk"
        assert root.is_dir()

    def test_runtime_dirs_are_under_kalshi_desk(self):
        root = get_package_root()
        assert str(RUNTIME_DIR).startswith(str(root))
        assert str(RUNTIME_DATA_DIR).startswith(str(root))
        assert str(RUNTIME_STATE_DIR).startswith(str(root))
        assert str(RUNTIME_LOGS_DIR).startswith(str(root))

    def test_sqlite_path_is_under_data_dir(self):
        assert str(SQLITE_DB_PATH).startswith(str(RUNTIME_DATA_DIR))

    def test_vessel_state_path_is_under_state_dir(self):
        assert str(VESSEL_STATE_PATH).startswith(str(RUNTIME_STATE_DIR))

    def test_ensure_runtime_dirs_creates_directories(self, tmp_path, monkeypatch):
        import kalshi_desk_package.config.cwd_independent_path_resolver as mod
        monkeypatch.setattr(mod, "RUNTIME_DIR", tmp_path / "runtime")
        monkeypatch.setattr(mod, "RUNTIME_DATA_DIR", tmp_path / "runtime" / "data")
        monkeypatch.setattr(mod, "RUNTIME_STATE_DIR", tmp_path / "runtime" / "state")
        monkeypatch.setattr(mod, "RUNTIME_LOGS_DIR", tmp_path / "runtime" / "logs")
        monkeypatch.setattr(mod, "RUNTIME_ARCHIVES_DIR", tmp_path / "runtime" / "archives")
        ensure_runtime_dirs()
        for subdir in ["runtime", "runtime/data", "runtime/state", "runtime/logs", "runtime/archives"]:
            assert (tmp_path / subdir).is_dir()


# =========================================================================
# Configuration settings
# =========================================================================

class TestConfigurationSettings:
    def test_defaults(self):
        settings = load_settings()
        assert settings.wallet_mode == "paper"
        assert settings.trading_mode == "hold"
        assert settings.auto_arm is False
        assert settings.dry_run is True

    def test_override_via_kwargs(self):
        settings = load_settings(wallet_mode="live", dry_run=False)
        assert settings.wallet_mode == "live"
        assert settings.dry_run is False

    def test_env_prefix_is_ar8(self):
        settings = load_settings()
        assert settings.model_config["env_prefix"] == "AR8_"


# =========================================================================
# Vessel state machine
# =========================================================================

class TestVesselStateMachine:
    def _make_machine(self, tmp_path):
        return VesselStateMachine(state_file=tmp_path / "vessel_state.json")

    def test_starts_in_full_stop(self, tmp_path):
        machine = self._make_machine(tmp_path)
        assert machine.current_state == VesselState.FULL_STOP

    def test_battery_from_full_stop(self, tmp_path):
        machine = self._make_machine(tmp_path)
        machine.transition(VesselState.BATTERY, reason="test")
        assert machine.current_state == VesselState.BATTERY

    def test_full_forward_from_battery(self, tmp_path):
        machine = self._make_machine(tmp_path)
        machine.transition(VesselState.BATTERY, reason="arm")
        machine.transition(VesselState.FULL_FORWARD, reason="go")
        assert machine.current_state == VesselState.FULL_FORWARD

    def test_invalid_transition_full_stop_to_full_forward(self, tmp_path):
        machine = self._make_machine(tmp_path)
        with pytest.raises(IllegalTransitionError):
            machine.transition(VesselState.FULL_FORWARD, reason="skip battery")

    def test_invalid_transition_full_forward_to_battery(self, tmp_path):
        machine = self._make_machine(tmp_path)
        machine.transition(VesselState.BATTERY, reason="arm")
        machine.transition(VesselState.FULL_FORWARD, reason="go")
        with pytest.raises(IllegalTransitionError):
            machine.transition(VesselState.BATTERY, reason="back to battery")

    def test_can_stop_from_any_state(self, tmp_path):
        machine = self._make_machine(tmp_path)
        machine.transition(VesselState.BATTERY, reason="arm")
        machine.transition(VesselState.FULL_FORWARD, reason="go")
        machine.transition(VesselState.FULL_STOP, reason="emergency")
        assert machine.current_state == VesselState.FULL_STOP

    def test_forced_stop_on_instantiation(self, tmp_path):
        f = tmp_path / "vessel_state.json"
        f.write_text(json.dumps({"vessel_state": "full_forward", "audit_log": []}))
        machine = VesselStateMachine(state_file=f)
        assert machine.current_state == VesselState.FULL_STOP

    def test_audit_trail_recorded(self, tmp_path):
        machine = self._make_machine(tmp_path)
        machine.transition(VesselState.BATTERY, reason="arm")
        info = machine.get_state()
        # First entry is the forced stop from startup
        assert any(e["reason"] == "startup: forced full stop" for e in info["audit_log"])
        assert any(e["reason"] == "arm" for e in info["audit_log"])

    def test_persists_state_to_file(self, tmp_path):
        f = tmp_path / "vessel_state.json"
        machine = VesselStateMachine(state_file=f)
        machine.transition(VesselState.BATTERY, reason="test")
        data = json.loads(f.read_text())
        assert data["vessel_state"] == "battery"

    def test_get_state_returns_dict(self, tmp_path):
        machine = self._make_machine(tmp_path)
        info = machine.get_state()
        assert "vessel_state" in info
        assert "audit_log" in info
        assert isinstance(info["audit_log"], list)


# =========================================================================
# Runtime lease
# =========================================================================

class TestRuntimeLease:
    def test_acquire_first(self, tmp_path):
        lease = RuntimeLease(lease_file=tmp_path / "lease.json", ttl=300)
        assert lease.acquire("proc-1") is True

    def test_release(self, tmp_path):
        lease = RuntimeLease(lease_file=tmp_path / "lease.json", ttl=300)
        lease.acquire("proc-1")
        assert lease.release("proc-1") is True
        assert lease.current_owner() is None

    def test_acquire_blocked_by_active_lease(self, tmp_path):
        lease = RuntimeLease(lease_file=tmp_path / "lease.json", ttl=300)
        lease.acquire("proc-1")
        assert lease.acquire("proc-2") is False

    def test_same_owner_reacquire(self, tmp_path):
        lease = RuntimeLease(lease_file=tmp_path / "lease.json", ttl=300)
        lease.acquire("proc-1")
        assert lease.acquire("proc-1") is True

    def test_expired_lease_can_be_stolen(self, tmp_path):
        lease = RuntimeLease(lease_file=tmp_path / "lease.json", ttl=1)
        lease.acquire("proc-1")
        time.sleep(1.1)
        assert lease.acquire("proc-2") is True
        assert lease.current_owner() == "proc-2"

    def test_release_wrong_owner_fails(self, tmp_path):
        lease = RuntimeLease(lease_file=tmp_path / "lease.json", ttl=300)
        lease.acquire("proc-1")
        assert lease.release("proc-2") is False

    def test_current_owner_none_when_no_file(self, tmp_path):
        lease = RuntimeLease(lease_file=tmp_path / "lease.json", ttl=300)
        assert lease.current_owner() is None

    def test_corrupt_file_treated_as_empty(self, tmp_path):
        f = tmp_path / "lease.json"
        f.write_text("not valid json{{{")
        lease = RuntimeLease(lease_file=f, ttl=300)
        assert lease.current_owner() is None
        assert lease.acquire("proc-1") is True


# =========================================================================
# CLI commands
# =========================================================================

class TestCLICommands:
    def test_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_status_default(self):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Vessel:" in result.output

    def test_status_json(self):
        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "vessel_state" in data
        assert data["wallet_mode"] == "paper"

    def test_vessel_status(self):
        result = runner.invoke(app, ["vessel", "status"])
        assert result.exit_code == 0
        assert "Vessel state:" in result.output

    def test_vessel_battery(self):
        result = runner.invoke(app, ["vessel", "battery"])
        assert result.exit_code == 0
        assert "Battery" in result.output

    def test_vessel_forward(self):
        result = runner.invoke(app, ["vessel", "forward"])
        assert result.exit_code == 0
        assert "Full_Forward" in result.output

    def test_vessel_stop(self):
        result = runner.invoke(app, ["vessel", "stop"])
        assert result.exit_code == 0
        assert "Full_Stop" in result.output

    def test_forward_start_repl(self):
        result = runner.invoke(app, ["forward", "start"])
        assert result.exit_code == 0
        assert "Vessel:" in result.output or "battery" in result.output

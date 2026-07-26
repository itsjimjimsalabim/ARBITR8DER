"""Session archive — persists full session data for replay and analysis.

Writes timestamped JSONL files to runtime/archives/sessions/ containing:
  - Session metadata (start/end time, vessel transitions, commands)
  - Snapshots received
  - Predictions generated
  - Journal entries
  - Health reports
  - Final scorecard

Each archive file is a complete record of a trading session that can be
replayed, analyzed, or used to train better prediction models.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)


@dataclass
class SessionArchive:
    """Accumulates session data and writes it to disk on close."""

    session_id: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str | None = None

    # Event log (chronological)
    events: list[dict[str, Any]] = field(default_factory=list)

    # Accumulated data
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    journal_entries: list[dict[str, Any]] = field(default_factory=list)
    health_reports: list[dict[str, Any]] = field(default_factory=list)
    vessel_transitions: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._archive_dir: Path | None = None

    def _ensure_dir(self) -> Path:
        if self._archive_dir is None:
            self._archive_dir = Path(__file__).resolve().parent.parent.parent / "runtime" / "archives" / "sessions"
            self._archive_dir.mkdir(parents=True, exist_ok=True)
        return self._archive_dir

    def _log_event(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **data,
        })

    def record_snapshot(self, snapshot: Any) -> None:
        """Record a snapshot (HotSnapshot or dict) to the archive."""
        if hasattr(snapshot, "model_dump"):
            data = snapshot.model_dump(mode="json")
        elif hasattr(snapshot, "to_dict"):
            data = snapshot.to_dict()
        else:
            data = snapshot
        self.snapshots.append(data)
        self._log_event("snapshot", {"asset": data.get("asset", "?"), "version": data.get("snapshot_version", 0)})

    def record_prediction(self, record: Any) -> None:
        """Record a prediction (PredictionRecord or dict) to the archive."""
        if hasattr(record, "to_dict"):
            data = record.to_dict()
        elif hasattr(record, "model_dump"):
            data = record.model_dump(mode="json")
        elif isinstance(record, dict):
            data = record
        else:
            # Fallback: extract common fields from any object
            data = {
                "asset": getattr(record, "asset", "?"),
                "ticker": getattr(record, "ticker", "?"),
                "yes_probability": getattr(record, "yes_probability", None),
                "prediction_id": getattr(record, "prediction_id", "?"),
            }
        self.predictions.append(data)
        self._log_event("prediction", {"asset": data.get("asset", "?"), "ticker": data.get("ticker", "?")})

    def record_journal_entry(self, entry: Any) -> None:
        """Record a journal entry to the archive."""
        if hasattr(entry, "to_dict"):
            data = entry.to_dict()
        elif hasattr(entry, "model_dump"):
            data = entry.model_dump(mode="json")
        else:
            data = entry
        self.journal_entries.append(data)
        self._log_event("journal", {"entry_id": data.get("entry_id", "?"), "asset": data.get("asset", "?")})

    def record_health(self, report: str) -> None:
        """Record a health report string."""
        self.health_reports.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "report": report,
        })
        self._log_event("health", {})

    def record_vessel_transition(self, from_state: str, to_state: str, reason: str) -> None:
        """Record a vessel state transition."""
        transition = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "from": from_state,
            "to": to_state,
            "reason": reason,
        }
        self.vessel_transitions.append(transition)
        self._log_event("vessel", transition)

    def record_command(self, command: str, args: str = "") -> None:
        """Record a REPL command invocation."""
        self._log_event("command", {"cmd": command, "args": args})

    def record_note(self, text: str) -> None:
        """Record a freeform note."""
        self._log_event("note", {"text": text})

    def close(self) -> Path:
        """Write the complete archive to disk and return the file path."""
        self.ended_at = datetime.now(timezone.utc).isoformat()
        archive_dir = self._ensure_dir()
        archive_file = archive_dir / f"session_{self.session_id}.jsonl"

        archive_data = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "snapshot_count": len(self.snapshots),
            "prediction_count": len(self.predictions),
            "journal_count": len(self.journal_entries),
            "health_count": len(self.health_reports),
            "command_count": sum(1 for e in self.events if e["type"] == "command"),
            "vessel_transitions": len(self.vessel_transitions),
        }

        try:
            # Write events as JSONL
            with open(archive_file, "w") as f:
                for event in self.events:
                    f.write(json.dumps(event) + "\n")

            # Write summary
            summary_file = archive_dir / f"session_{self.session_id}_summary.json"
            with open(summary_file, "w") as f:
                json.dump(archive_data, f, indent=2)

            logger.info("Session archive written: %s (%d events)", archive_file, len(self.events))
            return archive_file
        except OSError as exc:
            logger.error("Failed to write session archive: %s", exc)
            return archive_file

    def summary(self) -> dict[str, Any]:
        """Return session summary stats."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_events": len(self.events),
            "snapshots": len(self.snapshots),
            "predictions": len(self.predictions),
            "journal_entries": len(self.journal_entries),
            "health_reports": len(self.health_reports),
            "vessel_transitions": len(self.vessel_transitions),
            "commands_run": sum(1 for e in self.events if e["type"] == "command"),
        }


def format_archive_summary_human(summary: dict[str, Any]) -> str:
    """Format session archive summary as human-readable text."""
    lines = [
        "=== Session Archive ===",
        f"  Session:      {summary['session_id']}",
        f"  Started:      {summary['started_at']}",
        f"  Ended:        {summary.get('ended_at', '(active)')}",
        "",
        f"  Total events: {summary['total_events']}",
        f"  Snapshots:    {summary['snapshots']}",
        f"  Predictions:  {summary['predictions']}",
        f"  Journal:      {summary['journal_entries']}",
        f"  Health:       {summary['health_reports']}",
        f"  Transitions:  {summary['vessel_transitions']}",
        f"  Commands:     {summary['commands_run']}",
    ]
    return "\n".join(lines)

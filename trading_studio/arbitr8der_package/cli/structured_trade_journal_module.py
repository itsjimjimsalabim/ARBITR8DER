"""Structured trade journal — links observations, hypotheses, predictions, and outcomes.

Entries are persisted as JSONL under runtime/archives/journal/ for durable
history and replay. Each entry captures the full reasoning chain:

  observation → hypothesis → prediction → outcome → next_experiment

This replaces the simple text journal from Phase 4 with structured, queryable
entries that can be scored and analyzed over time.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)


class EntryStatus(str, Enum):
    """Lifecycle status of a journal entry."""
    HYPOTHESIS = "hypothesis"      # Observation logged, prediction pending
    PREDICTED = "predicted"        # Prediction recorded
    RESOLVED = "resolved"          # Outcome known, scored
    REVIEWED = "reviewed"          # Operator reviewed the result
    ARCHIVED = "archived"          # Final state


@dataclass
class JournalEntry:
    """A single structured journal entry linking the full reasoning chain."""
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Context
    asset: str = ""
    session_id: str = ""

    # Snapshot linkage
    snapshot_version: int | None = None
    snapshot_timestamp: str | None = None

    # Reasoning chain
    observation: str = ""
    hypothesis: str = ""
    next_experiment: str = ""

    # Prediction linkage
    prediction_id: str | None = None
    yes_probability: float | None = None
    confidence: float | None = None
    edge_pct: float | None = None
    ticker: str | None = None
    model_version: str | None = None

    # Outcome linkage
    actual_outcome: int | None = None  # 0 = NO, 1 = YES
    outcome_timestamp: str | None = None
    score_brier: float | None = None
    score_log_loss: float | None = None

    # Status
    status: str = EntryStatus.HYPOTHESIS.value

    # Freeform notes (operator can append anytime)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def add_note(self, text: str) -> None:
        """Append a timestamped note."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self.notes.append(f"[{ts}] {text}")
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def link_prediction(
        self,
        prediction_id: str,
        yes_probability: float,
        confidence: float | None,
        edge_pct: float | None,
        ticker: str,
        model_version: str,
    ) -> None:
        """Link a prediction record to this journal entry."""
        self.prediction_id = prediction_id
        self.yes_probability = yes_probability
        self.confidence = confidence
        self.edge_pct = edge_pct
        self.ticker = ticker
        self.model_version = model_version
        self.status = EntryStatus.PREDICTED.value
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def resolve(self, actual_outcome: int, score_brier: float | None = None, score_log_loss: float | None = None) -> None:
        """Record the market outcome and scores."""
        self.actual_outcome = actual_outcome
        self.outcome_timestamp = datetime.now(timezone.utc).isoformat()
        self.score_brier = score_brier
        self.score_log_loss = score_log_loss
        self.status = EntryStatus.RESOLVED.value
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def review(self) -> None:
        """Mark as operator-reviewed."""
        self.status = EntryStatus.REVIEWED.value
        self.updated_at = datetime.now(timezone.utc).isoformat()


class TradeJournal:
    """Persistent structured journal backed by JSONL files.

    Each session gets its own journal file under runtime/archives/journal/.
    """

    def __init__(self, session_id: str | None = None, journal_dir: Path | str | None = None) -> None:
        if journal_dir is not None:
            self._journal_dir = Path(journal_dir)
        else:
            self._journal_dir = Path(__file__).resolve().parent.parent.parent / "runtime" / "archives" / "journal"
        self._journal_dir.mkdir(parents=True, exist_ok=True)

        if session_id is None:
            session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._session_id = session_id
        self._journal_file = self._journal_dir / f"journal_{session_id}.jsonl"
        self._entries: list[JournalEntry] = []

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def entries(self) -> list[JournalEntry]:
        return list(self._entries)

    def start_entry(
        self,
        asset: str,
        observation: str,
        hypothesis: str,
        snapshot_version: int | None = None,
        snapshot_timestamp: str | None = None,
    ) -> JournalEntry:
        """Create a new journal entry with an observation and hypothesis."""
        entry = JournalEntry(
            asset=asset,
            session_id=self._session_id,
            snapshot_version=snapshot_version,
            snapshot_timestamp=snapshot_timestamp,
            observation=observation,
            hypothesis=hypothesis,
        )
        self._entries.append(entry)
        self._persist_entry(entry)
        logger.info("Journal entry %s started for %s (snapshot v%s)",
                     entry.entry_id, asset, snapshot_version)
        return entry

    def record_prediction(self, entry_id: str, prediction_record: Any) -> JournalEntry | None:
        """Link a prediction record to an existing journal entry."""
        entry = self._find_entry(entry_id)
        if entry is None:
            logger.warning("Journal entry %s not found", entry_id)
            return None

        entry.link_prediction(
            prediction_id=prediction_record.prediction_id,
            yes_probability=prediction_record.yes_probability,
            confidence=prediction_record.confidence,
            edge_pct=prediction_record.edge_pct,
            ticker=prediction_record.ticker,
            model_version=prediction_record.model_version,
        )
        self._persist_entry(entry)
        return entry

    def resolve_entry(
        self,
        entry_id: str,
        actual_outcome: int,
        score_brier: float | None = None,
        score_log_loss: float | None = None,
    ) -> JournalEntry | None:
        """Record the outcome for a journal entry."""
        entry = self._find_entry(entry_id)
        if entry is None:
            return None

        entry.resolve(actual_outcome, score_brier, score_log_loss)
        self._persist_entry(entry)
        return entry

    def add_note(self, entry_id: str, text: str) -> JournalEntry | None:
        """Append a note to an existing entry."""
        entry = self._find_entry(entry_id)
        if entry is None:
            return None
        entry.add_note(text)
        self._persist_entry(entry)
        return entry

    def set_next_experiment(self, entry_id: str, text: str) -> JournalEntry | None:
        """Set the next experiment to run after this entry."""
        entry = self._find_entry(entry_id)
        if entry is None:
            return None
        entry.next_experiment = text
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist_entry(entry)
        return entry

    def get_open_entries(self, asset: str | None = None) -> list[JournalEntry]:
        """Get entries that are not yet resolved."""
        open_statuses = {EntryStatus.HYPOTHESIS.value, EntryStatus.PREDICTED.value}
        results = [e for e in self._entries if e.status in open_statuses]
        if asset:
            results = [e for e in results if e.asset.upper() == asset.upper()]
        return results

    def get_resolved_entries(self, asset: str | None = None) -> list[JournalEntry]:
        """Get entries that have been resolved."""
        results = [e for e in self._entries if e.status in {
            EntryStatus.RESOLVED.value, EntryStatus.REVIEWED.value
        }]
        if asset:
            results = [e for e in results if e.asset.upper() == asset.upper()]
        return results

    def summary(self) -> dict[str, Any]:
        """Generate a summary of all journal entries."""
        total = len(self._entries)
        by_status: dict[str, int] = {}
        for e in self._entries:
            by_status[e.status] = by_status.get(e.status, 0) + 1

        resolved = [e for e in self._entries if e.status in {EntryStatus.RESOLVED.value, EntryStatus.REVIEWED.value}]
        correct = sum(1 for e in resolved if e.actual_outcome is not None and e.yes_probability is not None
                      and (e.yes_probability >= 0.5) == (e.actual_outcome == 1))
        brier_scores = [e.score_brier for e in resolved if e.score_brier is not None]

        return {
            "session_id": self._session_id,
            "total_entries": total,
            "by_status": by_status,
            "resolved_count": len(resolved),
            "correct_count": correct,
            "accuracy_pct": correct / len(resolved) * 100 if resolved else None,
            "mean_brier": sum(brier_scores) / len(brier_scores) if brier_scores else None,
        }

    def _find_entry(self, entry_id: str) -> JournalEntry | None:
        for e in self._entries:
            if e.entry_id == entry_id:
                return e
        return None

    def _persist_entry(self, entry: JournalEntry) -> None:
        """Append entry to the JSONL journal file."""
        try:
            with open(self._journal_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except OSError as exc:
            logger.error("Failed to persist journal entry: %s", exc)


def format_entry_human(entry: JournalEntry) -> str:
    """Format a journal entry as human-readable text."""
    lines = [
        f"=== Journal {entry.entry_id} [{entry.status}] ===",
        f"  Asset:      {entry.asset}",
        f"  Created:    {entry.created_at}",
        f"  Snapshot v: {entry.snapshot_version or 'n/a'}",
        "",
        f"  Observation: {entry.observation}",
        f"  Hypothesis:  {entry.hypothesis}",
    ]

    if entry.prediction_id:
        lines.append(f"  Prediction:  {entry.prediction_id} ({entry.ticker})")
        if entry.yes_probability is not None:
            lines.append(f"    YES prob:  {entry.yes_probability:.4f}")
        if entry.confidence is not None:
            lines.append(f"    Confidence: {entry.confidence:.4f}")
        if entry.edge_pct is not None:
            lines.append(f"    Edge:      {entry.edge_pct:.4f}%")
    else:
        lines.append("  Prediction:  (none)")

    if entry.actual_outcome is not None:
        outcome_str = "YES" if entry.actual_outcome == 1 else "NO"
        lines.append(f"  Outcome:     {outcome_str}")
        if entry.score_brier is not None:
            lines.append(f"    Brier:     {entry.score_brier:.4f}")
        if entry.score_log_loss is not None:
            lines.append(f"    Log loss:  {entry.score_log_loss:.4f}")
    else:
        lines.append("  Outcome:     (pending)")

    if entry.next_experiment:
        lines.append(f"  Next:        {entry.next_experiment}")

    if entry.notes:
        lines.append("")
        lines.append("  Notes:")
        for n in entry.notes:
            lines.append(f"    {n}")

    return "\n".join(lines)


def format_entry_json(entry: JournalEntry) -> str:
    """Format a journal entry as JSON."""
    return json.dumps(entry.to_dict(), indent=2)

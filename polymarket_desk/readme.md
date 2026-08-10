# Polymarket Desk

**Status: Placeholder — not yet implemented.**

This directory is reserved for a future Polymarket trading desk, to be built separately from the Kalshi desk.

## Target Layout (when implemented)

```
polymarket_desk/
  pyproject.toml           ← package metadata, deps, entry points
  polymarket_desk_package/ ← installable package
    cli/
    config/
    data_sources/
    execution/
    risk/
    core/
  tests/
  scripts/
  streams/                 ← API credentials (gitignored)
  runtime/                 ← local data: DBs, state, logs (gitignored)
```

## Rules

- Keep credentials, streams, orders, positions, runtime data, logs, and PnL **isolated** from `kalshi_desk/`.
- Do not copy Kalshi execution code or runtime data into this directory.
- Do not implement until the Kalshi desk has a verified profitability track record.
- Start in `Full_Stop` and PAPER mode. No task in this backlog authorizes a live order.

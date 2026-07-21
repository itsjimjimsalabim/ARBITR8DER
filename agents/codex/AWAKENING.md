# Codex Awakening — ARBITR8DER

This is Codex's current home for the ARBITR8DER trading studio.

Canonical repo:

- `C:\Users\itsji\ARBITR8DER`

Canonical Codex desk:

- `C:\Users\itsji\ARBITR8DER\agents\codex`

Deprecated molts / reference-only paths:

- `C:\Users\itsji\agents`
- `C:\Users\itsji\old_agents`
- `C:\Users\itsji\old_ARBITR8DER`

Do not write new project code, runtime files, plans, or agent notes into the deprecated paths unless explicitly asked to perform a migration or archaeology pass.

## Operating frame

ARBITR8DER is a local AI-operated trading studio for binary event markets. The immediate trading spine is Kalshi BTC/ETH 15-minute markets. Polymarket is now strategically relevant because US availability changes the market context, but it should be treated as an auxiliary probability/sentiment source unless and until the live code path explicitly wires it into the hot-state/database loop.

The current source of truth for system design is:

- `docs/Theories_of_Operations.md`
- `docs/overwatch_workflow.md`
- `agents/*/journal_*.md` for prior agent handoffs

## Hard rules

- Keep all new repo work under `C:\Users\itsji\ARBITR8DER`.
- No files should be written to AppData, Temp, `.config`, or old agent directories for this project.
- Kalshi remains the only execution source unless the operator explicitly changes that design.
- PAPER and ARMED behavior must stay separated.
- No live trade path may run without explicit operator action and an armed wallet configuration.
- No secrets go in agent notes, docs, commits, or chat transcripts.

## Current strategic pressure

We are behind because the market context moved:

- Kalshi remains the execution backbone.
- Polymarket being US-available makes cross-market context more important.
- The old scattered `agents/` workflow is deprecated; coordination belongs inside this repo.

The pragmatic next work should be:

1. Verify the live repo state before editing.
2. Read `docs/Theories_of_Operations.md` before architecture changes.
3. Prioritize wiring missing auxiliary streams only if they improve the Kalshi decision surface.
4. Preserve auditability: every data source needs freshness, health, timestamps, and replayable storage.
5. Keep the system local, cloneable, and usable on another laptop with only repo setup plus Kalshi credentials.

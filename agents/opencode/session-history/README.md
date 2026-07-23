# OpenCode Session History

## Session Databases

OpenCode stores all session history in a single SQLite database per OS:

| Label | Real Path | Size |
|-------|-----------|------|
| Windows | `C:\Users\itsji\.local\share\opencode\opencode.db` | ~1 GB |
| WSL/Ubuntu | `/home/itsjimjimsalabim/.local/share\opencode\opencode.db` | ~46 MB |

After running `setup-symlinks.ps1` as admin, this directory contains symlinks:

- `opencode_windows.db` -> Windows DB
- `opencode_wsl.db` -> WSL DB

These symlinks are **gitignored** (they point to ~1.5 GB of data that must never go to GitHub).

## Setup (one-time, requires admin)

```powershell
# Right-click PowerShell -> Run as Administrator
cd C:\Users\itsji\ARBITR8DER
.\agents\opencode\session-history\setup-symlinks.ps1
```

## Session Notes (from prior sessions)

- `2026-07-17_1245-session-notes.md` — First debugging session, 7 problems found
- `2026-07-17_fixes-and-learnings.md` — All fixes (Binance WS, strike prices, limit orders)

## Why symlinks?

- The DB files are massive and change constantly (every chat turn writes to them)
- Git cannot track them efficiently — they'd bloat every commit
- Symlinks let agents reference the live data without duplicating it
- The `setup-symlinks.ps1` script is the only thing committed that points here

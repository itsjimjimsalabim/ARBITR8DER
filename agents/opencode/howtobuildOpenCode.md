# howtobuildOpenCode — Rebuild and Reconnect Guide

> This document tells any AI exactly how to install, configure, and reconnect
> OpenCode on this machine. OpenCode is a pre-built binary — there is no source
> to compile. The "build" is installing the binary and wiring the config.

---

## 1. System Layout

### Canonical Locations

```
C:\Users\itsji\ARBITR8DER                       <- main workspace
C:\Users\itsji\ARBITR8DER\agents\opencode\      <- agent desk (pointers + session history)
C:\Users\itsji\ARBITR8DER\agents\agents.md      <- one brain for all agents
```

### OpenCode Install Paths

| Platform | Binary | Config |
|----------|--------|--------|
| WSL/Linux | `/home/itsjimjimsalabim/.opencode/bin/opencode` | `~/.config/opencode/opencode.jsonc` |
| Windows | (runs via WSL) | `C:\Users\itsji\.config\opencode\opencode.jsonc` |

OpenCode does not have a Windows-native binary in this setup. The Windows bat
file launches via WSL.

---

## 2. Prerequisites

| # | Dependency | Version | Install | Verify |
|---|-----------|---------|---------|--------|
| 1 | **Node.js** | >= 22.0.0 | `nvm install 22` or nodejs.org | `node --version` |
| 2 | **npm** | latest | comes with Node.js | `npm --version` |
| 3 | **WSL** | any | Windows Features or `wsl --install` | `wsl --list` |

---

## 3. Install / Update OpenCode

### 3.1 Install the Binary

The binary is distributed as a standalone executable. It does not compile from
source. To install or update:

```bash
# The binary lives at:
#   Linux/WSL: /home/itsjimjimsalabim/.opencode/bin/opencode
#   It is an ELF 64-bit executable on Linux.

# To reinstall or update, download the latest release and replace the binary.
# Check https://opencode.ai for the latest version.
```

### 3.2 Install the Plugin (if needed)

```bash
cd /home/itsjimjimsalabim/.opencode
npm install @opencode-ai/plugin
```

### 3.3 Verify

```bash
/home/itsjimjimsalabim/.opencode/bin/opencode --version
```

---

## 4. Configuration

### 4.1 Config File

| Platform | Path |
|----------|------|
| Linux/WSL | `~/.config/opencode/opencode.jsonc` |
| Windows | `C:\Users\itsji\.config\opencode\opencode.jsonc` |

Both configs are synced and include:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "permission": "allow",
  "instructions": ["...agents.md path..."],
  "agent": {
    "build": { "steps": 200 },
    "plan": { "steps": 200 }
  },
  "compaction": {
    "auto": true,
    "tail_turns": 20
  }
}
```

- `"permission": "allow"` — skips all permission prompts (equivalent to
  `--dangerously-skip-permissions`). Local-only, trusted environment.
- `"instructions"` — points to `agents.md` so the agent loads the one-brain
  system prompt on startup.
- `"agent"` — 200 steps for both build and plan modes (max effort).
- `"compaction"` — auto-compaction with 20 tail turns preserved.

### 4.2 Environment Variables

| Variable | Purpose | Where Set |
|----------|---------|-----------|
| `OPENCODE_API_KEY` | API key for NVIDIA NIM provider | `ARBITR8DER/.env` or launcher |
| `OPENAI_MODEL` | Model name (default: `big-pickle`) | Launcher or shell |

The API key is stored in `C:\Users\itsji\ARBITR8DER\.env` and sourced by
the launcher scripts. The key is also hardcoded in `opencode.jsonc` under
the provider config.

**Windows gotcha:** The `opencode.jsonc` at `~/.config/opencode/` has the provider
config hardcoded. The project-level `opencode.json` only sets permissions. Both work
because OpenCode reads both.

---

## 5. Launch Chain

### Windows (Desktop Shortcut)

```
Desktop: "OpenCode at Home.lnk"
  → wt.exe → opencode (in C:\Users\itsji\ARBITR8DER)
```

### Windows (Batch File — WSL edition)

```
local-files\Desktop-Shortcuts\OpenCode_Ubuntu.bat
  → cmd /k "wsl bash -c 'source .env; export OPENAI_MODEL=big-pickle; cd ARBITR8DER && opencode --auto'"
```

### Linux / WSL

```
~/bin/claude (for Claude) — opencode is a direct binary call
  → Sources ARBITR8DER/.env (OPENCODE_API_KEY)
  → Sets OPENAI_MODEL=big-pickle
  → exec opencode --auto
```

### Desktop Shortcut Locations

All shortcuts live in: `C:\Users\itsji\local-files\Desktop-Shortcuts\`
Windows also syncs them to: `C:\Users\itsji\OneDrive\Desktop\` (registry redirect)

| Shortcut | Platform | Target |
|----------|----------|--------|
| `OpenCode at Home.lnk` | Windows | `wt.exe` → `opencode` |
| `OpenCode_Ubuntu.bat` | Windows→WSL | `wsl bash -c ... opencode` |
| `Claude Windows.lnk` | Windows | `C:\Users\itsji\bin\claude.bat` → native node |
| `OpenClaude_Ubuntu.bat` | Windows→WSL | `wsl bash -ic claude` |
| `Start Codex Full Access.lnk` | Windows | `codex.exe` |

---

## 6. Auto-Approve & Permissions

Both OpenCode instances (Windows config and WSL/Ubuntu config) are configured
with `"permission": "allow"`. This means:

- All tool calls (Bash, Read, Write, Edit, Glob, Grep, Task, WebFetch, etc.)
  execute without permission prompts.
- This is the equivalent of `--dangerously-skip-permissions`.
- Only appropriate for a trusted, local-only environment.

The `agents.md` instructions file also reinforces this:
> "Give yourselves full access, always allow, dangerously-skip-permissions"

No additional CLI flags are needed — the config handles it.

---

## 7. Reconnection Checklist

| Step | Command | Expected |
|------|---------|----------|
| 1 | `node --version` | v22+ |
| 2 | `npm --version` | Latest |
| 3 | `/home/itsjimjimsalabim/.opencode/bin/opencode --version` | Prints version |
| 4 | `cat ~/.config/opencode/opencode.jsonc` | Shows `"permission": "allow"` + instructions |
| 5 | `cat ARBITR8DER/.env` | Shows `OPENCODE_API_KEY=nvapi-...` |
| 6 | Double-click desktop shortcut | OpenCode launches in WSL |

---

## 8. First Agent Workflow

When a fresh agent starts:

1. Read `C:\Users\itsji\ARBITR8DER\agents\agents.md` — the one brain
2. Read `agents/opencode/README.md` — pointers to session history
3. Run the reconnection checklist above
4. Launch via the desktop shortcut or batch file

---

## 9. Debug Tips

### Binary won't run
```bash
ls -la /home/itsjimjimsalabim/.opencode/bin/opencode
chmod +x /home/itsjimjimsalabim/.opencode/bin/opencode
file /home/itsjimjimsalabim/.opencode/bin/opencode
# Should be: ELF 64-bit LSB executable, x86-64
```

### API key not being picked up
```bash
# Check .env file
cat /mnt/c/Users/itsji/ARBITR8DER/.env
# Should contain OPENCODE_API_KEY=nvapi-...

# Or check the config file
cat ~/.config/opencode/opencode.jsonc | grep apiKey
```

### Config not loading
```bash
cat ~/.config/opencode/opencode.jsonc
# Windows side
cat /mnt/c/Users/itsji/.config/opencode/opencode.jsonc
```

### Permission denied on launch
```bash
chmod +x /home/itsjimjimsalabim/.opencode/bin/opencode
```

### WSL can't find the binary
```bash
# Use the full path in the bat file, not a relative path
# Wrong: opencode
# Right: /home/itsjimjimsalabim/.opencode/bin/opencode
```

### Batch file closes immediately
The batch file includes `pause` on error. If it still closes:
1. Open cmd manually and run the .bat to see output
2. Check that WSL is installed: `wsl --list`
3. Check that the .env has OPENCODE_API_KEY set

---

## 10. Customizations

### Permission Mode

`"permission": "allow"` in `opencode.jsonc` — equivalent to
`--dangerously-skip-permissions`. All tools run without prompts.

### Model Selection

The model is set via `OPENAI_MODEL` env var. Default: `big-pickle`.
Change in the launcher scripts or shell profile.

### Agent Steps

Both `build` and `plan` modes are set to 200 steps (maximum effort).
This is configured in `opencode.jsonc` under `agent.build.steps` and
`agent.plan.steps`.

### Compaction

Auto-compaction is enabled with 20 tail turns preserved. This means
the context window is automatically compressed when it gets full, but
the last 20 turns of conversation are kept in full detail.

### Session Database

OpenCode stores all chat history in `~/.local/share/opencode/opencode.db`.
This is NOT in the repo — it is app-managed data.
Do not move or delete unless you want to lose all session history.

### What NOT to Touch

| Item | Why |
|------|-----|
| `~/.local/share/opencode/opencode.db` | Session history — too large, app-managed |
| `~/.local/state/opencode` | Runtime state — app-managed |
| The binary itself | Pre-built, do not modify |

---

## 12. Quick Fix Reference (2-Minute Recovery)

### OpenCode_Ubuntu.bat fails with "No such file or directory"
```bash
# Check the .bat — it was calling wrong path
cat /mnt/c/Users/itsji/OneDrive/Desktop/OpenCode_Ubuntu.bat
# Must call: wsl bash -c 'source .env; ...; opencode --auto'
# NOT: wsl bash -c 'cd /mnt/c/Users/itsji/ARBITR8DER && opencode --auto'
```

### Shortcuts don't appear on desktop
```bash
# Windows uses OneDrive\Desktop as Desktop (registry redirect)
cp local-files/Desktop-Shortcuts/*.lnk local-files/Desktop-Shortcuts/*.bat "/mnt/c/Users/itsji/OneDrive/Desktop/"
```

### OpenCode starts but can't find API key
```bash
# Check ARBITR8DER/.env exists and has OPENCODE_API_KEY
cat /mnt/c/Users/itsji/ARBITR8DER/.env
```

### Run full launcher test
```powershell
pwsh -File tests/test_launcher_scripts.ps1
```

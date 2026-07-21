# howtobuildOpenCode — Rebuild and Reconnect Guide

> This document tells any AI exactly how to install, configure, and reconnect
> OpenCode on this machine. OpenCode is a pre-built binary — there is no source
> to compile. The "build" is installing the binary and wiring the config.

---

## 1. System Layout

### Canonical Locations

```
C:\Users\itsji\ARBITR8DER                   <- main workspace
C:\Users\itsji\ARBITR8DER\agents\opencode\  <- agent desk (pointers + session history)
C:\Users\itsji\ARBITR8DER\agents\agents.md  <- one brain for all agents
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

Minimal config:
```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "permission": "allow"
}
```

`"permission": "allow"` skips all permission prompts. This is the equivalent
of Claude's `--dangerously-skip-permissions`. Local-only, trusted environment.

### 4.2 Environment Variables

| Variable | Purpose | Where Set |
|----------|---------|-----------|
| `OPENCODE_API_KEY` | API key for the OpenAI-compatible provider | Launcher (.bat / .sh) or shell |
| `OPENAI_MODEL` | Model name (e.g., `big-pickle`) | Launcher or shell |
| `CLAUDE_CODE_USE_OPENAI=1` | Enable OpenAI-compatible bridge | Launcher or shell |

These are set by the launcher scripts, not stored in the config file.

---

## 5. Launch Chain

### Windows

```
OneDrive/Desktop/OpenCode_Ubuntu.bat
  → cmd /k "wsl bash -c 'cd ARBITR8DER/agents && opencode' %*"
  → Launches opencode from WSL inside the agents directory
```

### Linux / WSL

```
~/Desktop/OpenCode_Ubuntu
  → Sets OPENCODE_API_KEY, OPENAI_MODEL
  → cd /mnt/c/Users/itsji/ARBITR8DER/agents
  → exec /home/itsjimjimsalabim/.opencode/bin/opencode "$@"
```

### WSL Companion Launcher

```
ARBITR8DER/agents/opencode/launchers/launch-opencode.sh
  → Same as above but callable from anywhere
```

---

## 6. Reconnection Checklist

| Step | Command | Expected |
|------|---------|----------|
| 1 | `node --version` | v22+ |
| 2 | `npm --version` | Latest |
| 3 | `/home/itsjimjimsalabim/.opencode/bin/opencode --version` | Prints version |
| 4 | `cat ~/.config/opencode/opencode.jsonc` | Shows `"permission": "allow"` |
| 5 | `echo $OPENCODE_API_KEY` | Set (or set in shell) |

---

## 7. First Agent Workflow

When a fresh agent starts:

1. Read `C:\Users\itsji\ARBITR8DER\agents\agents.md` — the one brain
2. Read `agents/opencode/README.md` — pointers to session history
3. Run the reconnection checklist above
4. Launch via the bat file or Desktop launcher

---

## 8. Debug Tips

### Binary won't run
```bash
# Check if it's executable
ls -la /home/itsjimjimsalabim/.opencode/bin/opencode
chmod +x /home/itsjimjimsalabim/.opencode/bin/opencode

# Check architecture (must match your system)
file /home/itsjimjimsalabim/.opencode/bin/opencode
# Should be: ELF 64-bit LSB executable, x86-64
```

### API key not being picked up
```bash
# Make sure the env var is set before launching
export OPENCODE_API_KEY="your-key-here"
echo $OPENCODE_API_KEY  # verify it's set

# Or check the bat/launcher files for hardcoded values
```

### Config not loading
```bash
# Verify the config file exists and is valid JSONC
cat ~/.config/opencode/opencode.jsonc

# Windows side
cat /mnt/c/Users/itsji/.config/opencode/opencode.jsonc
```

### Permission denied on launch
```bash
# The binary needs execute permission
chmod +x /home/itsjimjimsalabim/.opencode/bin/opencode
```

### WSL can't find the binary
```bash
# Use the full path in the bat file, not a relative path
# Wrong: opencode
# Right: /home/itsjimjimsalabim/.opencode/bin/opencode
```

---

## 9. Customizations

These are OpenCode-specific tweaks applied on top of the default install.

### Permission Mode

`"permission": "allow"` in `opencode.jsonc` — equivalent to
`--dangerously-skip-permissions`. All tools (Bash, Read, Write, Edit, Glob, Grep)
run without prompts. This is intentional for a trusted local-only environment.

### Model Selection

The model is set via `OPENAI_MODEL` env var, not in the config file. Default:
`big-pickle`. Change in the launcher scripts or shell profile.

### Provider Routing

`CLAUDE_CODE_USE_OPENAI=1` enables the OpenAI-compatible bridge. The provider
is `opencode` (OpenAI-compatible endpoint). This routes through the OpenCode API
rather than directly to OpenAI or Anthropic.

### Session Database

OpenCode stores all chat history in `~/.local/share/opencode/opencode.db`.
On this machine it is 591MB. This is NOT in the repo — it is app-managed data.
Do not move or delete unless you want to lose all session history.

### What NOT to Touch

| Item | Why |
|------|-----|
| `~/.local/share/opencode/opencode.db` | Session history — too large, app-managed |
| `~/.local/state/opencode` | Runtime state — app-managed |
| The binary itself | Pre-built, do not modify |

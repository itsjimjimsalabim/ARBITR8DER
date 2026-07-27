# Tools Database — ARBITR8DER System
**Last Updated:** 2026-07-21 (full audit)
**Machine:** ZEN-LAPTOP (AMD Ryzen AI 9 465, 32GB RAM, 1TB SSD)
**OS:** Windows 11 + WSL2 Ubuntu 24.04.4
**User:** itsjimjimsalabim

---

## How to Read This Document

- **Active** = installed, working, in PATH
- **Broken** = installed but not working (missing dependency, wrong PATH, etc.)
- **Dead** = no longer on the system or directory deleted
- **Available** = can be installed quickly
- Each tool lists: what it is, where it lives, what version, what it's for

---

## AI Coding Agents

| Tool | Status | Windows | WSL | Version | Purpose | Config Location |
|------|--------|---------|-----|---------|---------|----------------|
| **OpenCode** | Active | `C:\Users\itsji\.bun\bin\opencode.exe` | `~/.opencode/bin/opencode` | **1.18.4** | Primary coding agent | `ARBITR8DER/opencode.json` + `~/.config/opencode/` |
| **OpenClaude** | Active | `C:\Users\itsji\.openclaude\dist\cli.mjs` | `~/bin/claude` (wrapper) | **0.25.0** | Coding agent (Claude-compatible CLI) | `.openclaude/settings.local.json` + `.openclaude-profile.json` |
| **Kilo** | Active | N/A | `~/.kilo/bin/kilo` | **7.4.11** | Same binary as OpenCode, different brand | `~/.config/opencode/` (shared) |
| **Copilot CLI** | Active | `C:\Program Files\GitHub CLI\` | N/A | Latest | GitHub Copilot in terminal | GitHub auth |
| **Codex** | Active | `C:\Users\itsji\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe` | `~/.local/bin/codex` | **0.143.0** | OpenAI Codex CLI | Needs API key |
| **GPT-CLI** | Dead | N/A | Not installed | — | OpenAI GPT in terminal | — |
| **Ollama** | Dead | Not installed | Not installed | — | Local LLMs | — |

### AI Desktop Apps

| App | Status | Location | Purpose |
|-----|--------|----------|---------|
| Claude Desktop | Installed | `AppData\Local\Packages\Claude_pzs8sxrjxfjjc` | Anthropic Claude GUI |
| GitHub Copilot | Installed | VS Code extension | Code suggestions |
| Agy | Installed | `AppData\Local\Agy` | Unknown |
| Copilot (Windows) | Built-in | Windows 11 | System AI |
| Grok | Dead | Not installed | — |
| Kimi | Dead | Not installed | — |

---

## Runtimes & Languages

| Tool | Windows | WSL | Version | Purpose |
|------|---------|-----|---------|---------|
| **Node.js** | `C:\Program Files\nodejs\` | nvm (`~/.nvm/`) | **v24.18.0** | JS runtime, OpenClaude |
| **npm** | Included w/ Node | nvm | **11.16.0** | Package manager |
| **Bun** | `C:\Users\itsji\.bun\bin\bun.exe` | `~/.bun/bin/bun` | **1.3.14** | Fast JS runtime, builds, scripts |
| **Python** | `C:\Users\itsji\AppData\Local\Programs\Python\Python312\python.exe` | `/usr/bin/python3` | **3.12.4** (Win) / **3.12.3** (WSL) | ARBITR8DER, scripts |
| **pip** | `C:\Users\itsji\AppData\Local\Programs\Python\Python312\Scripts\pip.exe` | `/usr/bin/pip3` | **24.0** | Python packages |
| **nvm** | N/A | `~/.nvm/` | **0.39.7** | Node version manager |
| **GCC** | N/A | `/usr/bin/gcc` | **13.3.0** | C compiler |
| **Make** | N/A | `/usr/bin/make` | **4.3** | Build tool |

---

## Package Managers

| Manager | Windows | WSL | Status |
|---------|---------|-----|--------|
| **npm** | ✔ | ✔ | Active |
| **bun** | ✔ | ✔ | Active |
| **pip** | ✔ | ✔ | Active |
| **winget** | ✔ | N/A | Windows packages |
| **apt** | N/A | ✔ | System packages |
| **pipx** | Missing | Missing | Not installed |

---

## Dev Tools

| Tool | Windows | WSL | Version | Purpose |
|------|---------|-----|---------|---------|
| **Git** | `C:\Program Files\Git\` | `/usr/bin/git` | **2.55.0** (Win) / **2.43.0** (WSL) | Version control |
| **GitHub CLI** | `C:\Program Files\GitHub CLI\` | N/A | **2.96.0** | PRs, issues, repos |
| **VS Code** | Installed | N/A | Latest | Editor |
| **Windows Terminal** | Installed | N/A | Latest | Terminal host |
| **PowerShell** | Built-in | N/A | 5.1 | Windows shell |
| **tmux** | N/A | `/usr/bin/tmux` | **3.4** | Terminal multiplexer |
| **vim** | N/A | `/usr/bin/vim` | **9.1** | Text editor |
| **nano** | N/A | `/usr/bin/nano` | **7.2** | Text editor |
| **curl** | N/A | `/usr/bin/curl` | **8.5.0** | HTTP client |
| **wget** | N/A | `/usr/bin/wget` | **1.21.4** | HTTP downloader |
| **make** | N/A | `/usr/bin/make` | **4.3** | Build automation |
| **gcc** | N/A | `/usr/bin/gcc` | **13.3.0** | C compiler |

### Missing Dev Tools (WSL — can be installed)

| Tool | Purpose | Install Command |
|------|---------|-----------------|
| ruff | Python linter | `pip install ruff` |
| uv | Fast Python installer | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| jq | JSON processor | `sudo apt install jq` |
| ripgrep | Fast grep | `sudo apt install ripgrep` |
| fd | Fast find | `sudo apt install fd-find` |
| fzf | Fuzzy finder | `sudo apt install fzf` |
| bat | Cat with colors | `sudo apt install bat` |
| htop | Process monitor | `sudo apt install htop` |
| tree | Directory tree | `sudo apt install tree` |
| gh (GitHub CLI) | PRs from WSL | `sudo apt install gh` or `curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \| sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg` |

---

## ARBITR8DER Project

| Component | Status | Location |
|-----------|--------|----------|
| **Trading studio** | Active | `C:\Users\itsji\ARBITR8DER\` |
| **arbitr8der package** | v2.0.0 editable | Installed in Windows Python |
| **Vessel state machine** | Active | `src/arbitr8der/` |
| **Kalshi integration** | Active | REST + WebSocket |
| **Binance feed** | Fixed | WebSocket streaming |
| **Coinbase feed** | Active | WebSocket |
| **Polymarket feed** | Active | REST + WS |
| **Coingecko feed** | Active | REST API |
| **Paper trading** | Active | `AR8_WALLET_MODE=PAPER` |
| **Live trading** | Armed (disabled) | Needs `AR8_WALLET_MODE=LIVE` |

### ARBITR8DER Python Dependencies (installed)

| Package | Version | Purpose |
|---------|---------|---------|
| arbitr8der | 2.0.0 | Trading studio |
| typer | 0.27.0 | CLI framework |
| pydantic | 2.13.4 | Data validation |
| pydantic-settings | 2.14.2 | Config management |
| httpx | 0.28.1 | HTTP client |
| websockets | 13.1 | WebSocket client |
| aiosqlite | 0.22.1 | Async SQLite |
| orjson | 3.11.9 | Fast JSON |
| python-dotenv | 1.2.2 | .env loading |
| cryptography | 43.0.3 | Crypto ops |

### ARBITR8DER Config Files

| File | Purpose |
|------|---------|
| `.env` | Wallet mode, API keys (Kalshi, OpenCode) |
| `opencode.json` | OpenCode auto-approve config |
| `agents/agents.md` | Single brain for all agents |
| `agents/claude/` | Claude desk |
| `agents/openclaude/` | OpenClaude desk (launchers, howto) |
| `agents/opencode/` | OpenCode desk |
| `agents/codex/` | Codex desk |
| `agents/gemini/` | Gemini desk |
| `agents/kilo/` | Kilo desk |

---

## Data Feeds & APIs

| Feed | Status | Type | Rate Limit |
|------|--------|------|------------|
| **Kalshi** | Active | REST + WebSocket | API-limited |
| **Binance** | Active | WebSocket | 5 connections |
| **Coinbase** | Active | WebSocket | — |
| **Polymarket** | Active | REST + WS | — |
| **Coingecko** | Active | REST | 10-50 req/min |

---

## OpenCode Providers (WSL)

Configured in `~/.config/opencode/opencode.jsonc`:

| Provider | Models | API Key |
|----------|--------|---------|
| **NVIDIA NIM** | Nemotron Ultra 253B, Super 49B v1.5, Nano 9B v2, Nemotron 3 Ultra 550B, Nemotron 3 Super 120B, DeepSeek V4 Pro/Flash, Qwen3 Coder 480B, Qwen3.5 122B, Qwen3 Next 80B, MiniMax M2.7, GLM 5.2/5.1, Kimi K2 Thinking/Instruct, Llama 3.1 405B, Llama 3.3 70B, GPT-OSS 120B, Mistral Nemotron, Nemotron Nano 12B VL | `<redacted-nvidia-api-key>...` |
| **OpenCode Zen** | big-pickle (default) | `sk-sSGtBd...` |
| **Ollama** | localhost:11434 (no models downloaded) | — |

---

## OpenCode Config Summary

| Setting | Value | Effect |
|---------|-------|--------|
| `permission` | `"allow"` | Auto-approve all tool calls |
| `agent.build.steps` | 200 | More steps before limits |
| `agent.plan.steps` | 200 | Same for plan mode |
| `compaction.auto` | `true` | Auto-compact when context full |
| `compaction.tail_turns` | 20 | Keep 20 turns before compacting |

---

## OpenClaude Config Summary

| Setting | Value | Effect |
|---------|-------|--------|
| Profile | `opencode` | Uses OpenCode Zen API |
| `OPENAI_BASE_URL` | `https://opencode.ai/zen/v1` | OpenCode Zen endpoint |
| `OPENAI_MODEL` | `big-pickle` | Default model |
| `CLAUDE_CODE_USE_OPENAI` | `1` | Forces OpenAI mode (not Anthropic) |
| Big Pickle Context | 256,000 tokens | 2x more context before compaction |
| Big Pickle Max Output | 64,000 tokens | No truncation on complex responses |
| Auto-compact at | 85% | More room before summarizing |
| Cooldown on failure | 120s (2min) | Faster retry after compact failures |

---

## Desktop Shortcuts

All shortcuts live in: `C:\Users\itsji\local-files\Desktop-Shortcuts\`
Windows also syncs them to: `C:\Users\itsji\OneDrive\Desktop\` (registry redirect)

| Shortcut | Platform | Target | Status |
|----------|----------|--------|--------|
| `Claude Windows.lnk` | Windows | `C:\Users\itsji\bin\claude.bat` → native Node | ✅ Working |
| `OpenClaude_Ubuntu.bat` | Windows→WSL | `wsl -e bash -ic claude` | ✅ Working |
| `OpenCode at Home.lnk` | Windows | `wt.exe` → `opencode` | ✅ Working |
| `OpenCode_Ubuntu.bat` | Windows→WSL | `wsl bash -c ... opencode --auto` | ✅ Working |
| `Start Codex Full Access.lnk` | Windows | `C:\Users\itsji\agents\launchers\Start-Codex-Full-Access.bat` → `codex.exe` | ✅ Working |
| `ARBITR8DER - Shortcut.lnk` | Windows | Opens ARBITR8DER folder | ✅ Working |
| `agents - Shortcut.lnk` | Windows | Opens agents folder | ✅ Working |

---

## WSL Launcher Scripts

| Script | Location | Purpose |
|--------|----------|---------|
| `~/bin/claude` | `/home/itsjimjimsalabim/bin/claude` | Big Pickle tuned Claude launcher |
| `launch-opencode.sh` | `agents/openclaude/launchers/launch-opencode.sh` | OpenCode launcher with .env |

---

## Known Gotchas

| Gotcha | Fix |
|--------|-----|
| `~/.bun/bin/claude` shadows `~/bin/claude` | Delete `~/.bun/bin/claude` — bun creates stale scripts |
| OneDrive Desktop redirect stuck | Windows treats `OneDrive\Desktop` as Desktop even after OneDrive removal |
| `pip install -e .` fails | Needs `pip install setuptools` first, then `pip install -e .` |
| `agents/claude/launchers/` is empty | Real launchers are at `C:\Users\itsji\bin\claude.bat` and `~/bin/claude` |

---

## Disk Usage

| Directory | Size | Notes |
|-----------|------|-------|
| `~/.nvm` (WSL) | 653 MB | Node versions |
| `~/.bun` (WSL) | 394 MB | Bun runtime |
| `~/.opencode` (WSL) | 223 MB | OpenCode binary + data |
| `~/.local` (WSL) | 100 MB | Python packages |
| `.openclaude` (Windows) | 450 MB | Built CLI + sessions + .env |
| `ARBITR8DER` | 3.4 MB | Trading studio |
| **Total** | **~1.8 GB** | |

---

## End of Database


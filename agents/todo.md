# ARBITR8DER Active Todo

**Canonical plan:** `agents/trading_studio_build_plan.md`
**Onboarding workflow:** `agents/onboarding_workflow.md` (read this first if new)
**Current implementation state:** Phase 8 — Prediction System (8a-8l complete, retraining loop closed, auto-trader wired)

## Rules For The Next Implementing AI

- All executable trading software belongs under `trading_studio/`, including `src/`, tests, scripts, runtime paths, package metadata, and a future UI.
- `agents/` contains shared context and planning only. Do not put runnable trading helpers there.
- Do not restore or copy the deleted root package or code from historical repositories. Use history only for lessons and test cases.
- Start each process in `Full_Stop` and PAPER mode. No task in this backlog authorizes a live order.
- Before changing code, verify the current worktree and preserve unrelated user changes.
- There is exactly ONE `.env`: `ARBITR8DER/.env` at the repo root. `trading_studio/.env` is gone. `TradingStudioSettings` loads the root `.env` by absolute path resolved from the package location, not CWD. Do not recreate `trading_studio/.env`.
- `trading_studio/runtime/` is the only runtime directory. The empty `runtime/` at the repo root is vestigial; delete it if it reappears, do not write to it.
- `.qodo/` is auto-created by the VSCode Qodo extension. It is gitignored. Delete on sight, never commit.
- File/variable names: at least 4 self-documenting words. Persona is "Paulie" — cold, calculating coder.
- **Core Philosophy: High-Speed AI-First Architecture**: Build exclusively for AI agent usability and execution speed. NO UI code or decorative graphics in `trading_studio/` (yet). Keep all outputs as compact plain-text or clean structured data tables optimized for machine parsing and token efficiency.

---

## Vibecoding Audit & Cleanup (2026-07-24) ← CURRENT

We built a lot vibecoding. We now have to audit, review, and clean. Goals: stop the env/runtime/tooling bugs that come from duplicate and stale paths, get the repo into a single sane shape so the next AI's onboarding is deterministic.

- **One .env, one runtime, one trading_studio.** Duplicate paths breed bugs.
- **Launch 3 subagents to research/vote** on architecture questions, per agents.md.


## Completed

- [x] Read the shared requirements, development log, current backlog, and both competing rebuild plans.
- [x] Audit the active worktree and Git history, plus the owned GitHub repositories relevant to ARBITR8DER.
- [x] Consolidate the active rebuild direction into `agents/trading_studio_build_plan.md`.
- [x] Remove the two superseded active rebuild plans and replace the studio's plan-like README with a directory map.
- [x] Phase 0: Boundary And Security — git status, trading_studio/ project scaffold, pyproject.toml, .env placeholders, kalshi key moved to .gitignore, tests directory, runtime paths
- [x] Phase 1: Foundation — VesselStateMachine, TradingStudioSettings, structured logging, path resolver, lease file lock, HotSnapshot/Asset/SourceHealthStatus contracts, JSONL hot snapshot merger
- [x] Phase 2: Data Contracts & Connectors — BinanceCandle/BinancePriceObservation/BinanceBookTicker, CoinbasePriceTick, PolymarketSentimentObservation, CoinGeckoMacroObservation, KalshiOrderbookDelta, all 5 data source modules wired
- [x] Phase 3: Real Data Connectors — all 5 sources running with real connections, candle backfill, market discovery, source health monitoring
- [x] Phase 4: Battery Mode — IngestionOrchestrator, interactive REPL with snapshot/health/markets/predict commands, JSON+human formatting
- [x] Phase 5: Forecast Evidence — BaselinePredictionModel, PredictionRecord, PredictionScorer, feature extraction engine, candle attribute contract fixes
- [x] Phase 6: Operator Workflow — StructuredTradeJournal, SessionArchive, ScorecardGenerator, REPL integration (observe/note/list/show/scorecard/archive)
- [x] Phase 7: PAPER Order Lifecycle — risk controls, paper adapter, reconciliation, positions/buy/sell/pending/cancel commands
- [x] Phase 8: Prediction System — 8a-8l complete (retraining loop closed, auto-trader wired)
- [ ] Phase 9: ARMED Transition — live Kalshi execution path

## Phase 7: PAPER Order Lifecycle ✅ DONE

Risk controls, paper venue adapter, reconciliation module, and REPL trading commands.

### 7a. Risk Controls ✅
- [x] Vessel state check (Full_Forward required for trades)
- [x] Wallet mode check (paper mode enforced)
- [x] Minimum 2-contract rule
- [x] Balance and exposure limits
- [x] Max positions per asset
- [x] Session and daily loss caps
- [x] Trade cooldown between orders
- [x] Stale book block (reject if market data older than 5 minutes)
- [x] Emergency stop mechanism

### 7b. PAPER Venue Adapter ✅
- [x] Persistent wallet balance (SQLite-backed)
- [x] Fill simulation using real market prices
- [x] Fee model matching Kalshi structure
- [x] Inventory tracking (positions, contracts, avg price)
- [x] Order intent → fill lifecycle
- [x] Settlement on market resolution
- [x] Limit order fill at midpoint (better price)
- [x] Real balance sync via Kalshi API

### 7c. Reconciliation ✅
- [x] Full order audit trail
- [x] Intent → validation → fill → settlement chain
- [x] Journal integration for trade reasoning
- [x] Discrepancy detection (flags stuck orders)

### 7d. REPL Commands ✅
- [x] `positions` — show current open positions with PnL
- [x] `buy ASSET SIDE N` — place market buy (min 2 contracts)
- [x] `buy ASSET SIDE N LIMIT` — place limit order at specified cents
- [x] `sell ASSET TICKER` — close position with settlement
- [x] `pending` — show pending limit orders
- [x] `cancel TICKER` — cancel pending limit order
- [x] `wallet` — show balance and PnL
- [x] `risk` — show risk status and limits

### 7e. Balance Fetcher ✅
- [x] `scripts/fetch_real_balance.py` — fetches real Kalshi balance
- [x] `--set-balance` flag updates paper wallet to match
- [x] Default balance: $17.00 (your real Kalshi balance)

## Phase 8: Prediction System ← COMPLETE

Dual-horizon prediction models for BTC/ETH 15-minute markets.

### 8a. Persistent Data Battery ✅
- [x] Candle collection battery: Binance + Coinbase REST backfill and polling
- [x] 72h of 1m candles (4320 max), polling every 60s
- [x] Circuit breaker with 5-error backoff
- [x] SQLite-backed candle persistence store
- [x] Schema migrations for candles, outcomes, features, model_runs

### 8b. Feature Engineering ✅
- [x] Macro features (29): regime, RSI, Bollinger, ATR, streaks, volume, time
- [x] Micro features (12): 1m/5m returns, momentum, volume spike, book imbalance
- [x] Cross-asset features (7): BTC↔ETH correlation, lead-lag, regime comparison
- [x] Regime detection: trending_up, trending_down, ranging, volatile

### 8c. Macro Prediction Model ✅
- [x] FrequencyLookupModel: groups by regime/streak/hour/RSI, counts outcomes
- [x] LightGBMClassifier: gradient boosted trees (installed: lightgbm 4.7.0)
- [x] MacroEnsemble: 30% freq + 70% lgbm weighted average

### 8d. Micro Prediction Model ✅
- [x] MomentumLookupModel: groups by return/momentum/volume/range buckets
- [x] LogisticRegressionClassifier: regularized LR with gradient descent
- [x] MicroEnsemble: 40% momentum + 60% lr weighted average

### 8e. Auto-Scoring Engine ✅
- [x] Match predictions to outcomes via (asset, window_open) join
- [x] Determine outcomes from 1m candles in 15m windows
- [x] Model scorecard: accuracy, Brier score, log loss, PnL
- [x] Dashboard: all models, per-asset, aggregate
- [x] Continuous scoring loop (30s interval)
- [x] Verified: 39 adversarial probes passed

### 8f. Battery + Scoring Integration ✅
- [x] Wire CandleCollectionBattery into IngestionOrchestrator for 24/7 operation
- [x] Wire AutoScoringEngine into orchestrator alongside battery
- [x] Run predictions every 15 minutes before market windows (scoring loop every 15s)
- [x] Score predictions when outcomes resolve (continuous auto-scoring)
- [x] REPL commands: predict (existing), accuracy (new), features (new)
- [x] Created ModelRunRecordStore — dedicated model_runs table CRUD
- [x] Fixed shared DB: orchestrator uses single prediction.db for candles + model_runs + outcomes JOIN
- [x] Added CandlePersistenceStore.initialize() safety-net schema creation
- [x] Fixed AutoScoringEngine constructor to accept ModelRunRecordStore
- [x] Fixed settings validator: wallet_mode/trading_mode normalized to lowercase

### 8g. Backtest Engine ✅
- [x] Walk-forward backtesting on historical candle data
- [x] Train on N periods, test on next period, slide forward
- [x] Aggregate metrics: Sharpe ratio, max drawdown, win rate, Brier score, profit factor
- [x] Compare macro vs micro vs ensemble performance
- [x] REPL command: backtest (run backtest on historical data with options)

### 8h. Kalshi Pricing + Model Comparison ✅
- [x] Real Kalshi contract PnL (YES/NO contracts, entry cost = probability * 100)
- [x] Model comparison mode: macro vs micro side-by-side with winner declaration
- [x] Feature importance tracking across retraining windows (LightGBM gain)
- [x] REPL comparison display: `backtest --model both`

### 8i. Settlement Watcher + Feature Importance ✅
- [x] SettlementWatcher: polls Kalshi REST for settled markets, records outcomes
- [x] Feature importance analyzer: CV stability, rankings, `compare_models()`
- [x] Wired SettlementWatcher into orchestrator background tasks
- [x] REPL `settlement` command: watcher status + recent outcomes table
- [x] 22 unit tests passing

### 8j. Live Retraining Feedback Loop ✅
- [x] `retrain_models()` on AutoScoringEngine: fetches scored predictions with features, retrains MacroEnsemble + MicroEnsemble per asset
- [x] Periodic retraining in score loop (every ~15 min / 30 cycles)
- [x] Model accessors: `get_macro_model(asset)`, `get_micro_model(asset)`
- [x] `_cmd_predict` records predictions to model_runs with features_json and window_open
- [x] REPL `retrain` command: manual retrain trigger + results display
- [x] 5 new unit tests for retraining (sufficient data, model accessors, insufficient data, empty DB, timestamp tracking)

### 8k. Predict Command ML Model Integration ✅
- [x] `aggregate_1m_to_15m_candles()` pure function: aggregates 1m candles to 15m OHLCV
- [x] `_cmd_predict --model` flag: baseline (default), macro, micro, auto
- [x] Macro/micro predict path: fetch 1m candles → aggregate → compute macro features → retrained model → output
- [x] Auto mode: uses retrained model if available, falls back to baseline
- [x] Records to model_runs with correct model name (macro_ensemble / micro_ensemble / baseline_v1)
- [x] 5 new unit tests for aggregation (empty, single window, two windows, sparse skip, sort order)

## Migrate to Linux (PCLinuxOS)

**Target OS:** PCLinuxOS (rolling-release RPM-based distro)
**Reason:** Get off Windows/OneDrive sync hell. Pure Linux native execution. No more WSL geo-block
on Binance WS. No more OneDrive lock files. Direct hardware access for Ollama (AMD Ryzen AI NPU
potential). Faster I/O, deterministic paths, no registry junk.

> ⚠️ ANOTHER AI IS CURRENTLY CODING ON THE `arbitrator` BRANCH — do not touch code, only docs and
> planning until that work is merged or confirmed paused. This is a research + documentation task.

---

### PRE-MIGRATION GATE 1: Repo Must Be Fully Committed and Pushed

The repo is currently **12 commits ahead of origin** and has a push-blocked history. Fix this first.
The Linux machine will clone from GitHub — if it's not on GitHub, it's gone.

#### 1a. Resolve the PAT-in-History Push Block
- [ ] Open the GitHub secret-scanning URL for commit `ac2e110` (check email/GitHub notification).
  Bypass option: go to `https://github.com/itsjimjimsalabim/ARBITR8DER/security` → Secret scanning.
- [ ] **Option A (easiest if GitHub grants bypass):** Click "Allow secret" in GitHub secret scanning.
  Then `git push origin main` normally.
- [ ] **Option B (history rewrite — nuclear):** If bypass is denied:
  - `git log --all --oneline | grep ac2e110` — confirm the commit
  - `git rebase -i ac2e110~1` — squash or drop the offending commit
  - Force push: `git push origin main --force-with-lease`
  - ⚠️ Coordinate with any active agent branches before force-pushing
- [ ] Verify push: `gh repo view itsjimjimsalabim/ARBITR8DER --web` — confirm latest commit shows on GitHub

#### 1b. Commit All Pending Local Changes
- [ ] `git status` — confirm which files are dirty (currently: `agents/todo.md` modified)
- [ ] `git add agents/todo.md` and commit with descriptive message
- [ ] After push block is resolved: `git push origin main`
- [ ] Confirm: `git log --oneline origin/main -5` matches `git log --oneline -5`
- [ ] Run full test suite one last time before migration: `python -m pytest trading_studio/tests/ -v -q`

#### 1c. Tag the Pre-Migration Snapshot
- [ ] `git tag pre-linux-migration-2026-07-27` — snapshot tag before the move
- [ ] `git push origin pre-linux-migration-2026-07-27` — push the tag to GitHub
- [ ] Verify: `gh release list` or `gh api repos/itsjimjimsalabim/ARBITR8DER/tags`

---

### PRE-MIGRATION GATE 2: Supporting Docs Audit — Bring Everything Up to Date

Every agent needs to find the right answer on the new Linux machine. All docs must reflect reality
*before* the move. If a doc lies, the next AI on Linux will be burned.

#### 2a. `agents/agents.md` — Machine Tool Inventory Update
- [ ] Update the "Local Machine Tool Inventory" table with verified current versions:
  - `git --version` (currently 2.55.0.windows.2 → will change on Linux, needs placeholder)
  - `gh --version` (currently 2.96.0)
  - `python --version` (currently 3.12.4 — confirm Python 3.12 available in PCLinuxOS repos)
  - `node --version` (currently v24.18.0)
  - `bun --version` (currently 1.3.14)
  - `ollama --version` (currently 0.32.3)
- [ ] Add note: "On PCLinuxOS, `python3` IS the alias — `python` may not be set. Use `python3`
  or create an alias."
- [ ] Add note: "On PCLinuxOS, `git` path is typically `/usr/bin/git`. Verify with `which git`."
- [ ] Add Linux path section: document that `/mnt/c/Users/itsji/` no longer applies. Repo lives
  at `~/ARBITR8DER` or `/home/itsji/ARBITR8DER` on Linux.
- [ ] Remove or archive all WSL-specific paths (e.g. `/mnt/c/Users/itsji/...` references)

#### 2b. `agents/onboarding_workflow.md` — Linux-First Onboarding Update
- [ ] Update §0 Skeptical Pre-Flight: add Linux-native path verification commands
- [ ] Update §1 Repo Layout: replace all Windows paths with Linux-native equivalents
- [ ] Update §3 Install + Verify: confirm `pip3` vs `pip` alias behavior on PCLinuxOS
- [ ] Update §6 Run a Session: replace `cd /mnt/c/...` with `cd ~/ARBITR8DER`
- [ ] Update §8 Test Suite: update paths
- [ ] Update §10 Known Issues: add new Linux-specific known issues (RPM package names, etc.)
- [ ] Add §13 PCLinuxOS-Specific Notes section (new): systemd services, pclinuxos-repos, synaptic

#### 2c. `agents/qwen_local_model_ops_guide.md` — Coin Model Re-Download Section (NEW)
See Gate 3 below — this file needs a full new section added.

#### 2d. `agents/github_connectivity.md` — Linux SSH Setup
- [ ] Add Linux SSH keygen instructions for PCLinuxOS
- [ ] Document: generate fresh SSH key on Linux, add `.pub` to GitHub account SSH keys
- [ ] Commands to add:
  ```bash
  ssh-keygen -t ed25519 -C "arbitr8der-pclinuxos" -f ~/.ssh/arbitr8der_linux
  cat ~/.ssh/arbitr8der_linux.pub   # copy this to GitHub → Settings → SSH Keys
  ssh -T git@github.com             # verify: "Hi itsjimjimsalabim! You've authenticated..."
  git remote set-url origin git@github.com:itsjimjimsalabim/ARBITR8DER.git
  ```
- [ ] Document: if staying HTTPS, `gh auth login` on PCLinuxOS (confirm gh CLI is in rpm repos
  or install from binary release)

#### 2e. `agents/dev_log.md` — Add Linux Migration Entry
- [ ] Write a new dev log entry (dated 2026-07-27 or when migration happens) covering:
  - Why we migrated (OneDrive sync hell, WSL geo-block, performance)
  - Target: PCLinuxOS rolling release
  - What changed: paths, package manager (rpm/apt → pclinuxos), Python alias, etc.
  - First verified working state on Linux

#### 2f. `trading_studio/readme.md` — Path Update
- [ ] Replace all WSL/Windows path references with Linux-native paths
- [ ] Add note: `arb` CLI is at `~/.local/bin/arb` after `pip install -e ./trading_studio`

#### 2g. `CLAUDE.md` — Linux-Aware Pointer Update
- [ ] Verify CLAUDE.md still correctly points to `agents/agents.md`
- [ ] Add note about Linux path changes

---

### PRE-MIGRATION GATE 3: Coin Model (Ollama) Re-Download Docs

We have two Ollama coin models — `qwen3:4b-instruct` and `qwen3-coder:30b`. These are **20.5 GB
total on disk** and NOT in the repo. The new Linux machine needs exact re-download instructions.
A new section must be added to `agents/qwen_local_model_ops_guide.md`.

#### 3a. Add "Re-Download on a Fresh Machine" Section to Ollama Ops Guide
- [ ] Edit `agents/qwen_local_model_ops_guide.md` — add section: **"How To Re-Download the Coin
  Models on a New Machine"**
- [ ] Include: Ollama install command for PCLinuxOS (curl install script or RPM package)
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh    # Linux universal installer
  # OR for PCLinuxOS RPM:
  # Check: https://ollama.com/download/linux — look for RPM or use the install script
  ```
- [ ] Include: model pull commands with expected sizes:
  ```bash
  ollama pull qwen3:4b-instruct      # ~2.5 GB — small manager/router model
  ollama pull qwen3-coder:30b        # ~18 GB  — large on-demand coding worker
  ```
- [ ] Include: verification commands after pull:
  ```bash
  ollama list                         # confirm both models appear
  ollama run qwen3:4b-instruct "say hello"    # quick smoke test
  ollama ps                           # confirm model is loaded
  ```
- [ ] Include: expected download time estimate (dependent on internet speed; 18 GB on 100Mbps ≈
  25 min)
- [ ] Include: disk space warning — models live at `~/.ollama/models/` on Linux, need 25 GB free
- [ ] Include: confirm Ollama service is running:
  ```bash
  systemctl status ollama        # on systemd Linux (PCLinuxOS)
  sudo systemctl enable ollama   # auto-start on boot
  sudo systemctl start ollama
  ```
- [ ] Include: progress monitoring commands (same as Windows section, adapted for Linux):
  ```bash
  ollama list
  ollama ps
  ls ~/.ollama/models/blobs/ | grep partial    # check for in-progress downloads
  ```

#### 3b. Verify Ollama Blobs on Current Windows Machine (Pre-Migration Backup Check)
- [ ] Run `Get-ChildItem "$env:USERPROFILE\.ollama\models\manifests" -Recurse` — document exact
  model names and tags currently installed
- [ ] Current confirmed installs (verified 2026-07-27):
  - `qwen3-coder:30b` (manifest: registry.ollama.ai/library/qwen3-coder/30b, ~18 GB)
  - `qwen3:4b-instruct` (manifest: registry.ollama.ai/library/qwen3/4b-instruct, ~2.5 GB)
- [ ] Confirm both models respond before migrating:
  ```powershell
  # In PowerShell (if ollama server running):
  Invoke-RestMethod -Uri "http://localhost:11434/api/tags"
  ```
- [ ] Note: Ollama model blobs cannot simply be copied folder-to-folder across OS boundaries
  reliably — always re-pull fresh on the new Linux machine

#### 3c. Update `agents/agents.md` — Ollama Model Table
- [ ] Confirm the "Installed local Ollama models" table is correct and will remain valid on Linux
- [ ] Add a note: "On PCLinuxOS, re-download these after `ollama` service install — see
  `agents/qwen_local_model_ops_guide.md` §Re-Download on a Fresh Machine"

---

### PRE-MIGRATION GATE 4: Tool Inventory & Env Backup Checklist

Every tool that was manually installed on Windows must be re-installed on Linux. Document what
we have now so we don't forget anything.

#### 4a. Windows Tool Inventory (document before wiping or dual-booting)
- [ ] Verify and document each tool currently installed:
  - [ ] Git: `git --version` → `2.55.0.windows.2` → on Linux: `git` from PCLinuxOS repos
  - [ ] GitHub CLI (`gh`): `gh --version` → `2.96.0` → install: `gh` RPM or binary release
  - [ ] Python: `python --version` → `3.12.4` → install: `python3.12` from PCLinuxOS repos
  - [ ] Node.js: `node --version` → `v24.18.0` → install: nvm on Linux (preferred), or nodejs RPM
  - [ ] Bun: `bun --version` → `1.3.14` → install: `curl -fsSL https://bun.sh/install | bash`
  - [ ] Ollama: `ollama --version` → `0.32.3` → install: ollama install script (see Gate 3)
  - [ ] pip packages: `pip list` → capture full list → `pip freeze > agents/pre-linux-pip-freeze.txt`
  - [ ] OpenClaude/Claude CLI: document how to reinstall from `.openclaude/` source
  - [ ] OpenCode: `opencode --version` → document install method for Linux
  - [ ] VSCode: document extensions list for Linux reinstall
  - [ ] Antigravity (agy): document install method for Linux

#### 4b. Environment Variables & Keys Backup
- [ ] Confirm `ARBITR8DER/.env` has ALL required vars filled in (not just placeholders)
- [ ] Confirm `trading_studio/streams/kalshi_private.pem` exists and is valid (gitignored — NOT in
  repo, must be manually transferred or re-downloaded from Kalshi)
- [ ] Kalshi private key transfer plan: copy `kalshi_private.pem` via USB or encrypted channel
  to the new Linux machine before the old machine is wiped
- [ ] Kalshi API key ID: confirm it's noted in `agents/KEYS` (gitignored local key file)
- [ ] OpenCode Zen API key (`sk-sSGtBd...`): confirm in `.openclaude/.env` or `agents/KEYS`
- [ ] NVIDIA NIM API key (`nvapi-GKWWa...`): confirm location
- [ ] GitHub PAT: confirm it's in `agents/KEYS` and accessible on Linux post-migration
- [ ] Note: `.env` files are gitignored and must be manually transferred

#### 4c. Local Data Backup (Databases & Runtime State)
- [ ] `trading_studio/runtime/` is gitignored — this contains:
  - `prediction.db` (candle data, model runs, outcomes — months of data eventually)
  - `paper_wallet.db` (paper trading history)
  - `logs/` (session logs, ollama downloads)
- [ ] Decision: transfer runtime data to Linux or start fresh?
  - Recommendation: copy `prediction.db` and `paper_wallet.db` to Linux — preserve model training
    history and paper wallet history
  - Transfer via: USB drive, `rsync`, or `scp` if network transfer is available
- [ ] If transferring: document target path on Linux: `~/ARBITR8DER/trading_studio/runtime/`

---

### PCLinuxOS INSTALLATION PLAN

#### 5a. Preparation (Before Installing)
- [ ] Download PCLinuxOS ISO: https://www.pclinuxos.com/downloads/
  - Recommended: PCLOS KDE (rolling release, most compatible with AMD hardware)
  - Verify SHA256 checksum of downloaded ISO
- [ ] Create bootable USB: use Rufus (Windows) or dd (Linux/WSL):
  ```powershell
  # In WSL:
  sudo dd if=pclinuxos.iso of=/dev/sdX bs=4M status=progress
  ```
- [ ] Decision: **Dual-boot Windows + PCLinuxOS** OR **wipe and full Linux**?
  - Dual-boot is safer for transition — keep Windows until everything is verified working on Linux
  - Allocate ≥ 200 GB for Linux partition (25 GB Ollama models + repo + DBs + swap)
- [ ] Backup Windows: Windows → Settings → Backup → drive image (optional, your call)
- [ ] Note AMD Ryzen AI hardware specifics:
  - PCLinuxOS ships with kernel ≥ 6.x which has Ryzen AI driver support
  - AMD GPU: if using integrated AMD GPU, `amdgpu` driver should load automatically
  - For Ollama GPU acceleration on AMD: check ROCm support for this specific Ryzen AI chip

#### 5b. PCLinuxOS Base Install
- [ ] Boot from USB, run installer
- [ ] Partition: at minimum 200 GB for `/`, separate `/home` partition recommended
- [ ] Set username: `itsji` (match Windows username for path familiarity)
- [ ] Set hostname: something identifiable (e.g. `arbitr8der-desktop`)
- [ ] Enable NTFS mount for Windows partition (for access during transition):
  ```bash
  sudo mount -t ntfs-3g /dev/sdXY /mnt/windows -o ro    # read-only for safety
  ```

#### 5c. PCLinuxOS Package Manager Setup
- [ ] Update repos: `sudo apt-get update` (PCLinuxOS uses apt-like Synaptic over RPM backend)
  - Note: PCLinuxOS uses `apt-get` as a front-end to RPM. Not the same as Debian apt.
  - Synaptic is the GUI package manager
- [ ] Install base dev tools:
  ```bash
  sudo apt-get install -y git curl wget build-essential python3 python3-pip
  ```

#### 5d. Reinstall All Tools on PCLinuxOS
- [ ] **Git**: `sudo apt-get install git` → verify `git --version`
- [ ] **GitHub CLI**: install from binary release (RPM package may not be in PCLOS repos):
  ```bash
  # Check if in repos first:
  apt-cache search gh
  # If not: download RPM from https://github.com/cli/cli/releases/latest
  sudo rpm -i gh_*.rpm
  gh auth login
  gh auth setup-git
  ```
- [ ] **Python 3.12**: check PCLinuxOS repos — may need to compile from source if 3.12 not in repos
  ```bash
  python3 --version   # what version is default?
  # If < 3.12: build from source or use pyenv
  curl https://pyenv.run | bash   # pyenv for Python version management
  pyenv install 3.12.4
  pyenv global 3.12.4
  ```
- [ ] **Node.js via nvm**:
  ```bash
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
  source ~/.bashrc
  nvm install 24
  node --version   # expect v24.x.x
  ```
- [ ] **Bun**:
  ```bash
  curl -fsSL https://bun.sh/install | bash
  bun --version   # expect 1.3.x
  ```
- [ ] **Ollama**: see Gate 3 above for full model re-download instructions
- [ ] **OpenClaude/Claude CLI**: rebuild from source
  ```bash
  cd ~/.openclaude
  bun install
  bun run build
  node bin/openclaude --version
  # Add ~/bin/claude script pointing to this
  ```
- [ ] **OpenCode**:
  ```bash
  # Install OpenCode from npm or binary — check opencode.ai for Linux install instructions
  npm install -g opencode    # or follow opencode.ai docs
  opencode --version
  ```
- [ ] **Antigravity (agy)**: check `agy install` docs for Linux — likely similar curl/npm install
- [ ] **pip packages** (from pre-migration freeze):
  ```bash
  cd ~/ARBITR8DER
  pip3 install -e ./trading_studio        # installs all deps + arb CLI
  pip3 install -e "./trading_studio[dev]" # adds pytest, ruff, mypy
  arb version                              # must print: arbitr8der 0.1.0
  ```

#### 5e. Clone Repo and Restore Runtime Data on Linux
- [ ] Clone from GitHub:
  ```bash
  cd ~
  git clone git@github.com:itsjimjimsalabim/ARBITR8DER.git
  # OR HTTPS:
  git clone https://github.com/itsjimjimsalabim/ARBITR8DER.git
  cd ARBITR8DER
  git log --oneline -5   # verify latest commit matches
  ```
- [ ] Copy `.env` from Windows machine / USB:
  ```bash
  cp /mnt/usb/.env ~/ARBITR8DER/.env
  ```
- [ ] Copy `kalshi_private.pem`:
  ```bash
  mkdir -p ~/ARBITR8DER/trading_studio/streams/
  cp /mnt/usb/kalshi_private.pem ~/ARBITR8DER/trading_studio/streams/
  chmod 600 ~/ARBITR8DER/trading_studio/streams/kalshi_private.pem
  ```
- [ ] Optionally copy runtime databases:
  ```bash
  mkdir -p ~/ARBITR8DER/trading_studio/runtime/
  cp /mnt/usb/prediction.db ~/ARBITR8DER/trading_studio/runtime/
  cp /mnt/usb/paper_wallet.db ~/ARBITR8DER/trading_studio/runtime/
  ```
- [ ] Install Python package:
  ```bash
  pip3 install -e ~/ARBITR8DER/trading_studio
  ```
- [ ] Verify REPL launches:
  ```bash
  arb status
  arb snapshot
  ```

#### 5f. Linux-Specific Path Fixes
- [ ] Update `ARBITR8DER/.env` — any absolute paths in env vars need Linux equivalents
- [ ] Check `agents/agents.md` §"Canonical Home" — update to `~/ARBITR8DER` or `/home/itsji/ARBITR8DER`
- [ ] Verify `TradingStudioSettings` resolves `.env` path correctly on Linux (it uses
  package-relative path — should work, but verify with `arb status`)
- [ ] Update `opencode.json` if any paths are Windows-absolute
- [ ] Check `CLAUDE.md` for Windows-specific paths

#### 5g. Binance WebSocket — The Big Win (No More WSL Geo-Block)
- [ ] On native Linux, Binance WS **should not be geo-blocked**
- [ ] Test Binance WS: `python3 -c "import websockets; print('OK')"` then run candle battery
- [ ] Update `agents/onboarding_workflow.md` §7 Data Sources:
  - Change Binance WS status from "geo-blocked" to "WORKING (native Linux)"
- [ ] If Binance.com is still blocked (US location): may need VPN or continue using Binance.US REST
  - Note: Binance.com (not .us) WS may be geo-blocked for US users at the API level, not WSL
  - Test: `curl -I https://api.binance.com/api/v3/time` — if 451, it's US geo-block not WSL

#### 5h. Post-Migration Verification Checklist
- [ ] `git status` → clean, no dirty files
- [ ] `git remote -v` → shows `github.com/itsjimjimsalabim/ARBITR8DER.git`
- [ ] `python3 --version` → 3.12.x
- [ ] `arb version` → `arbitr8der 0.1.0`
- [ ] `arb status` → vessel: Full_Stop, all connections attempted
- [ ] `ollama list` → shows `qwen3:4b-instruct` and `qwen3-coder:30b`
- [ ] `ollama run qwen3:4b-instruct "say hello"` → responds
- [ ] `python3 -m pytest trading_studio/tests/ -v -q` → same pass rate as Windows
- [ ] `gh auth status` → authenticated as `itsjimjimsalabim`
- [ ] Kalshi WS connection: `arb forward start` → snapshot shows Kalshi WS WORKING
- [ ] Paper trade test: `buy BTC YES 2` → fills in paper mode
- [ ] Update `agents/dev_log.md` with Linux migration completion entry

---

### POST-MIGRATION DOCS UPDATE

#### 6a. After Linux Is Verified Working — Update All Docs
- [ ] `agents/agents.md` — update all version numbers with `--version` output from Linux
- [ ] `agents/agents.md` — update "Canonical Home" to Linux path
- [ ] `agents/agents.md` — update tool inventory table with Linux versions
- [ ] `agents/onboarding_workflow.md` — mark as "verified on PCLinuxOS YYYY-MM-DD"
- [ ] `agents/qwen_local_model_ops_guide.md` — update with Linux Ollama service notes
- [ ] `agents/github_connectivity.md` — update with Linux SSH working state
- [ ] `agents/onboarding_workflow.md` §10 Known Issues — add/resolve Linux-specific issues
- [ ] Commit all doc updates: `git add agents/ && git commit -m "docs: post-linux-migration docs update"`
- [ ] Push: `git push origin main`

#### 6b. OneDrive Sync — What Changes
- [ ] OneDrive no longer ruins everything — verify repo is NOT in any auto-sync folder on Linux
- [ ] `~/ARBITR8DER` on Linux = clean, no OneDrive, no slow lock files
- [ ] Remove all "OneDrive sync causes slow builds / stray lock files" warnings from docs if resolved
- [ ] Update `agents/agents.md` Known Issues table

---

### ARBITRATOR BRANCH AWARENESS NOTE

> The arbitrator feature is being coded by another AI agent. This Linux migration plan intentionally
> avoids code changes. When the arbitrator work is merged:
> - Review `agents/todo.md` §arbitrator for any new dependencies (new pip packages, new tools,
>   new services) that would need to be added to the Linux migration checklist above.
> - Update Gate 4a pip freeze after arbitrator deps land.
> - Confirm arbitrator runs on PCLinuxOS (no Windows-only APIs or COM objects).


## Theories of Operation

### Dual-Horizon Theory
Two models operating at different timescales should capture different market dynamics:

- **Macro model (72h / 288 × 15m candles)**: Captures trend regime, mean-reversion patterns,
  time-of-day effects, and broader momentum. Uses RSI, Bollinger bands, ATR, and volume
  trends. Best when market is in a clear regime (trending or ranging).

- **Micro model (5min / 30 × 1m candles)**: Captures short-term momentum, volume spikes,
  and order flow signals. Best for mean-reversion at the micro level or momentum continuation
  at the start of a new 15m window.

- **Ensemble**: Combines both signals. When models agree, confidence is higher. When they
  disagree, it may indicate a regime transition or noise.

### Frequency Lookup Theory
Markets exhibit recurring patterns under similar conditions. By bucketing historical windows
by {regime, streak, hour_of_day, RSI_level}, we can count how often UP occurred in each
bucket and use that frequency as a prediction. This is essentially a non-parametric
Bayesian approach — no assumptions about distribution shape, just empirical counts.

### Momentum Lookup Theory
Short-horizon price momentum tends to persist over 1-5 minute windows. If the last few
minutes showed strong upward movement with high volume, the next 15-minute window is
slightly more likely to be UP. The momentum acceleration metric captures whether this
momentum is increasing or fading.

### Auto-Scoring Theory
Continuous scoring provides real-time model feedback. Brier score tracks probability
calibration (is a 60% prediction right 60% of the time?). Log loss penalizes confident
wrong predictions more than uncertain ones. Running these metrics continuously lets us
detect model drift and know when to retrain.

### Live Retraining Theory
Models trained once will degrade as market dynamics shift. By periodically retraining
on accumulated scored predictions (features + outcomes), the models adapt to current
conditions. The retraining loop: `Predict → Score → Retrain → Predict (improved)`.
Minimum 20 samples required to avoid overfitting on small data. Both frequency lookup
(group-level counts) and gradient boosted trees (LightGBM) are retrained, preserving
the ensemble architecture while updating the underlying distributions.

### Feature Importance Hierarchy
From domain knowledge and backtesting experience:
1. **Regime** — the single most predictive feature. Trending markets behave differently.
2. **Momentum (returns at various horizons)** — short-term momentum persists.
3. **RSI** — overbought/oversold conditions predict mean-reversion.
4. **Volume spike** — unusual volume precedes large moves.
5. **Time of day** — market activity patterns repeat daily.
6. **Cross-asset correlation** — BTC leads ETH ~70% of the time.

## New Todos

### Immediate (Phase 8k)
- [x] Wire retrained models into predict command
- [x] 1m→15m candle aggregation
- [x] Predict --model flag (baseline|macro|micro|auto)

### Paper Trading Readiness (2026-07-26)
- [x] Run a preflight check before `autotrade on`: fresh snapshot, active Kalshi ticker, recent candles, wallet status, and model availability.
- [x] Make the auto-trade risk estimate price-aware for market orders so the risk gate uses the real midpoint instead of a fixed 50c fallback.
- [x] Persist auto-trade decisions and skip reasons outside memory so a restart does not erase the audit trail.
- [x] Expose an auto-trade heartbeat / last-evaluated timestamp in `autotrade status` so a stalled loop is visible quickly.
- [x] Add integration tests for `autotrade on|off|status`, one-trade-per-window gating, and the main skip paths (`no_snapshot`, `no_midpoint`, `no_candles`, stale data, risk block).
- [x] Define the unattended-session kill switch: max loss, max trades, and the manual stop command the operator should use first.
- [x] Reconcile and display any existing paper positions and wallet state at startup before enabling autonomous trades.

### Local Model Setup Docs (2026-07-26)
- [x] Create `agents/qwen_local_model_ops_guide.md` with the Qwen manager/coder split, download checks, and PC impact notes.
- [x] Update `agents/agents.md` with the verified machine tool inventory and current Ollama models.
- [x] Update `agents/onboarding_workflow.md` so new agents can find the local model guide during onboarding.

### Short-term
- [ ] Push local commits to GitHub — GitHub push protection blocks PAT in old commit ac2e110 (agents/KEYS). Either unblock via the GitHub secret-scanning URL, or rebase to remove the PAT from history. KEYS is now gitignored and PAT redacted locally.
- [ ] Kalshi WebSocket prediction feed integration
- [ ] Connect Binance WS from WSL (currently geo-blocked; REST fallback works)
- [x] Auto-trading: place paper orders when edge exceeds threshold

- [x] **Phase 9: Live Exchange Physics Realism & Paper Wallet Settlement System (2026-07-26) ← CURRENT**:
  - [x] **Quarter-Hour Auto-Settlement Physics Engine**:
    - Auto-settle all open paper positions at every 15-minute market resolution boundary (XX:00, XX:15, XX:30, XX:45).
    - Query official Kalshi settlement REST endpoint (`/markets/{ticker}`) or `SettlementWatcher` for the resolution outcome (`yes` or `no`).
    - Calculate contract payouts: 100c ($1.00 per contract) for winning side, 0c for losing side.
    - Credit cash balance with settlement proceeds and record realized PnL in `PaperVenueAdapter` (`paper_wallet.db`).
  - [x] **Paper Wallet Physics Realism**:
    - Align paper wallet mechanics 1:1 with live Kalshi execution (locking position cost on order fill, updating unrealized PnL during open market, auto-closing positions at expiration).
    - Prevent orphaned open positions from persisting past contract expiry across REPL / runner sessions.
  - [x] **Research & Intelligence Gathering**:
    - **Kalshi Trading Physics**: Research 15-minute binary market settlement rules (CFTC compliance, underlying index strike settlement formula, settlement verification lag).
    - **Short-Term BTC/ETH Prediction Models**: Research micro-momentum indicators (1m-15m timeframe), realized volatility metrics, order flow imbalance, and Bayesian frequency lookups for 15-minute horizons.
    - **Community & Market Insights**: Research Kalshi 15-minute BTC/ETH market dynamics across Reddit (r/Kalshi, r/AlgorithmicTrading), trading forums, and market maker quote behavior.
  - [x] **Live Kalshi Portfolio Balance Auto-Sync on Session Start**:
    - **Theory of Operation**: Paper trading physics must match live portfolio equity constraints (e.g. ~$17 real cash). At the start of every 15-minute paper session, query Kalshi REST API `/portfolio/balance` via `KalshiRestMarketDiscoveryClient.get_balance()`.
    - **Auto-Initialization**: Automatically override `PaperVenueAdapter` starting/current balance with the real live portfolio cash balance (falling back cleanly to `paper_wallet.db` if API key is unconfigured or offline).
    - **Position & Risk Sizing Realism**: Ensure contract quantity rules (minimum 2 contracts @ ~50c = $1.00 cost) and risk caps are evaluated against true live equity at the beginning of each 15-minute market run.
    - **Reprogramming Plan**:
      1. Update `PaperVenueAdapter` to support async `sync_live_balance(kalshi_client)` or auto-sync on init.
      2. Wire `run_ai_trading_session.py` to auto-fetch live balance from Kalshi REST and invoke `sync_live_balance()` before enabling `AutoTradingEngine`.
      3. Update `TradeJournal` session headers to log `real_kalshi_balance_usd` alongside paper balance.
  - [x] **Model Retraining & Brier Scorecard Feedback Loop**:
    - Log settled outcomes into `prediction.db` scorecards to continuously evaluate model calibration (Brier score & LogLoss tracking).
    - Trigger walk-forward auto-retraining on new candle/settlement batches to continuously adapt model parameters.
  - [x] **CLI REPL Modularization & Terminal UI Streamlining**:
    - **Theory of Operation**: The trading studio is built for AI agent operability, speed, and clean structured data—not human visual terminal eye-candy. Elaborate ASCII banners and complex colorized tables add non-essential LOC (~1,649 lines) and token bloat.
    - **Modularization Plan**:
      1. Split `interactive_trading_repl_loop.py` into smaller focused modules: `repl_command_parser.py` (argument parsing), `repl_view_renderers.py` (data output formatting), and `repl_trading_handlers.py` (order & wallet actions).
      2. Streamline terminal UI formatting, favoring fast, compact, machine-readable JSON and plain-text outputs tailored for AI context efficiency.

### Medium-term (Phase 10+)
- [ ] Multi-model ensemble weighting based on recent accuracy
- [ ] Calendar-aware features (market hours, weekends, news events)
- [ ] Sentiment integration (Polymarket, social media)
- [ ] ARMED transition: live Kalshi execution with real money

## Current Implementation State

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Boundary And Security | DONE |
| 1 | Foundation | DONE |
| 2 | Data Contracts & Connectors | DONE |
| 3 | Real Data Connectors | DONE |
| 4 | Battery Mode | DONE |
| 5 | Forecast Evidence | DONE |
| 6 | Operator Workflow | DONE |
| 7 | PAPER Order Lifecycle | DONE |
| 8 | Prediction System | DONE (8a-8l complete) |
| 9 | Exchange Physics Realism & Auto-Settlement | PENDING |
| 10 | ARMED Transition | PENDING |

## Test Status

394 passed, 2 failed (network integration), 1 skipped across 17 test files (as of 2026-07-25):
- `test_auto_scoring_engine.py` — 16 tests (all pass)
- `test_backtest_engine.py` — 26 tests (all pass)
- `test_settlement_and_importance.py` — 22 tests (all pass)
- `test_micro_prediction_model.py` — 16 tests
- `test_macro_prediction_model.py` — 16 tests
- `test_feature_engine_v2.py` — 18 tests
- `test_candle_persistence.py` — 19 tests
- `test_connection_battery.py` — 1 failed (Kalshi WS assertion), 1 failed (orchestrator import — network), 1 skipped (geo-blocked)
- `test_phase1_complete.py` — 36 tests (all pass)
- `test_phase2_complete.py` — 38 tests
- `test_phase3_providers.py` — 39 tests
- `test_phase4_repl.py` — 13 tests
- `test_phase5_prediction.py` — 30 tests
- `test_phase6_operator_workflow.py` — 39 tests
- `test_phase7_paper_trading.py` — 58 tests
- `test_vessel_state_machine.py` — 2 tests

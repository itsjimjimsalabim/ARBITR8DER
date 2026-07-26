# ARBITR8DER Trading Studio - Canonical Fresh Build Plan

**Status:** The single active rebuild plan as of 2026-07-23.  
**Implementation target:** `ARBITR8DER/trading_studio/` only.  
**Execution posture:** `Full_Stop` and `PAPER` by default. No implementation phase authorizes a live Kalshi order.

## 1. Decisions Locked By This Plan

1. `agents/` is the shared operating brain: requirements, this plan, the active todo, development log, agent desks, and historical references. It must not contain executable trading software.
2. `trading_studio/` is the self-contained trading software project. Every executable trading module, test, operational script, package manifest, runtime path, and future UI source belongs beneath it.
3. The installable Python distribution and import package remain `arbitr8der`, but its source directory is `trading_studio/src/arbitr8der/`. Install it with `pip install -e .\\trading_studio`.
4. The root-level `src/`, `tests/`, `runtime/`, `pyproject.toml`, and requirements files describe the deleted legacy package. They are not a fallback implementation. Retire them only after the nested project installs and tests successfully.
5. Use RAM for the current hot snapshot and SQLite for durable history, audit, replay, and PAPER state. PostgreSQL is not part of the fresh build unless a later evidence-backed decision replaces SQLite.
6. Kalshi is the only execution venue. Binance, Coinbase, Polymarket, and CoinGecko are observation sources. Initial market scope is BTC and ETH 15-minute Kalshi markets only.
7. `PAPER` and `ARMED` share the complete intent, validation, risk, audit, and reconciliation lifecycle, but use separate venue adapters. PAPER must never be described as live-fill parity when a step is simulated.
8. Historical repositories and deleted code are reference evidence only. Do not restore, transplant, or import their implementation wholesale.
9. No strategic plans live under `trading_studio/`. Its README files are short directory maps only. The future passive UI, if built, is `trading_studio/ui/`, not a root application.

## 2. Starting Truth And Historical Lessons

### Verified starting state

- `main` has four commits and the legacy root `src/arbitr8der/` and root test suite are currently deleted in the worktree. Preserve that in-progress migration; do not reset, restore, or silently relocate it.
- Before this plan consolidation, `trading_studio/` contained only an obsolete planning README, not a package. The README is now a directory map; no package exists yet.
- The current root `pyproject.toml` points at the deleted root `src/arbitr8der/`; root `requirements.txt` and `.env.example` are stale. The example environment also contains a concrete Kalshi identifier and PostgreSQL settings, so it must be sanitized before any push.
- `agents.md` correctly identifies `trading_studio/` as the software home, but its directory map and build commands still describe the deleted root layout. Update it during the boundary phase.
- `agents/_archive/` remains historical reference only. It is not an active plan or source of current truth.

### Lessons retained from Git history

- The current repository's deleted code and `OLD_ARBITR8DER` show repeated failures around thin depth, stream stability, sequence handling, PAPER persistence, settlement, timing, and reconciliation. Those become acceptance gates rather than code to copy.
- `OLD_ARBITR8DER` expanded into a root-flat, multi-asset, bot/cloud system. The fresh build deliberately rejects that breadth: BTC/ETH, 15-minute markets, one operator, headless CLI, and explicit trade intent.
- `agents_attempt` and `Old_Agents` demonstrate that large shared histories quickly obscure runtime truth. Keep one active todo and one active build plan; preserve older material as read-only history.
- `ClaudeCodeCopyCat` is empty and `Gemma-Base` has no relevant implementation history. Neither is an input to the fresh build.

## 3. Target Repository Contract

```text
ARBITR8DER/
  .env                              # ignored shared secrets and local configuration
  .gitignore                        # includes scoped studio runtime ignores
  agents/                           # shared brain; no trading implementation
    agents.md
    Product_Requirements_&_Theories_of_Operations.md
    dev_log.md
    todo.md
    trading_studio_build_plan.md    # this file, the only active rebuild plan
    _archive/                       # historical reference only
  trading_studio/                   # all executable trading software
    readme.md                       # short directory map only
    pyproject.toml                  # `arbitr8der` package definition
    .env.example                    # placeholders only; explains root `.env`
    src/
      arbitr8der/
        ...                         # application source
    tests/
      unit/
      integration/
      network/
    scripts/                        # explicit operational utilities
    runtime/                        # ignored data, state, logs, archives, locks
      data/
      state/
      logs/
      archives/
    ui/                             # deferred passive display, if ever built
```

### Path and packaging rules

- A future agent must not create root-level `src/`, `tests/`, `scripts/`, `runtime/`, or a second Python project for the trading studio.
- `trading_studio/pyproject.toml` owns dependencies, linting, test configuration, and the `arbitr8der` command. It must be runnable from any current working directory.
- Resolve the shared root `.env` from the package location, not from the caller's current directory. Never commit secrets, private keys, real account values, or raw runtime data.
- Add scoped ignores for `trading_studio/runtime/`, local environments, and generated package artifacts. Do not hide source, tests, migrations, or recorded test fixtures.
- Use long, self-documenting names for new domain modules, classes, and public functions. Standard Python package markers and well-known protocol terms are the narrow exceptions.
- Every source subdirectory gets a small README only after it exists. The README states purpose, owned files, runtime inputs/outputs, and the parent map. It does not become a second requirements document.

## 4. Engineering Constraints

1. A new process starts in `Full_Stop`; persisted state may provide audit history but may never resume `Full_Forward` automatically.
2. `Battery` owns observation, health, and storage only. It has no execution capability or order adapter loaded.
3. `Full_Forward` permits an AI operator to submit explicit intent only after the applicable PAPER or ARMED gate is satisfied. No autonomous order loop is in scope.
4. Only one process can own live provider streams at a time. Use a runtime lease/lock and fail closed if another owner exists, preserving provider stream allowances.
5. Every operator decision records the immutable hot-snapshot version, data ages, and timestamps from provider receipt through outcome or fill.
6. A broken, stale, or sequence-gapped Kalshi book blocks trading. Auxiliary sources never substitute for it.
7. Unit tests may use sanitized, recorded provider payloads for pure parsing and domain behavior. They are not live evidence. Real endpoint checks are explicit, read-only `network` tests; no test may submit an order.
8. Do not hard-code historical source weights, polling intervals, fee figures, or profitability thresholds as facts. Version them as experiments after validating provider contracts and measuring outcomes.

## 5. Ordered Build Plan

### Phase 0 - Establish the boundary and remove ambiguity

**Objective:** Make the repository unambiguous before new implementation starts.

1. Record the current dirty-tree migration state in the development log and verify `git status`, `git remote -v`, and the active branch. Do not reset or recover deleted legacy files.
2. Verify that the studio README remains a directory map and that strategic documents remain under `agents/`; do not add another plan surface.
3. Create the nested `trading_studio/pyproject.toml`, `src/`, `tests/`, `scripts/`, and `runtime/` boundary before creating domain code.
4. Move or recreate package metadata beneath `trading_studio/`; then retire the stale root packaging files and root implementation directories in the same deliberate migration change.
5. Replace the tracked example environment with placeholder-only SQLite-era configuration. Treat the exposed Kalshi identifier as needing operator review/rotation before any ARMED work.
6. Update `agents.md`, the root README, and build instructions so no current document directs an agent to root `src/` or root tests.
7. Add scoped runtime ignores and confirm secrets and runtime artifacts are not staged.

**Exit gate:** `pip install -e .\\trading_studio` succeeds in a clean environment; `git ls-files` has no root trading implementation tree; no tracked config contains a real credential; one active plan exists under `agents/`.

### Phase 1 - Safe runnable foundation

**Objective:** Build the smallest installable studio that is safe by construction.

1. Create the package version module, typed configuration, path resolver, structured logging, and CLI entry point under `trading_studio/src/arbitr8der/`.
2. Implement the `Full_Stop -> Battery -> Full_Forward` state machine with transition audit persistence under `trading_studio/runtime/state/` and forced `Full_Stop` at process start.
3. Separate capability boundaries so status/config commands make no network connection and Battery cannot import an order-submission adapter.
4. Add a single-process runtime lease for provider-stream ownership.
5. Provide only conservative commands initially: `arbitr8der --version`, `status`, `vessel status`, and explicit state transition commands. All machine-readable output supports `--json`.
6. Add unit tests for paths, configuration, vessel transitions, forced-stop startup, CLI output, and lease behavior.

**Exit gate:** A fresh install can run `arbitr8der status` from outside the repository without network I/O, writes only beneath `trading_studio/runtime/`, reports `Full_Stop`, and reports PAPER as the default wallet mode.

### Phase 2 - Canonical data contracts and durable storage

**Objective:** Define one precise local truth before connecting providers.

1. Define immutable event, provider-health, order-book, price-observation, hot-snapshot, prediction, trade-intent, journal, and archive contracts.
2. Give every event and snapshot provider timestamp, receive timestamp, source age, source status, sequence/version, asset, market ticker, and snapshot version.
3. Define the end-to-end latency lineage: provider event -> local receipt -> hot snapshot -> AI read -> intent -> venue response -> fill or settlement.
4. Implement SQLite migrations, WAL mode, integrity checks, and a bounded asynchronous persistence queue. Market/order/audit events have priority over disposable sensor samples.
5. Create tables for observations, raw provider events, snapshots, provider health, predictions/outcomes, trade intents/fills, wallet snapshots, journals, sensor samples, and archive manifests.
6. Implement 72-hour hot-history retention with an atomic archive manifest and replay-friendly immutable exports. Never delete data before its archive is verified.
7. Test migrations, restart behavior, queue backpressure, data-lineage round trips, and CWD-independent paths using temporary databases.

**Exit gate:** A restart-safe local SQLite database can persist and replay a versioned snapshot without blocking the producer path or writing outside `trading_studio/runtime/`.

### Phase 3 - Observe real provider contracts, one source at a time

**Objective:** Validate actual provider behavior before claiming a five-source pipeline.

1. Implement read-only Kalshi REST market discovery for active BTC/ETH 15-minute tickers and market details: status, close time, strike/reference, bid/ask, depth, and fee metadata.
2. Implement a stateful Kalshi order-book client that applies a snapshot plus ordered deltas, detects sequence gaps, records staleness, and requires a verified rebuild after a gap.
3. Implement Binance BTC/ETH spot and historical-candle ingestion, including a read-only backfill path for recent one-minute data.
4. Implement Coinbase BTC/ETH spot ingestion as an independent cross-check.
5. Research and implement the smallest real Polymarket mapping that can be shown to be relevant to the active Kalshi market; mark it unavailable instead of inventing a mapping.
6. Implement CoinGecko macro context as a slow, non-triggering observation source.
7. For each provider, add a sanitized parsing fixture from an observed response and an opt-in read-only network smoke test. Record rate limits, authentication requirements, and failure modes in source-adjacent directory maps or `agents/dev_log.md`, never in secrets-bearing docs.

**Exit gate:** Each source has a verified contract, clear unavailable/stale state, and no path can submit a Kalshi order. The Kalshi order book is stateful and rejects invalid sequence state.

### Phase 4 - Battery-mode five-source vertical slice

**Objective:** Make one complete, timestamped local picture of the market.

1. Build the ingestion orchestrator to own the stream lease, start/stop every provider, update hot state, and enqueue durable events without waiting on SQLite.
2. Merge all five provider states into one immutable hot snapshot with a monotonically increasing version.
3. Implement health policy for source ages, reconnects, sequence gaps, clock errors, provider errors, queue depth, CPU/RAM/disk/network counters, and degraded modes.
4. Expose compact read-only commands: `snapshot`, `health`, `markets`, and `history`. They must identify missing or stale sources rather than silently omitting them.
5. Run Battery soak sessions and archive the resulting health, timing, and data-quality evidence.

**Exit gate:** A Battery session produces a single versioned snapshot containing all five source states, persists the audit trail, reports every degradation, and exposes no trade command or execution adapter.

### Phase 5 - Measurable BTC/ETH prediction evidence loop

**Objective:** Prove that the studio can measure a forecast before it can trade one.

1. Build the minimum loop: collect actual BTC/ETH observations -> create a 15-minute forecast -> record inputs and snapshot version -> resolve the outcome -> score the forecast.
2. Backfill only validated recent historical candles, initially capped at 72 hours, and label coverage gaps explicitly.
3. Implement transparent baseline features: 1/5/15-minute direction, realized volatility, spot disagreement, volume, time to market close, market-implied price, and data freshness.
4. Store forecast probability, confidence/calibration inputs, rejection reasons, model/feature version, and outcome. A NO_TRADE recommendation is a valid scored output.
5. Create replay tooling that produces the same forecast from the archived input snapshot and feature version.
6. Treat source weights and decision thresholds as versioned experiments. Compare them to a documented simple baseline before accepting any claimed improvement.

**Exit gate:** The studio can replay a resolved 15-minute forecast, identify exactly what it saw, and report accuracy, calibration, coverage, and rejection reasons. It still creates no trade intent automatically.

### Phase 6 - AI operator workflow and journals

**Objective:** Let an AI inspect evidence and record reasoning without hiding actions in prose.

1. Build the operator CLI around compact JSON-capable commands: `monitor`, `snapshot`, `health`, `markets`, `history`, `predict`, `opportunities`, `positions`, `journal`, `pending`, `cancel`, and `exit`.
2. Keep Battery commands read-only. A future `Full_Forward` intent command must require the exact snapshot version it was based on.
3. Add `--script` or a timestamped command queue for repeatable timed workflows; do not rely on fragile piped interactive input.
4. Store structured journal entries that link observation, hypothesis, snapshot version, intent, outcome, and next experiment.
5. Produce session archives and a read-only scorecard for forecast accuracy, coverage, health, latency, fees, depth, slippage, and PnL when those fields exist.

**Exit gate:** An operator can reconstruct a decision from the journal and archived snapshot, and Battery remains incapable of placing an order.

### Phase 7 - PAPER order lifecycle and reconciliation

**Objective:** Add conservative paper trading only after the observation and scoring loop is trustworthy.

1. Define a common order-intent lifecycle: operator intent -> snapshot/risk validation -> pricing/depth check -> venue adapter -> acknowledgement/fill -> inventory -> settlement -> reconciliation -> journal/archive.
2. Implement risk controls before the PAPER adapter: vessel state, wallet mode, minimum two-contract rule, balance/exposure, maximum positions, session/daily loss caps, cooldowns, reentry lock, stale-Kalshi-book block, and emergency stop.
3. Implement a PAPER venue adapter using real observed market data and a documented, calibratable fill policy. Never call arbitrary random latency "realistic" or conceal model assumptions.
4. Persist paper wallet, pending limit orders, fills, cost basis, fees, drift, and inventory. Implement settlement watching from Kalshi market resolution and restart-safe reconciliation.
5. Implement fee calculations only after verifying the current Kalshi specification and lock the formula behind focused tests.
6. Keep the ARMED adapter absent or physically disabled in PAPER builds. The shared lifecycle does not mean PAPER can reach a live endpoint.

**Exit gate:** A paper position survives restart, resolves against a real market outcome, has a complete audit lineage, and cannot cause a live Kalshi mutation through any CLI, script, or test.

### Phase 8 - PAPER proof, review, and readiness report

**Objective:** Generate evidence before even considering ARMED capability.

1. Define success metrics before a proof run: coverage, stream stability, reconciliation completeness, drawdown, fees/slippage, prediction calibration, baseline comparison, and data exclusions.
2. Require each PAPER session to end with archived inputs, reconciled inventory, settled or explicitly open positions, health findings, and a human/AI journal review.
3. Three consecutive profitable, reconciled PAPER sessions are a minimum operational check, not statistical proof by themselves. Define the required sample size and confidence rule before using the result as a recommendation.
4. Build a readiness report that fails closed on stale books, stream gaps, missing archives, unexplained positions, failed replay, or an unreviewed assumption.
5. Keep the passive UI parked until this CLI/PAPER loop is demonstrated. If resumed, it reads archived/runtime data only and cannot write orders or data.

**Exit gate:** A reproducible readiness report shows the evidence, limitations, and failures. It makes no automatic recommendation to enable ARMED.

### Phase 9 - ARMED capability, only after explicit authorization

**Objective:** Add a tightly constrained live adapter only when the operator explicitly starts this phase.

1. Perform a separate security, provider-contract, and failure-mode review against current Kalshi documentation before writing live-order code.
2. Require an explicit typed `ARMED` confirmation for every live session, fresh credential validation, live-balance/position reconciliation, and a verified single-process lease.
3. Use the shared lifecycle with an ARMED Kalshi adapter, idempotency identifiers, post-submit reconciliation, cancel-all emergency behavior, and a forced return to `Full_Stop`.
4. Enforce operator-selected sizing, loss caps, and audit journaling. No autonomous order generation is introduced.

**Exit gate:** A human explicitly authorizes a defined live session after reviewing the readiness report. This plan itself does not grant that authorization.

## 6. Verification Standard For Every Phase

Each implementation change must provide all of the following before its todo item is marked complete:

1. A focused test and a relevant end-to-end or read-only network check when external behavior is involved.
2. A clean install/test/lint command run from `trading_studio/` and recorded outcome in `agents/dev_log.md`.
3. A directory-map update for any new studio subsystem.
4. A check that no secret, runtime database, log, or generated archive is staged for Git.
5. An update to `agents/todo.md` that moves only verified work forward.

## 7. Immediate Next Action

Do not begin provider or execution work yet. The next implementing AI starts Phase 0: preserve the current migration, make `trading_studio/` a self-contained installable package, remove stale root-package references, sanitize tracked configuration examples, and verify the package boundary before creating domain modules.

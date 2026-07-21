# AI Benchmark Tests & Performance Dynamometers — Master Plan

> Created: 2026-07-21
> Status: **SCAFFOLD / PLANNING PHASE**
> Author: Agent Claude

---

## Purpose

Build a rigorous, cheat-proof benchmarking system that tests real AI models and CLI
agents across every skill domain ARBITR8DER cares about. No mock data. No shortcuts.
Every test run is logged with full AI specs so results are reproducible and comparable.

This is **not** a toy leaderboard. This is a precision dynamometer — we measure
torque, not marketing claims.

---

## Core Principles

| Principle | Meaning |
|-----------|---------|
| **No Mock Data** | Every test uses real inputs — real codebases, real market data, real problems |
| **No Cheating** | Tests are blind where possible; the AI doesn't know the expected answer beforehand |
| **Full AI Specs** | Every result row logs: provider, model ID, model version, reasoning depth, context window, temperature, max tokens, and any custom config flags |
| **Reproducible** | Same inputs + same config = same score band (within tolerance) |
| **Database-Backed** | All results go into a SQLite database, not spreadsheets |
| **Scoreboard** | A live scoreboard view shows who's winning across all categories |

---

## Benchmark Categories

### 1. Reading Comprehension
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| RC-01 | Read a long technical document and answer precise questions | Easy |
| RC-02 | Extract structured data from an unstructured report | Medium |
| RC-03 | Read a 100K+ token codebase section and identify a buried bug | Hard |
| RC-04 | Multi-document synthesis — read 5 files, answer cross-reference questions | Hard |

### 2. Research & Synthesis
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| RS-01 | Given a topic, produce a factual research brief with sources | Easy |
| RS-02 | Analyze conflicting information and identify the most reliable claim | Medium |
| RS-03 | Build a technical comparison matrix from 3+ vendor docs | Hard |
| RS-04 | Research a trading strategy and produce a feasibility report | Hard |

### 3. Reasoning & Logic
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| RG-01 | Multi-step logic puzzle with dependencies | Easy |
| RG-02 | Causal chain analysis — "what happens if X changes" | Medium |
| RG-03 | Game theory / strategic reasoning scenario | Hard |
| RG-04 | Formal logic — given rules, determine if a conclusion is valid | Hard |

### 4. Planning & Strategy
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| PL-01 | Break a feature request into a sprint plan with dependencies | Easy |
| PL-02 | Design a multi-system architecture for a real problem | Medium |
| PL-03 | Risk analysis — identify failure modes in a proposed plan | Hard |
| PL-04 | Full project plan: requirements → design → implementation → testing | Hard |

### 5. Programming — Backend
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| PB-01 | Implement a REST API endpoint with validation | Easy |
| PB-02 | Build a data pipeline that processes real CSV/JSON data | Medium |
| PB-03 | Design and implement a caching layer with invalidation logic | Hard |
| PB-04 | Refactor a messy codebase (real OpenCode or OpenClaude files) | Hard |

### 6. Programming — Analysis
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| PA-01 | Analyze a function's time/space complexity | Easy |
| PA-02 | Profile a slow query and optimize it | Medium |
| PA-03 | Review a PR for security vulnerabilities | Hard |
| PA-04 | Analyze a production incident log and identify root cause | Hard |

### 7. Programming — Debugging
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| DB-01 | Find and fix a syntax error in a 50-line script | Easy |
| DB-02 | Debug a race condition in async code | Medium |
| DB-03 | Track down a memory leak across multiple modules | Hard |
| DB-04 | Fix a failing test suite where the bug is non-obvious | Hard |

### 8. Programming — Database
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| DT-01 | Write a correct SQL query for a join problem | Easy |
| DT-02 | Design a schema for a given set of requirements | Medium |
| DT-03 | Optimize a slow query with proper indexes | Hard |
| DT-04 | Implement a migration script with rollback safety | Hard |

### 9. Programming — Frontend
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| FE-01 | Build a responsive component from a mockup | Easy |
| FE-02 | Implement a complex form with validation and state management | Medium |
| FE-03 | Build a real-time data dashboard with charts | Hard |
| FE-04 | Fix cross-browser compatibility issues in existing code | Hard |

### 10. Subagent Drift (Key Variable)
> **The question**: How many subagents can work on a single project before drift occurs?
> Is it 2? 4? 8? We're measuring the exact tipping point.

| Test | What It Measures | Agents | Difficulty |
|------|------------------|--------|------------|
| SA-01 | Baseline: single agent on a 5-file feature. Score quality. | 1 | Easy |
| SA-02 | Two agents split a project into frontend/backend. Measure alignment. | 2 | Medium |
| SA-03 | Four agents work on separate modules of the same codebase. Detect drift. | 4 | Hard |
| SA-04 | Six+ agents on a full project sprint. Find the chaos threshold. | 6+ | Hard |

#### Drift Detection Metrics
| Metric | How Measured |
|--------|-------------|
| Code duplication | Two agents write the same function independently |
| Style divergence | Inconsistent naming, patterns, architecture across files |
| Contradictory logic | Agent A does X, Agent B undoes X |
| Context loss | Agents forget decisions made by earlier agents |
| Merge conflicts | File-level conflicts requiring human resolution |
| Quality degradation | Per-agent quality score drops as agent count rises |

#### Models Under Test (Subagent Drift)
Priority order:
1. **Big Pickle OpenCode** vs **Big Pickle OpenClaude** — same model, different CLI
2. **GLM / DeepSeek** — free/cheap challengers
3. **Qwen Coder** vs **another free model** — budget tier showdown
4. All tested against themselves with config tweaks
5. **All tested through Ubuntu** — no exceptions

### 11. Trading (Future)
| Test | What It Measures | Difficulty |
|------|------------------|------------|
| TR-01 | Analyze a binary event market and calculate fair odds | Easy |
| TR-02 | Build a pricing model from historical Kalshi/Polymarket data | Medium |
| TR-03 | Execute a paper trade with proper risk management | Hard |
| TR-04 | Full autotrade cycle: research → analysis → execution → monitoring | Hard |

---

## AI Spec Tracking (Every Result Row Must Include)

| Field | Example | Required |
|-------|---------|----------|
| `provider` | `openai`, `anthropic`, `ollama`, `openclaudedotdev` | Yes |
| `model_id` | `gpt-5.2-codex`, `claude-opus-4-0`, `llama3.1:8b` | Yes |
| `model_version` | Specific commit/date/version if known | Yes |
| `cli_tool` | `openclaude`, `opencode`, `claude-desktop`, `claude-code` | Yes |
| `reasoning_depth` | `none`, `low`, `medium`, `high` | Yes |
| `context_window` | `200000` (tokens) | Yes |
| `max_output_tokens` | `64000` | Yes |
| `temperature` | `0.0` | Yes |
| `custom_flags` | `--dangerously-skip-permissions`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=85` | No |
| `env_overrides` | Any env vars that affect behavior | No |

---

## Database Schema (SQLite)

See `database/SCHEMA.sql` for the full DDL. Key tables:

| Table | Purpose |
|-------|---------|
| `ai_specs` | Every unique AI configuration (provider + model + settings) |
| `test_categories` | The 10 benchmark categories above |
| `tests` | Individual test definitions (id, category, difficulty, prompt, expected properties) |
| `test_runs` | Each execution: which AI spec, which test, timestamp, environment |
| `test_results` | Scores, timing, token usage, pass/fail, notes |
| `scoreboard` | Materialized view for fast leaderboard queries |

---

## Scoreboard Design

### Per-Test Score (0–100)
- **Correctness** (0–40): Did it get the right answer?
- **Quality** (0–25): Is the output well-structured, complete, professional?
- **Speed** (0–15): Time to first token + total time (relative to fastest)
- **Efficiency** (0–10): Token usage — fewer tokens for same quality = higher score
- **Bonus** (0–10): Edge cases caught, extra insight, creative approach

### Aggregate Scores
- **Category Score**: Average across all tests in a category
- **Overall Score**: Weighted average across all categories
- **Tier Rank**: S / A / B / C / D / F

### Scoreboard Views
- **Overall Leaderboard**: All models ranked by overall score
- **Category Deep-Dive**: Best model per category
- **Cost-Adjusted**: Score per dollar of API cost
- **Speed-Adjusted**: Score per second of wall time
- **Config Comparison**: Same model with different settings (our Big Pickle tuning vs default)

---

## Anti-Cheat Measures

| Measure | How |
|---------|-----|
| **Blind Tests** | AI doesn't see expected answers during the test |
| **Salted Inputs** | Test data has unique fingerprints — if AI memorized a benchmark, it won't match |
| **Variation Rounds** | Same test type with different data each run |
| **Output Fingerprinting** | Detect copy-paste from training data via n-gram analysis |
| **Human Spot-Checks** | Random sample of results reviewed manually |
| **Timed Sessions** | AI must complete within a time window — no infinite retries |
| **One-Shot Scoring** | Primary score is from first attempt only (retries noted separately) |

---

## Implementation Phases

### Phase 0: Scaffold & Planning (NOW)
- [x] Create directory structure
- [x] Write this master plan
- [ ] Define full database schema
- [ ] Design test prompt templates
- [ ] Choose scoring rubrics per category
- [ ] Decide on SQLite vs SQLite+FTS for full-text search

### Phase 1: Database & Framework
- [ ] Create SQLite database with schema
- [ ] Build CLI runner that accepts AI spec + test ID → executes and logs
- [ ] Build scorer (automated where possible, manual review queue where not)
- [ ] Build scoreboard renderer (terminal + optional markdown export)

### Phase 2: Core Benchmarks (Reading, Reasoning, Debugging)
- [ ] Write 4 tests per category (12 tests total)
- [ ] Run against Big Pickle (gpt-5.2-codex via OpenClaude)
- [ ] Run against Claude (claude-opus-4-0 via Claude Code)
- [ ] Run against local Ollama (llama3.1:8b)
- [ ] Record baseline scores

### Phase 3: Programming Benchmarks
- [ ] Write programming tests with real code repos as input
- [ ] Validate that outputs actually work (compile, pass tests, etc.)
- [ ] Run against all models

### Phase 4: Subagent Drift Experiments
- [ ] Build multi-agent test harness (spawns N agents on same project)
- [ ] Run SA-01 through SA-04 against Tier 1 models (Big Pickle variants)
- [ ] Run against Tier 2 (GLM/DeepSeek, Qwen)
- [ ] Plot the drift curve — find the sweet spot
- [ ] Document findings: "N agents is too many for X project type"

### Phase 5: Full Suite + Trading
- [ ] Complete all 44 tests (11 categories × 4 tests)
- [ ] Add trading benchmarks when market data pipeline is ready
- [ ] Publish first official scoreboard

### Phase 6: Automation
- [ ] Nightly benchmark runs on a schedule
- [ ] Regression detection — alert if a model's score drops
- [ ] New model onboarding — add any new model to the suite in < 30 minutes

---

## Directory Structure (Final)

```
agent_benchmark_tests_&_performance_dynamometers/
├── SCAFFOLD_PLAN.md              ← you are here
├── METHODOLOGY.md                ← how we score, anti-cheat, versioning
├── AI_SPEC_FORMAT.md             ← exact format for recording AI configs
├── tests/
│   ├── reading/                  ← RC-01 through RC-04
│   ├── research/                 ← RS-01 through RS-04
│   ├── reasoning/                ← RG-01 through RG-04
│   ├── planning/                 ← PL-01 through PL-04
│   ├── programming-backend/      ← PB-01 through PB-04
│   ├── programming-analysis/     ← PA-01 through PA-04
│   ├── programming-debugging/    ← DB-01 through DB-04
│   ├── programming-database/     ← DT-01 through DT-04
│   ├── programming-frontend/     ← FE-01 through FE-04
│   ├── subagent-drift/           ← SA-01 through SA-04 (the key variable)
│   └── trading/                  ← TR-01 through TR-04 (future)
├── database/
│   ├── SCHEMA.sql                ← full DDL
│   ├── queries/                  ← useful queries (leaderboard, etc.)
│   └── benchmark.db              ← the actual database (gitignored until Phase 1)
├── runner/
│   ├── run_test.sh               ← execute a test against an AI spec
│   ├── score.sh                  ← score a test result
│   └── scoreboard.sh             ← render the leaderboard
├── results/
│   ├── raw/                      ← raw AI outputs per run
│   └── summaries/                ← aggregated results
└── configs/
    └── ai_specs/                 ← one JSON file per AI configuration tested
```

---

## Next Steps

1. **Review this plan** — anything missing? Wrong priority?
2. **Database schema** — I'll draft `database/SCHEMA.sql`
3. **First test batch** — write RC-01 through RC-04 (reading is easiest to score)
4. **Runner script** — build the CLI that pipes a test to an AI and captures output
5. **Run against Big Pickle** — first real benchmark data

---

*"Measure what matters. Log everything. Trust nothing the marketing says."*

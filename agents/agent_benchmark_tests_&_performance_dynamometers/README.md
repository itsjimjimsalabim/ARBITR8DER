# AI Benchmark Tests & Performance Dynamometers

> Created: 2026-07-21
> Status: **SCAFFOLD / PLANNING PHASE**

---

## The Prompt

> I want to scaffold a plan to perform a massive amount of research to develop our own
> benchmark tests with scoreboard and database to keep track of performance for all these
> AI models and CLI's, and even the custom configs: Reading, Researching, Reasoning,
> Planning, Programming (Backend, Analysis, Debugging, Database, Frontend), Trading
> (eventually), no mock data, no way to cheat, and the AI specs have to be super specific
> about model and model number, reasoning depth setting, context, other context,
> parameters, etc.
>
> I want a way to test for this variable: **amount of subagents on a project** — how many
> is too many before drift occurs? Is it 2 or 8?

---

## Priority Model Comparison Matrix

These are the head-to-head matchups that matter most to us, in priority order:

### Tier 1 — The Main Event
| Matchup | Why |
|---------|-----|
| **OG Big Pickle (OpenCode)** vs **Custom Big Pickle (OpenClaude)** | Same model (gpt-5.2-codex), different CLI. Does our tuning + OpenClaude CLI beat vanilla OpenCode? This is the question. |

### Tier 2 — Strong Challengers
| Matchup | Why |
|---------|-----|
| **GLM / DeepSeek** vs Tier 1 | Free/cheap alternatives. Can they hang with Big Pickle? |
| **Qwen Coder** vs **another free model** | Budget tier showdown. Which free model is least terrible? |

### Tier 3 — Config Wars (Same Model, Different Settings)
Every model above is also tested against **itself** with different configs:
- Default settings vs our custom tuning
- Different reasoning depth levels
- Different context window sizes
- Different CLI tools (OpenCode, OpenClaude, Claude Code, direct API)

### The Full Matrix
```
                    Big Pickle   Big Pickle   GLM/Deep    Qwen        Free
                    (OpenCode)   (OpenClaude)  Seek        Coder       Model X
                    --------     -----------   --------    --------    --------
Big Pickle (OC)       —           vs           vs          vs          vs
Big Pickle (OCL)                  —            vs          vs          vs
GLM/DeepSeek                                   —           vs          vs
Qwen Coder                                                 —          vs
Free Model X                                                          —
```

**All tested through Ubuntu.** Every run goes through the Ubuntu/WSL launcher — no exceptions.

---

## The Subagent Drift Test (Key Variable)

This is the experiment we're most curious about beyond raw model performance:

> **How many subagents can work on a single project before drift occurs?**

| Subagent Count | What We Measure |
|----------------|-----------------|
| **1 agent** | Baseline — no drift possible, score is pure model capability |
| **2 agents** | Minimal coordination. Do they stay aligned? |
| **4 agents** | Moderate. Does a shared codebase start to diverge? |
| **6 agents** | High. Are they rewriting each other's work? |
| **8 agents** | Maximum. Is it chaos or organized complexity? |
| **12+ agents** | Stress test. At what point does adding agents make output worse? |

### Drift Detection Metrics
| Metric | How We Detect It |
|--------|-----------------|
| **Code duplication** | Two agents write the same function independently |
| **Style divergence** | Inconsistent naming, patterns, architecture across files |
| **Contradictory logic** | Agent A does X, Agent B undoes X and does Y |
| **Context loss** | Agents forget decisions made by earlier agents |
| **Merge conflicts** | File-level conflicts that require human resolution |
| **Quality degradation** | Per-agent quality score drops as agent count rises |

### The Graph We Want
```
Quality Score
    ^
100 |  *
 90 |     *
 80 |        *
 70 |           *
 60 |              *  *  *
 50 |                       *  *
 40 |                              *
 30 |                                    *
    +--+--+--+--+--+--+--+--+--+--+--+--+-> Subagent Count
       1  2  3  4  5  6  7  8  9  10 11 12

         sweet spot
         ^^^
```

**Hypothesis**: The sweet spot is 2-4 agents for most projects. Beyond 4, drift cost
exceeds the parallelism benefit. But we're going to prove it with data, not guesses.

---

## What We Benchmark (11 Categories × 4 Tests = 44 Tests)

| Category | Tests | Priority |
|----------|-------|----------|
| Reading Comprehension | RC-01 to RC-04 | Phase 2 |
| Research & Synthesis | RS-01 to RS-04 | Phase 2 |
| Reasoning & Logic | RG-01 to RG-04 | Phase 2 |
| Planning & Strategy | PL-01 to PL-04 | Phase 2 |
| Programming — Backend | PB-01 to PB-04 | Phase 3 |
| Programming — Analysis | PA-01 to PA-04 | Phase 3 |
| Programming — Debugging | DB-01 to DB-04 | Phase 3 |
| Programming — Database | DT-01 to DT-04 | Phase 3 |
| Programming — Frontend | FE-01 to FE-04 | Phase 3 |
| **Subagent Drift** | **SA-01 to SA-04** | **Phase 4 (the key variable)** |
| Trading | TR-01 to TR-04 | Phase 5 (future) |

---

## Documentation

| Document | Purpose |
|----------|---------|
| [SCAFFOLD_PLAN.md](./SCAFFOLD_PLAN.md) | Full implementation plan, test definitions, phases |
| [METHODOLOGY.md](./METHODOLOGY.md) | Scoring rubric, anti-cheat, versioning |
| [AI_SPEC_FORMAT.md](./AI_SPEC_FORMAT.md) | Exact format for recording AI configurations |
| [database/SCHEMA.sql](./database/SCHEMA.sql) | SQLite schema — 7 tables, 5 views |
| [database/queries/](./database/queries/) | Leaderboard, category deep dive, config comparison |

---

## Quick Start (When We Build the Runner)

```bash
# 1. Initialize the database
sqlite3 database/benchmark.db < database/SCHEMA.sql

# 2. Register an AI spec
# (Insert from configs/ai_specs/*.json)

# 3. Run a test
./runner/run_test.sh --spec big-pickle-default --test RC-01

# 4. Check the scoreboard
sqlite3 database/benchmark.db < database/queries/leaderboard.sql
```

---

## Directory Structure

```
agent_benchmark_tests_&_performance_dynamometers/
├── README.md                     ← you are here
├── SCAFFOLD_PLAN.md              ← master plan with all 44 tests
├── METHODOLOGY.md                ← scoring, anti-cheat, versioning
├── AI_SPEC_FORMAT.md             ← how we record AI configs
├── configs/ai_specs/             ← one JSON per AI configuration
├── database/
│   ├── SCHEMA.sql                ← full DDL
│   └── queries/                  ← leaderboard, comparisons, etc.
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
│   ├── subagent-drift/           ← SA-01 through SA-04 (THE key variable)
│   └── trading/                  ← TR-01 through TR-04
├── runner/                       ← CLI to run and score tests
└── results/
    ├── raw/                      ← raw AI outputs (gitignored)
    └── summaries/                ← aggregated results
```

---

*"The only benchmark that matters is the one that matches how you actually use the model."*

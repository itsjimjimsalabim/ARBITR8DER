# Benchmark Methodology

> Created: 2026-07-21
> Status: SCAFFOLD

---

## Scoring Rubric (Per Test: 0–100 Points)

### 1. Correctness (0–40)
| Score | Criteria |
|-------|----------|
| 40 | Fully correct answer, all edge cases handled |
| 30 | Correct core answer, minor omission (e.g., missed one edge case) |
| 20 | Partially correct — right approach but wrong result in places |
| 10 | Fundamentally wrong direction but showed some understanding |
| 0 | Completely wrong or no answer |

### 2. Quality (0–25)
| Score | Criteria |
|-------|----------|
| 25 | Production-ready output: well-structured, complete, professional |
| 20 | Good output, minor formatting or completeness issues |
| 15 | Adequate — gets the job done but sloppy |
| 10 | Low quality — hard to read, missing key sections |
| 5 | Barely usable |
| 0 | Gibberish or refusal |

### 3. Speed (0–15)
| Score | Criteria |
|-------|----------|
| 15 | Under 30 seconds for easy, under 2 min for medium, under 5 min for hard |
| 12 | Under 1 min easy, under 3 min medium, under 8 min hard |
| 9 | Under 2 min easy, under 5 min medium, under 15 min hard |
| 6 | Under 5 min easy, under 10 min medium, under 30 min hard |
| 3 | Slow but finished |
| 0 | Timed out or never completed |

### 4. Efficiency (0–10)
| Score | Criteria |
|-------|----------|
| 10 | Minimal tokens for the quality achieved (top 10% of all runs) |
| 7 | Average token usage for the quality |
| 4 | Verbose but correct (2x+ tokens vs most efficient) |
| 1 | Extremely wasteful |
| 0 | N/A (failed test) |

### 5. Bonus (0–10)
| Score | Criteria |
|-------|----------|
| 10 | Caught edge cases we didn't test for, exceptional insight |
| 7 | Notable extra value beyond what was asked |
| 4 | Minor extra insight |
| 0 | Nothing extra |

---

## Test Difficulty Definitions

| Difficulty | Time Budget | Complexity | Token Budget |
|------------|-------------|------------|--------------|
| **Easy** | < 2 min | Single-step, clear instructions | < 4K output |
| **Medium** | < 5 min | Multi-step, some ambiguity | < 8K output |
| **Hard** | < 15 min | Complex, requires synthesis | < 16K output |

---

## Anti-Cheat Protocol

### Principle: "The test is real or it doesn't count"

1. **No Synthetic Benchmarks**
   - Every test uses real data: real code, real docs, real market data
   - No "solve this math puzzle" — those exist in training data
   - Test inputs are generated fresh or pulled from live sources

2. **Salted Inputs**
   - Each test run has a unique salt (hash of timestamp + random)
   - Test data is modified with salt-dependent variations
   - Example: RC-01 reads a specific GitHub PR, but the questions change each run

3. **Blind Execution**
   - AI never sees the expected answer before responding
   - Scoring rubric is hidden until after the AI produces output
   - Reviewer scoring is also blind to which AI produced which output (when possible)

4. **Output Fingerprinting**
   - Track n-gram patterns in outputs
   - Flag outputs that match training data verbatim
   - Compare across runs — suspiciously identical outputs get flagged

5. **One-Shot Primary Score**
   - The official score is from the FIRST attempt only
   - Retries are logged separately with a penalty flag
   - "I'll try again" is not a benchmark strategy

6. **Human Spot-Checks**
   - 20% of results randomly selected for manual review
   - Discrepancies trigger a full re-score of that test
   - Reviewer notes are stored in the database

---

## Versioning

### Test Versioning
- Format: `MAJOR.MINOR` (e.g., `1.0`, `1.1`, `2.0`)
- **MAJOR**: Test fundamentally changed (new data, new questions, new scoring)
- **MINOR**: Minor adjustments (typo fixes, scoring recalibration)

### Result Versioning
- Each result row has `test_version` and `runner_version`
- Scoreboard only compares results from compatible test versions
- Old results are archived, not deleted

### Runner Versioning
- The test runner itself is versioned
- Bugs in the runner that affect scoring require re-runs

---

## Data Integrity

| Rule | Enforcement |
|------|-------------|
| Every result must have a complete AI spec | DB constraint: NOT NULL on required fields |
| Raw outputs are immutable once logged | SHA-256 hash stored, verified on read |
| Scores can be updated (with reason) | Audit log tracks all score changes |
| No deleting results | Soft-delete only; `deleted_at` timestamp |
| Timestamps are UTC | All times stored as ISO 8601 UTC |

---

## What We Are NOT

| Not This | Instead We Are |
|----------|----------------|
| A marketing leaderboard | A precision measurement tool |
| "AI X beats AI Y" headlines | "Model A scored 73.2 on backend programming with 9999 REPL turns" |
| Comprehensive (test everything) | Focused (test what ARBITR8DER actually uses) |
| Fair to all models | Optimized for our use case (trading + coding + reasoning) |
| Static | Living — tests evolve as models and our needs evolve |

# Subagent Drift Tests

> **The key variable**: How many subagents can work on a single project before drift occurs?

This is the experiment we care about most beyond raw model performance.

## Tests

| Test | Agents | Difficulty | What Happens |
|------|--------|------------|-------------|
| SA-01 | 1 | Easy | Baseline — single agent builds a 5-file feature. Pure quality score. |
| SA-02 | 2 | Medium | Two agents split frontend/backend. Measure alignment at the seam. |
| SA-03 | 4 | Hard | Four agents build separate modules of the same codebase. Detect drift. |
| SA-04 | 6+ | Hard | Six+ agents on a full sprint. Find the chaos threshold. |

## Drift Detection

| Metric | Detection Method | Severity |
|--------|-----------------|----------|
| **Code duplication** | AST comparison — two agents write the same function | High |
| **Style divergence** | Linting rules + naming convention check | Medium |
| **Contradictory logic** | Semantic diff of module interfaces | Critical |
| **Context loss** | Check if agents reference decisions made by others | High |
| **Merge conflicts** | Git-level conflict count at integration | High |
| **Quality degradation** | Per-agent score vs single-agent baseline | Medium |

## Models to Test (Priority Order)

1. **Big Pickle OpenCode** (gpt-5.2-codex, default settings)
2. **Big Pickle OpenClaude** (gpt-5.2-codex, our custom tuning)
3. **GLM / DeepSeek** (free/cheap alternatives)
4. **Qwen Coder** vs another free model
5. All tested against themselves with config tweaks
6. **All through Ubuntu** — no exceptions

## What We Want to Prove

```
Hypothesis: The sweet spot is 2-4 agents for most projects.
Beyond 4, drift cost > parallelism benefit.

We want a graph like this:

Quality
  ^
100|  *
 90|     *
 80|        *
 70|           *
 60|              *  *  *
 50|                       *  *
 40|                              *
 30|                                    *
   +--+--+--+--+--+--+--+--+--+--+--+--+-> Agents
      1  2  3  4  5  6  7  8  9 10 11 12
```

## Test Design Requirements

Each test run must:
- Use the **same project codebase** across all agent counts
- Have a **clearly defined deliverable** (files, features, tests)
- Be **scored identically** regardless of agent count
- Log **per-agent** metrics (not just aggregate)
- Record **inter-agent conflicts** as a first-class metric

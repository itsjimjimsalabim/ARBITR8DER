# Codebase Memory MCP — AI Developer Guide

**Tool:** `codebase-memory-mcp` (CBM)
**Installed:** System-wide binary, NOT inside this repo
**Binary location:** `~/.local/bin/codebase-memory-mcp` (WSL/Linux)
**Source:** https://github.com/DeusData/codebase-memory-mcp
**Purpose:** Code intelligence for AI agents — call graphs, architecture, impact analysis, semantic search

> ⚠️ This tool lives OUTSIDE `ARBITR8DER/`. It is a developer tool, not trading software.
> Never add its source or binaries inside this repo.

---

## What It Does

CBM indexes `trading_studio/arbitr8der_package/` into a persistent knowledge graph using
tree-sitter AST analysis. Instead of reading 52 source files to understand the codebase,
you issue one graph query and get a structured answer in milliseconds using ~99% fewer tokens.

It is wired into the project via `.mcp.json` at the repo root alongside the GitHub MCP entry.
Any MCP-capable agent (Antigravity, OpenCode, Claude, Codex) can call its 15 tools directly.

---

## When To Use It

Use CBM **before** making any non-trivial code change:

| Question | CBM Tool | Example |
|----------|----------|---------|
| What calls this function? | `trace_path` | "What calls `settle_expired_positions`?" |
| What does this module depend on? | `get_architecture` | "Show me the orchestrator's boundaries" |
| If I change X, what breaks? | `detect_changes` | Impact of editing `paper_venue_adapter.py` |
| Is this function dead code? | `get_architecture` (dead code) | Find unused prediction helpers |
| Where is this pattern used? | `search_code` / `semantic_query` | "Find all places we acquire the lease" |
| How do these modules connect? | `search_graph` | "Show call edges from AutoTradingEngine" |

Use it **instead of** grepping 52 files, reading every import chain manually, or asking
"does anything call X?" and hoping.

---

## How To Use It (MCP Tool Calls)

CBM exposes tools your agent calls via MCP. After indexing, use these directly:

```
# Index the project (do once per session, or on first use)
index_repository(project="arbitr8der", path="/mnt/c/Users/itsji/ARBITR8DER/trading_studio")

# Trace a call chain
trace_path(function_name="settle_expired_positions", direction="inbound")

# Architecture overview — one call replaces reading the whole codebase
get_architecture(project="arbitr8der")

# Semantic search
semantic_query(project="arbitr8der", query="paper order execution flow")

# Structural search — regex on names
search_graph(project="arbitr8der", name_pattern=".*Engine.*")

# Impact analysis on current diff
detect_changes(project="arbitr8der")

# Graph query (Cypher-like)
query_graph(project="arbitr8der", query="MATCH (f:Function)-[:CALLS]->(g) WHERE f.name = 'retrain_models' RETURN g.name")
```

---

## First-Time Index (Run Once Per Machine)

```bash
# From WSL, after installing CBM:
codebase-memory-mcp index /mnt/c/Users/itsji/ARBITR8DER/trading_studio --project arbitr8der

# Verify the index:
codebase-memory-mcp cli search_graph '{"project": "arbitr8der", "name_pattern": ".*Orchestrator.*"}'
```

Auto-indexing via the background watcher will keep it current after that.

---

## Installation Status

CBM is installed as a **system binary** outside this repo. To verify:

```bash
which codebase-memory-mcp        # should return ~/.local/bin/codebase-memory-mcp
codebase-memory-mcp --version    # print version
```

If not installed (e.g. fresh machine, Linux migration):

```bash
curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash
```

No cloning required. Single static binary. Zero dependencies. Works on WSL and native Linux.

---

## MCP Config

CBM is registered in `ARBITR8DER/.mcp.json` under the `"codebase-memory"` key.
Any agent that reads `.mcp.json` picks it up automatically on project load.

The binary connects over stdio — no network, no API key, 100% local.
Your code never leaves the machine.

---

## What NOT To Do

- **Don't clone the CBM source into ARBITR8DER/** — it's a tool, not part of the trading studio
- **Don't put CBM results in `agents/`** — query it live, don't paste graph dumps into docs
- **Don't replace `agents/*.md` with CBM** — CBM knows *structure*, the docs know *intent and operating principles*. Both are needed.
- **Don't use CBM for runtime decisions** — it's a static analysis tool, not a live data source

---

## Integration Notes

- CBM persists its index at `~/.cache/codebase-memory-mcp/` — outside the repo, as expected
- The team-shared graph artifact (`.codebase-memory/graph.db.zst`) can optionally be committed
  to the repo so every new agent skips the initial index. Decision: add to `.gitignore` for now
  and re-index fresh per machine (fast enough on this codebase)
- WSL note: use Linux paths (`/mnt/c/...`) not Windows paths when calling `index_repository`

---

*Last updated: 2026-08-02 · Added by Antigravity*
*CBM source: https://github.com/DeusData/codebase-memory-mcp (37k stars, MIT license)*

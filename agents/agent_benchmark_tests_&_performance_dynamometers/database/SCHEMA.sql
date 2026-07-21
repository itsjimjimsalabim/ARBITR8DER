-- ============================================================
-- ARBITR8DER AI Benchmark Database Schema
-- Created: 2026-07-21
-- Engine: SQLite 3.x
-- ============================================================

-- -----------------------------------------------------------
-- AI Specifications — every unique configuration we test
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_specs (
    spec_id             TEXT PRIMARY KEY,
    display_name        TEXT NOT NULL,
    -- Provider
    provider_name       TEXT NOT NULL,           -- 'openai', 'anthropic', 'ollama', 'openclaudedotdev'
    provider_api_base   TEXT,
    provider_auth       TEXT DEFAULT 'api_key',
    -- Model
    model_id            TEXT NOT NULL,           -- 'gpt-5.2-codex', 'claude-opus-4-0', etc.
    model_version       TEXT,
    model_family        TEXT,
    context_window      INTEGER NOT NULL,        -- tokens
    max_output_tokens   INTEGER NOT NULL,        -- tokens
    -- CLI Tool
    cli_name            TEXT NOT NULL,           -- 'openclaude', 'opencode', 'claude-code', etc.
    cli_version         TEXT,
    cli_source          TEXT,                    -- 'local-build', 'npm', 'binary'
    cli_build_date      TEXT,
    -- Reasoning
    reasoning_depth     TEXT NOT NULL DEFAULT 'none',  -- 'none','low','medium','high'
    chain_of_thought    INTEGER DEFAULT 0,       -- boolean
    self_correction     INTEGER DEFAULT 0,       -- boolean
    -- Generation Settings
    temperature         REAL DEFAULT 0.0,
    top_p               REAL DEFAULT 1.0,
    frequency_penalty   REAL DEFAULT 0.0,
    presence_penalty    REAL DEFAULT 0.0,
    -- Session Config (JSON blob for flexibility)
    session_config      TEXT DEFAULT '{}',       -- JSON: repl_max_turns, auto_compact_pct, etc.
    env_overrides       TEXT DEFAULT '{}',       -- JSON: any env vars that affected behavior
    -- Metadata
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------
-- Test Categories
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_categories (
    category_id         TEXT PRIMARY KEY,        -- 'reading', 'research', 'reasoning', etc.
    display_name        TEXT NOT NULL,
    description         TEXT,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    weight              REAL DEFAULT 1.0         -- weight in overall score calculation
);

-- -----------------------------------------------------------
-- Individual Tests
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS tests (
    test_id             TEXT PRIMARY KEY,        -- 'RC-01', 'PB-03', etc.
    category_id         TEXT NOT NULL REFERENCES test_categories(category_id),
    difficulty          TEXT NOT NULL CHECK (difficulty IN ('easy','medium','hard')),
    title               TEXT NOT NULL,
    description         TEXT,
    prompt_template     TEXT NOT NULL,           -- the actual prompt sent to the AI
    input_data_path     TEXT,                    -- path to input files for this test
    expected_properties TEXT DEFAULT '{}',       -- JSON: what a correct answer must contain
    time_budget_seconds INTEGER,                 -- max allowed time
    token_budget_output INTEGER,                 -- max expected output tokens
    scoring_rubric      TEXT,                    -- JSON: custom scoring criteria
    version             TEXT NOT NULL DEFAULT '1.0',
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------
-- Test Runs — each execution of a test by an AI
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_runs (
    run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id             TEXT NOT NULL REFERENCES ai_specs(spec_id),
    test_id             TEXT NOT NULL REFERENCES tests(test_id),
    salt                TEXT,                    -- unique salt for this run (anti-cheat)
    -- Timing
    started_at          TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at        TEXT,
    wall_time_ms        INTEGER,                 -- total wall clock time
    time_to_first_ms    INTEGER,                 -- time to first token
    -- Token Usage
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_tokens        INTEGER,
    -- Status
    status              TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','completed','timeout','error','cancelled')),
    error_message       TEXT,
    -- Output
    raw_output_path     TEXT,                    -- path to raw output file in results/raw/
    output_hash         TEXT,                    -- SHA-256 of raw output (immutability)
    -- Metadata
    runner_version      TEXT,
    test_version        TEXT,
    environment         TEXT,                    -- JSON: OS, node version, etc.
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------
-- Test Results — scoring for each run
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_results (
    result_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES test_runs(run_id),
    -- Scores (0-100 scale, broken into components)
    correctness_score   INTEGER CHECK (correctness_score BETWEEN 0 AND 40),
    quality_score       INTEGER CHECK (quality_score BETWEEN 0 AND 25),
    speed_score         INTEGER CHECK (speed_score BETWEEN 0 AND 15),
    efficiency_score    INTEGER CHECK (efficiency_score BETWEEN 0 AND 10),
    bonus_score         INTEGER CHECK (bonus_score BETWEEN 0 AND 10),
    total_score         INTEGER GENERATED ALWAYS AS (
        COALESCE(correctness_score, 0) +
        COALESCE(quality_score, 0) +
        COALESCE(speed_score, 0) +
        COALESCE(efficiency_score, 0) +
        COALESCE(bonus_score, 0)
    ) STORED,
    -- Scoring Metadata
    scored_by           TEXT NOT NULL DEFAULT 'auto',  -- 'auto', 'human', 'hybrid'
    scorer_notes        TEXT,
    -- Anti-cheat
    fingerprint_flag    INTEGER DEFAULT 0,       -- flagged for suspicious output patterns
    human_spot_check    INTEGER DEFAULT 0,       -- selected for human review
    -- Versioning
    test_version        TEXT NOT NULL DEFAULT '1.0',
    runner_version      TEXT,
    -- Audit
    reviewed_at         TEXT,
    reviewed_by         TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------
-- Score Audit Log — track all score changes
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS score_audit_log (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id           INTEGER NOT NULL REFERENCES test_results(result_id),
    field_changed       TEXT NOT NULL,           -- 'correctness_score', etc.
    old_value           INTEGER,
    new_value           INTEGER,
    reason              TEXT NOT NULL,
    changed_by          TEXT NOT NULL,
    changed_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------
-- Indexes for performance
-- -----------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_test_runs_spec ON test_runs(spec_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_test ON test_runs(test_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_status ON test_runs(status);
CREATE INDEX IF NOT EXISTS idx_test_results_run ON test_results(run_id);
CREATE INDEX IF NOT EXISTS idx_test_results_score ON test_results(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_ai_specs_provider ON ai_specs(provider_name);
CREATE INDEX IF NOT EXISTS idx_ai_specs_model ON ai_specs(model_id);

-- -----------------------------------------------------------
-- Useful Views
-- -----------------------------------------------------------

-- Latest results per test per spec (best score)
CREATE VIEW IF NOT EXISTS v_best_scores AS
SELECT
    tr.spec_id,
    ai.display_name AS ai_name,
    ai.model_id,
    ai.provider_name,
    tr.test_id,
    t.category_id,
    t.difficulty,
    res.total_score,
    res.correctness_score,
    res.quality_score,
    res.speed_score,
    res.efficiency_score,
    res.bonus_score,
    tr.wall_time_ms,
    tr.total_tokens,
    res.created_at AS scored_at
FROM test_results res
JOIN test_runs tr ON res.run_id = tr.run_id
JOIN ai_specs ai ON tr.spec_id = ai.spec_id
JOIN tests t ON tr.test_id = t.test_id
WHERE tr.status = 'completed'
  AND res.total_score IS NOT NULL
ORDER BY res.total_score DESC;

-- Category leaderboard (average score per spec per category)
CREATE VIEW IF NOT EXISTS v_category_leaderboard AS
SELECT
    spec_id,
    ai_name,
    model_id,
    provider_name,
    category_id,
    ROUND(AVG(total_score), 1) AS avg_score,
    COUNT(*) AS tests_taken,
    MIN(total_score) AS worst_score,
    MAX(total_score) AS best_score
FROM v_best_scores
GROUP BY spec_id, category_id;

-- Overall leaderboard (weighted average across all categories)
CREATE VIEW IF NOT EXISTS v_overall_leaderboard AS
SELECT
    spec_id,
    ai_name,
    model_id,
    provider_name,
    ROUND(SUM(avg_score * cat.weight) / SUM(cat.weight), 1) AS weighted_overall,
    COUNT(DISTINCT category_id) AS categories_tested,
    SUM(tests_taken) AS total_tests_taken,
    ROUND(AVG(avg_score), 1) AS simple_average
FROM v_category_leaderboard
JOIN test_categories cat ON v_category_leaderboard.category_id = cat.category_id
GROUP BY spec_id
ORDER BY weighted_overall DESC;

-- Config comparison (same model, different settings)
CREATE VIEW IF NOT EXISTS v_config_comparison AS
SELECT
    a1.spec_id AS spec_a,
    a1.display_name AS name_a,
    a2.spec_id AS spec_b,
    a2.display_name AS name_b,
    a1.model_id AS shared_model,
    v1.category_id,
    v1.avg_score AS score_a,
    v2.avg_score AS score_b,
    (v1.avg_score - v2.avg_score) AS delta
FROM v_category_leaderboard v1
JOIN v_category_leaderboard v2 ON v1.category_id = v2.category_id
JOIN ai_specs a1 ON v1.spec_id = a1.spec_id
JOIN ai_specs a2 ON v2.spec_id = a2.spec_id
WHERE a1.model_id = a2.model_id
  AND a1.spec_id != a2.spec_id
  AND v1.spec_id < v2.spec_id;

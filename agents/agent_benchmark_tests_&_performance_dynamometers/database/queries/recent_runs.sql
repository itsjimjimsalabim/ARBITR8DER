-- ============================================================
-- Recent Test Runs
-- Latest activity across all AI configs
-- ============================================================
SELECT
    tr.run_id,
    ai.display_name AS ai_name,
    tr.test_id,
    t.category_id,
    t.difficulty,
    tr.status,
    res.total_score,
    tr.wall_time_ms,
    tr.total_tokens,
    tr.started_at
FROM test_runs tr
JOIN ai_specs ai ON tr.spec_id = ai.spec_id
JOIN tests t ON tr.test_id = t.test_id
LEFT JOIN test_results res ON res.run_id = tr.run_id
ORDER BY tr.started_at DESC
LIMIT 50;

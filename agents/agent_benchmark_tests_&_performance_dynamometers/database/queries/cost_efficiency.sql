-- ============================================================
-- Cost Efficiency
-- Score per dollar (requires token cost data)
-- ============================================================
SELECT
    tr.spec_id,
    ai.display_name,
    ai.model_id,
    COUNT(*) AS total_runs,
    ROUND(AVG(res.total_score), 1) AS avg_score,
    SUM(tr.total_tokens) AS total_tokens_used,
    ROUND(AVG(tr.total_tokens), 0) AS avg_tokens_per_run,
    ROUND(AVG(res.total_score) / NULLIF(SUM(tr.total_tokens) / 1000000.0, 0), 2) AS score_per_million_tokens
FROM test_results res
JOIN test_runs tr ON res.run_id = tr.run_id
JOIN ai_specs ai ON tr.spec_id = ai.spec_id
WHERE tr.status = 'completed'
  AND res.total_score IS NOT NULL
GROUP BY tr.spec_id
ORDER BY score_per_million_tokens DESC;

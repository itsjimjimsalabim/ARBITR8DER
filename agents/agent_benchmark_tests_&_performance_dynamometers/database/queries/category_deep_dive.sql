-- ============================================================
-- Category Deep Dive
-- Best model per category with all scores
-- ============================================================
SELECT
    category_id,
    ai_name,
    model_id,
    avg_score,
    tests_taken,
    best_score,
    worst_score
FROM v_category_leaderboard
ORDER BY category_id, avg_score DESC;

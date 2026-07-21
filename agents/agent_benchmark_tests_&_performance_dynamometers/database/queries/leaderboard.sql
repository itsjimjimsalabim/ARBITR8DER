-- ============================================================
-- Overall Leaderboard
-- Shows all AI configs ranked by weighted score across categories
-- ============================================================
SELECT
    spec_id,
    ai_name,
    model_id,
    provider_name,
    weighted_overall AS overall_score,
    categories_tested,
    total_tests_taken,
    simple_average
FROM v_overall_leaderboard;

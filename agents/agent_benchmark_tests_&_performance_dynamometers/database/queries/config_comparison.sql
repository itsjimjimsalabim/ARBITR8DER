-- ============================================================
-- Config Comparison
-- Same model, different settings — where does tuning help?
-- ============================================================
SELECT
    name_a,
    name_b,
    shared_model,
    category_id,
    score_a,
    score_b,
    delta,
    CASE
        WHEN delta > 5 THEN 'Config A wins significantly'
        WHEN delta > 0 THEN 'Config A wins slightly'
        WHEN delta = 0 THEN 'Tie'
        WHEN delta > -5 THEN 'Config B wins slightly'
        ELSE 'Config B wins significantly'
    END AS verdict
FROM v_config_comparison
ORDER BY ABS(delta) DESC;

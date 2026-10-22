-- =====================================================================================
-- 08_reconciliation.sql — Revenue bridge from ledger to customer analytics
-- WHY: The first question a Finance/Commercial stakeholder asks is "why doesn't your
-- revenue number match mine?" This bridge shows exactly where every pound goes.
-- =====================================================================================

CREATE OR REPLACE TABLE revenue_bridge AS
WITH s AS (SELECT * FROM stg_sales_lines)
SELECT step, ROUND(amount, 2) AS amount_gbp FROM (
    SELECT 1 AS ord, '1. Cleaned ledger, all lines (net of cancellations)' AS step,
           SUM(revenue) AS amount FROM s
    UNION ALL
    SELECT 2, '2. Remove bad-debt write-offs (A-invoices)',
           -SUM(revenue) FILTER (WHERE line_type = 'bad_debt_adjustment') FROM s
    UNION ALL
    SELECT 3, '3. Remove non-merchandise (postage, fees, manual, discounts, vouchers)',
           -SUM(revenue) FILTER (WHERE NOT is_product AND line_type IN ('sale','cancellation')) FROM s
    UNION ALL
    SELECT 4, '4. = Net merchandise revenue, all buyers',
           SUM(revenue) FILTER (WHERE is_product AND line_type IN ('sale','cancellation')) FROM s
    UNION ALL
    SELECT 5, '5. Remove guest / unidentified buyers',
           -SUM(revenue) FILTER (WHERE is_product AND line_type IN ('sale','cancellation')
                                  AND NOT is_identified) FROM s
    UNION ALL
    SELECT 6, '6. Remove product sales reversed via manual credit (rule R5b)',
           -SUM(revenue) FILTER (WHERE is_product AND is_identified AND is_reversed) FROM s
    UNION ALL
    SELECT 7, '7. = Net merchandise revenue, identified customers (analytics base)',
           SUM(revenue) FROM v_customer_lines
    UNION ALL
    SELECT 8, 'Check: step 4 + 5 + 6 - step 7 (must be 0)',
           (SELECT SUM(revenue) FROM s WHERE is_product AND line_type IN ('sale','cancellation'))
         - (SELECT SUM(revenue) FROM s WHERE is_product AND line_type IN ('sale','cancellation') AND NOT is_identified)
         - (SELECT SUM(revenue) FROM s WHERE is_product AND is_identified AND is_reversed)
         - (SELECT SUM(revenue) FROM v_customer_lines)
) t
ORDER BY ord;

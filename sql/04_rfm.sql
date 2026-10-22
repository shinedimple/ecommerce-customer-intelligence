-- =====================================================================================
-- 04_rfm.sql — Recency / Frequency / Monetary segmentation
-- Business question: "Who are our best customers, who is slipping, and who is gone?"
-- -------------------------------------------------------------------------------------
-- Scoring decisions (WHY):
--   R  quintiles on days since last order (5 = most recent). Continuous → quintiles OK.
--   F  BUSINESS BINS, not quintiles: ~27% of customers have exactly one order, so
--      quintiles would split identical customers arbitrarily into different scores.
--        1 order → 1 | 2 → 2 | 3–4 → 3 | 5–9 → 4 | 10+ → 5
--   M  quintiles on net merchandise revenue (after returns).
--   Segment names use the widely used R×F grid; M is kept as a separate value lens
--   because the management segmentation (Python, step 16) uses predicted CLV instead.
-- Mirrors src/cie/rfm.py — tests/test_consistency.py asserts both give the same counts.
-- =====================================================================================

CREATE OR REPLACE TABLE rfm_base AS
SELECT
    l.customer_id,
    DATE_DIFF('day', MAX(l.invoice_ts), (SELECT snapshot_date FROM params))      AS recency_days,
    COUNT(DISTINCT l.invoice) FILTER (WHERE l.line_type = 'sale')                 AS frequency,
    SUM(l.revenue)                                                                AS monetary
FROM v_customer_lines l
WHERE l.line_type = 'sale' OR l.line_type = 'cancellation'
GROUP BY l.customer_id
HAVING COUNT(DISTINCT l.invoice) FILTER (WHERE l.line_type = 'sale') > 0;

CREATE OR REPLACE TABLE rfm_scores AS
WITH s AS (
    SELECT
        *,
        6 - NTILE(5) OVER (ORDER BY recency_days, customer_id)                    AS r_score,
        CASE WHEN frequency >= 10 THEN 5
             WHEN frequency >= 5  THEN 4
             WHEN frequency >= 3  THEN 3
             WHEN frequency  = 2  THEN 2
             ELSE 1 END                                                            AS f_score,
        NTILE(5) OVER (ORDER BY monetary, customer_id)                            AS m_score
    FROM rfm_base
)
SELECT
    *,
    CAST(r_score AS VARCHAR) || CAST(f_score AS VARCHAR) || CAST(m_score AS VARCHAR) AS rfm_cell,
    CASE
        WHEN r_score >= 5 AND f_score >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 4 THEN 'Loyal Customers'
        WHEN r_score >= 4 AND f_score IN (2, 3) THEN 'Potential Loyalists'
        WHEN r_score = 5 AND f_score = 1 THEN 'New Customers'
        WHEN r_score = 4 AND f_score = 1 THEN 'Promising'
        WHEN r_score = 3 AND f_score = 3 THEN 'Need Attention'
        WHEN r_score = 3 AND f_score IN (1, 2) THEN 'About to Sleep'
        WHEN r_score <= 2 AND f_score = 5 THEN 'Cannot Lose Them'
        WHEN r_score <= 2 AND f_score IN (3, 4) THEN 'At Risk'
        ELSE 'Hibernating'
    END                                                                            AS rfm_segment
FROM s;

-- ---------- Q4.1 Segment summary: size vs value ------------------------------------
CREATE OR REPLACE TABLE rfm_segment_summary AS
SELECT
    rfm_segment,
    COUNT(*)                                                           AS customers,
    ROUND(COUNT(*) * 1.0 / SUM(COUNT(*)) OVER (), 4)                   AS pct_customers,
    ROUND(SUM(monetary), 0)                                            AS net_revenue,
    ROUND(SUM(monetary) / SUM(SUM(monetary)) OVER (), 4)               AS pct_revenue,
    ROUND(MEDIAN(recency_days), 0)                                     AS median_recency_days,
    ROUND(AVG(frequency), 1)                                           AS avg_orders,
    ROUND(MEDIAN(monetary), 0)                                         AS median_revenue
FROM rfm_scores
GROUP BY rfm_segment
ORDER BY net_revenue DESC;

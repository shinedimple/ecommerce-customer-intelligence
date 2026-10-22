-- =====================================================================================
-- 06_churn_risk_rules.sql — Transparent, rule-based churn-risk signal
-- Business question: "Which customers are overdue for their next order relative to
-- THEIR OWN buying rhythm?"
-- -------------------------------------------------------------------------------------
-- WHY a rule-based signal alongside the statistical model (Python, BG/NBD):
--   This is a non-contractual business — customers never "cancel", they just stop
--   ordering. So churn is never observed, only inferred. A simple overdue ratio is
--   explainable to an account manager in one sentence ("she usually orders every
--   40 days; it has been 130") and is the benchmark the model must beat.
-- overdue_ratio = days since last order / customer's average gap between orders.
-- Requires >= 3 orders (>= 2 gaps) for a meaningful personal cadence.
-- Thresholds (business rules, tunable): <=1.5 on track | 1.5–3 slipping | >3 lapsed.
-- =====================================================================================

CREATE OR REPLACE TABLE churn_risk_rules AS
WITH ord AS (
    SELECT customer_id, order_ts,
           LAG(order_ts) OVER (PARTITION BY customer_id ORDER BY order_ts) AS prev_ts
    FROM fact_orders
    WHERE is_identified AND order_type = 'sale'
),
gaps AS (
    SELECT customer_id,
           COUNT(*)                                                         AS orders,
           AVG(DATE_DIFF('day', prev_ts, order_ts))                         AS avg_gap_days,
           MEDIAN(DATE_DIFF('day', prev_ts, order_ts))                      AS median_gap_days,
           MAX(order_ts)                                                    AS last_order_ts
    FROM ord
    GROUP BY customer_id
),
t12 AS (
    -- Trailing-12-month net revenue: the revenue base that is "at stake".
    SELECT customer_id, SUM(revenue) AS revenue_t12m
    FROM v_customer_lines
    WHERE invoice_ts >= (SELECT snapshot_date FROM params) - INTERVAL 365 DAY
    GROUP BY customer_id
)
SELECT
    g.customer_id,
    g.orders,
    ROUND(g.avg_gap_days, 1)                                                AS avg_gap_days,
    g.median_gap_days,
    DATE_DIFF('day', g.last_order_ts, (SELECT snapshot_date FROM params))  AS recency_days,
    ROUND(DATE_DIFF('day', g.last_order_ts, (SELECT snapshot_date FROM params))
          / NULLIF(g.avg_gap_days, 0), 2)                                   AS overdue_ratio,
    CASE
        WHEN g.orders < 3 THEN 'Insufficient history'
        WHEN DATE_DIFF('day', g.last_order_ts, (SELECT snapshot_date FROM params))
             / NULLIF(g.avg_gap_days, 0) <= 1.5 THEN 'On track'
        WHEN DATE_DIFF('day', g.last_order_ts, (SELECT snapshot_date FROM params))
             / NULLIF(g.avg_gap_days, 0) <= 3.0 THEN 'Slipping'
        ELSE 'Lapsed'
    END                                                                     AS cadence_status,
    COALESCE(t.revenue_t12m, 0)                                             AS revenue_t12m
FROM gaps g
LEFT JOIN t12 t USING (customer_id);

CREATE OR REPLACE TABLE churn_risk_rules_summary AS
SELECT
    cadence_status,
    COUNT(*)                                                                AS customers,
    ROUND(SUM(revenue_t12m), 0)                                             AS revenue_t12m,
    ROUND(SUM(revenue_t12m) / SUM(SUM(revenue_t12m)) OVER (), 4)            AS pct_t12m_revenue
FROM churn_risk_rules
GROUP BY cadence_status
ORDER BY revenue_t12m DESC;

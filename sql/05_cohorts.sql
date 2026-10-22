-- =====================================================================================
-- 05_cohorts.sql — Acquisition cohort retention & revenue
-- Business question: "Are customers we acquire more recently as good as older ones,
-- and when do customers typically drop off?"
-- -------------------------------------------------------------------------------------
-- Cohort = month of first merchandise order (dim_customer.cohort_month).
-- CAVEAT: Dec-2009 cohort is left-censored (contains pre-existing customers whose
-- earlier history is not in the data). It is flagged and excluded from averages.
-- Months are compared only up to Nov-2011 (last complete month).
-- =====================================================================================

CREATE OR REPLACE TABLE cohort_activity AS
WITH act AS (
    SELECT DISTINCT
        o.customer_id,
        strftime(o.order_ts, '%Y-%m') AS active_month
    FROM fact_orders o
    WHERE o.is_identified AND o.order_type = 'sale'
      AND o.order_date <= DATE '2011-11-30'
)
SELECT
    c.cohort_month,
    c.is_left_censored,
    a.active_month,
    DATE_DIFF('month', CAST(c.cohort_month || '-01' AS DATE),
                       CAST(a.active_month || '-01' AS DATE))            AS months_since_first,
    a.customer_id
FROM act a
JOIN dim_customer c USING (customer_id);

CREATE OR REPLACE TABLE cohort_retention AS
WITH sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size
    FROM cohort_activity WHERE months_since_first = 0 GROUP BY cohort_month
)
SELECT
    a.cohort_month,
    ANY_VALUE(a.is_left_censored)                                         AS is_left_censored,
    s.cohort_size,
    a.months_since_first,
    COUNT(DISTINCT a.customer_id)                                         AS active_customers,
    ROUND(COUNT(DISTINCT a.customer_id) * 1.0 / s.cohort_size, 4)         AS retention_rate
FROM cohort_activity a
JOIN sizes s USING (cohort_month)
GROUP BY a.cohort_month, s.cohort_size, a.months_since_first
ORDER BY a.cohort_month, a.months_since_first;

-- ---------- Q5.1 Average retention curve (excl. left-censored Dec-2009 cohort) -------
-- Weighted by cohort size. Only cohorts old enough to have month N are included in N.
CREATE OR REPLACE TABLE cohort_avg_curve AS
SELECT
    months_since_first,
    COUNT(*)                                                              AS cohorts_observed,
    ROUND(SUM(active_customers) * 1.0 / SUM(cohort_size), 4)              AS weighted_retention
FROM cohort_retention
WHERE NOT is_left_censored AND months_since_first BETWEEN 1 AND 12
GROUP BY months_since_first
ORDER BY months_since_first;

-- ---------- Q5.2 Cumulative revenue per customer by cohort (value maturity) ---------
CREATE OR REPLACE TABLE cohort_revenue AS
WITH rev AS (
    SELECT
        c.cohort_month,
        DATE_DIFF('month', CAST(c.cohort_month || '-01' AS DATE),
                  CAST(strftime(o.order_ts, '%Y-%m') || '-01' AS DATE))   AS months_since_first,
        SUM(o.order_value)                                                AS revenue
    FROM fact_orders o
    JOIN dim_customer c USING (customer_id)
    WHERE o.is_identified AND o.order_date <= DATE '2011-11-30'
    GROUP BY 1, 2
),
sizes AS (SELECT cohort_month, COUNT(*) AS cohort_size FROM dim_customer GROUP BY 1)
SELECT
    r.cohort_month,
    r.months_since_first,
    s.cohort_size,
    ROUND(SUM(r.revenue) OVER (PARTITION BY r.cohort_month ORDER BY r.months_since_first)
          / s.cohort_size, 2)                                             AS cum_revenue_per_customer
FROM rev r JOIN sizes s USING (cohort_month)
ORDER BY r.cohort_month, r.months_since_first;

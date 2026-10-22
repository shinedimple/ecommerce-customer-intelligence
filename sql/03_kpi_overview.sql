-- =====================================================================================
-- 03_kpi_overview.sql — Business health KPIs (definitions: docs/02_kpi_definitions.md)
-- Business question: "Is the business growing, and is growth coming from more
-- customers, more orders per customer, or bigger orders?"
-- =====================================================================================

-- ---------- Q3.1 Monthly KPI trend (complete months only) ----------------------------
CREATE OR REPLACE TABLE kpi_monthly AS
WITH orders AS (
    SELECT o.*, strftime(order_ts, '%Y-%m') AS ym
    FROM fact_orders o
),
first_order AS (
    SELECT customer_id, cohort_month FROM dim_customer
),
m AS (
    SELECT
        ym                                                                        AS year_month,
        SUM(order_value) FILTER (WHERE order_type = 'sale')                       AS gross_merch_sales,
        -SUM(order_value) FILTER (WHERE order_type = 'cancellation')              AS returns_value,
        SUM(order_value)                                                          AS net_merch_revenue,
        SUM(order_value) FILTER (WHERE order_type = 'sale' AND is_identified)     AS identified_sales,
        COUNT(*) FILTER (WHERE order_type = 'sale')                               AS orders,
        COUNT(DISTINCT customer_id) FILTER (WHERE order_type = 'sale')            AS active_customers
    FROM orders
    GROUP BY ym
),
newc AS (
    SELECT cohort_month AS year_month, COUNT(*) AS new_customers
    FROM first_order GROUP BY cohort_month
)
SELECT
    m.*,
    ROUND(m.gross_merch_sales / NULLIF(m.orders, 0), 2)                           AS aov,
    ROUND(m.returns_value / NULLIF(m.gross_merch_sales, 0), 4)                    AS return_rate,
    ROUND(m.identified_sales / NULLIF(m.gross_merch_sales, 0), 4)                 AS identified_share,
    COALESCE(n.new_customers, 0)                                                  AS new_customers,
    m.active_customers - COALESCE(n.new_customers, 0)                             AS returning_customers
FROM m
LEFT JOIN newc n USING (year_month)
WHERE m.year_month <= '2011-11'
ORDER BY m.year_month;

-- ---------- Q3.2 Year-on-year bridge (FY = Dec–Nov, 12 complete months each) ---------
-- Decomposes revenue into Customers x Orders/Customer x AOV for IDENTIFIED customers,
-- because only they can be counted. Guests shown separately.
CREATE OR REPLACE TABLE kpi_fy_comparison AS
WITH o AS (
    SELECT f.*, d.fiscal_year
    FROM fact_orders f
    JOIN dim_date d ON d.date_key = f.order_date
    WHERE d.fiscal_year IN ('FY2010', 'FY2011')
)
SELECT
    fiscal_year,
    SUM(order_value)                                                              AS net_merch_revenue,
    SUM(order_value) FILTER (WHERE order_type = 'sale')                           AS gross_merch_sales,
    SUM(order_value) FILTER (WHERE order_type = 'sale' AND NOT is_identified)     AS guest_sales,
    SUM(order_value) FILTER (WHERE order_type = 'sale' AND is_identified)         AS identified_sales,
    COUNT(DISTINCT customer_id) FILTER (WHERE order_type = 'sale')                AS active_customers,
    COUNT(*) FILTER (WHERE order_type = 'sale' AND is_identified)                 AS identified_orders,
    ROUND(COUNT(*) FILTER (WHERE order_type = 'sale' AND is_identified) * 1.0
          / COUNT(DISTINCT customer_id) FILTER (WHERE order_type = 'sale'), 3)    AS orders_per_customer,
    ROUND(SUM(order_value) FILTER (WHERE order_type = 'sale' AND is_identified)
          / COUNT(*) FILTER (WHERE order_type = 'sale' AND is_identified), 2)     AS identified_aov,
    ROUND(-SUM(order_value) FILTER (WHERE order_type = 'cancellation')
          / SUM(order_value) FILTER (WHERE order_type = 'sale'), 4)               AS return_rate
FROM o
GROUP BY fiscal_year
ORDER BY fiscal_year;

-- ---------- Q3.3 Customer retention year-over-year ----------------------------------
-- Of customers active in FY2010, how many bought again in FY2011, and how much did
-- the retained base spend vs the prior year (net revenue retention, NRR)?
CREATE OR REPLACE TABLE kpi_yoy_retention AS
WITH cy AS (
    -- Active = placed at least one (non-reversed) sale order in the year.
    -- Revenue = net of that year's returns.
    SELECT f.customer_id, d.fiscal_year, SUM(f.order_value) AS rev
    FROM fact_orders f JOIN dim_date d ON d.date_key = f.order_date
    WHERE f.is_identified AND d.fiscal_year IN ('FY2010','FY2011')
    GROUP BY 1, 2
    HAVING COUNT(*) FILTER (WHERE f.order_type = 'sale') > 0
),
p AS (
    SELECT customer_id,
           SUM(rev) FILTER (WHERE fiscal_year = 'FY2010') AS rev_fy10,
           SUM(rev) FILTER (WHERE fiscal_year = 'FY2011') AS rev_fy11
    FROM cy GROUP BY customer_id
)
SELECT
    COUNT(*) FILTER (WHERE rev_fy10 IS NOT NULL)                                  AS customers_fy10,
    COUNT(*) FILTER (WHERE rev_fy10 IS NOT NULL AND rev_fy11 IS NOT NULL)         AS retained_customers,
    ROUND(COUNT(*) FILTER (WHERE rev_fy10 IS NOT NULL AND rev_fy11 IS NOT NULL) * 1.0
          / COUNT(*) FILTER (WHERE rev_fy10 IS NOT NULL), 4)                      AS customer_retention_rate,
    COUNT(*) FILTER (WHERE rev_fy10 IS NULL AND rev_fy11 IS NOT NULL)             AS new_or_reactivated_fy11,
    SUM(rev_fy10)                                                                 AS revenue_fy10,
    SUM(rev_fy11) FILTER (WHERE rev_fy10 IS NOT NULL)                             AS revenue_fy11_from_fy10_base,
    ROUND(SUM(rev_fy11) FILTER (WHERE rev_fy10 IS NOT NULL) / SUM(rev_fy10), 4)   AS net_revenue_retention,
    SUM(rev_fy10) FILTER (WHERE rev_fy11 IS NULL)                                 AS revenue_lost_from_churned
FROM p;

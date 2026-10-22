-- =====================================================================================
-- 07_concentration_products_markets.sql
-- Business questions:
--   Q7.1 How dependent is revenue on a small number of customers? (key-account risk)
--   Q7.2 Which products drive revenue, and which are returned disproportionately?
--   Q7.3 How much revenue comes from outside the UK, and how does it behave?
-- =====================================================================================

-- ---------- Q7.1 Customer concentration (Pareto) --------------------------------------
CREATE OR REPLACE TABLE customer_concentration AS
WITH c AS (
    SELECT customer_id, SUM(revenue) AS rev
    FROM v_customer_lines GROUP BY customer_id HAVING SUM(revenue) > 0
),
r AS (
    SELECT customer_id, rev,
           ROW_NUMBER() OVER (ORDER BY rev DESC)                          AS rnk,
           COUNT(*) OVER ()                                               AS n,
           SUM(rev) OVER (ORDER BY rev DESC ROWS UNBOUNDED PRECEDING)     AS cum_rev,
           SUM(rev) OVER ()                                               AS tot
    FROM c
)
SELECT
    band,
    MAX(cum_share) AS cumulative_revenue_share
FROM (
    SELECT rnk * 1.0 / n AS pct_rank, cum_rev / tot AS cum_share,
           CASE WHEN rnk <= 10 THEN 'Top 10 customers'
                WHEN rnk * 1.0 / n <= 0.01 THEN 'Top 1%'
                WHEN rnk * 1.0 / n <= 0.05 THEN 'Top 5%'
                WHEN rnk * 1.0 / n <= 0.10 THEN 'Top 10%'
                WHEN rnk * 1.0 / n <= 0.20 THEN 'Top 20%'
                WHEN rnk * 1.0 / n <= 0.50 THEN 'Top 50%'
                ELSE 'All' END AS band
    FROM r
)
GROUP BY band
ORDER BY cumulative_revenue_share;

-- ---------- Q7.2 Product performance & return rates ---------------------------------
CREATE OR REPLACE TABLE product_performance AS
SELECT
    l.stock_code,
    p.product_name,
    SUM(l.revenue) FILTER (WHERE l.line_type = 'sale')                    AS gross_sales,
    -SUM(l.revenue) FILTER (WHERE l.line_type = 'cancellation')           AS returns_value,
    SUM(l.revenue)                                                        AS net_revenue,
    COUNT(DISTINCT l.customer_id)                                         AS buyers,
    COUNT(DISTINCT l.invoice) FILTER (WHERE l.line_type = 'sale')         AS orders,
    ROUND(COALESCE(-SUM(l.revenue) FILTER (WHERE l.line_type = 'cancellation'), 0)
          / NULLIF(SUM(l.revenue) FILTER (WHERE l.line_type = 'sale'), 0), 4) AS return_rate
FROM stg_sales_lines l
JOIN dim_product p USING (stock_code)
WHERE l.is_product AND l.line_type IN ('sale','cancellation') AND NOT l.is_reversed
GROUP BY l.stock_code, p.product_name;

-- ---------- Q7.3 Market mix (identified customers, by home country region) ------------
CREATE OR REPLACE TABLE market_mix AS
SELECT
    dc.region,
    COUNT(DISTINCT r.customer_id)                                         AS customers,
    ROUND(SUM(r.monetary), 0)                                             AS net_revenue,
    ROUND(SUM(r.monetary) / SUM(SUM(r.monetary)) OVER (), 4)              AS pct_revenue,
    ROUND(AVG(r.frequency), 2)                                            AS avg_orders,
    ROUND(MEDIAN(r.monetary), 0)                                          AS median_customer_revenue
FROM rfm_scores r
JOIN dim_customer c USING (customer_id)
JOIN dim_country dc ON dc.country = c.country
GROUP BY dc.region
ORDER BY net_revenue DESC;

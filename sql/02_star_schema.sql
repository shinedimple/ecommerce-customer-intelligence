-- =====================================================================================
-- 02_star_schema.sql — Analytical data model (Kimball star schema)
-- -------------------------------------------------------------------------------------
-- Grain decisions (WHY):
--   fact_sales_lines : one row per invoice line. Needed for product mix & returns.
--   fact_orders      : one row per invoice (order). Needed for AOV, frequency, cadence.
--   dim_customer     : one row per identified customer. Guests have NO row — they
--                      cannot be tracked across orders, which is the core limitation.
--   dim_product, dim_date, dim_country : conformed dimensions for slicing.
-- Customer-level scores (RFM, CLV, risk, segment) are produced in Python and joined
-- to dim_customer as `customer_scores` (see src/cie/export_powerbi.py).
-- =====================================================================================

-- ---------- Canonical analytical view (mirrors src/cie/clean.py::analysis_lines) -----
-- Identified customers, merchandise only, sales + unmatched cancellations (genuine
-- partial returns), excluding order/cancel pairs that fully reverse each other.
CREATE OR REPLACE VIEW v_customer_lines AS
SELECT *
FROM stg_sales_lines
WHERE is_identified
  AND is_product
  AND line_type IN ('sale', 'cancellation')
  AND NOT is_reversed;

-- ---------- dim_date ------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_date AS
SELECT
    CAST(d AS DATE)                                   AS date_key,
    EXTRACT(year FROM d)                              AS calendar_year,
    EXTRACT(quarter FROM d)                           AS calendar_quarter,
    EXTRACT(month FROM d)                             AS month_num,
    strftime(d, '%Y-%m')                              AS year_month,
    strftime(d, '%b %Y')                              AS month_label,
    EXTRACT(isodow FROM d)                            AS iso_day_of_week,   -- 1 = Mon
    strftime(d, '%a')                                 AS day_name,
    CASE WHEN CAST(d AS DATE) BETWEEN DATE '2009-12-01' AND DATE '2010-11-30' THEN 'FY2010'
         WHEN CAST(d AS DATE) BETWEEN DATE '2010-12-01' AND DATE '2011-11-30' THEN 'FY2011'
         ELSE 'Partial (Dec-2011)' END                AS fiscal_year,        -- Dec–Nov
    CAST(d AS DATE) > DATE '2011-11-30'               AS is_partial_month
FROM generate_series(TIMESTAMP '2009-12-01', TIMESTAMP '2011-12-31', INTERVAL 1 DAY) AS t(d);

-- ---------- dim_product ---------------------------------------------------------------
CREATE OR REPLACE TABLE dim_product AS
SELECT
    stock_code,
    ANY_VALUE(product_name)                                            AS product_name,
    ANY_VALUE(item_type)                                               AS item_type,
    BOOL_AND(is_product)                                               AS is_product,
    MIN(invoice_date)                                                  AS first_sold_date,
    MAX(invoice_date)                                                  AS last_sold_date,
    MEDIAN(unit_price) FILTER (WHERE line_type = 'sale')               AS median_unit_price
FROM stg_sales_lines
GROUP BY stock_code;

-- ---------- dim_country ---------------------------------------------------------------
CREATE OR REPLACE TABLE dim_country AS
SELECT
    country,
    CASE WHEN country = 'United Kingdom' THEN 'UK'
         WHEN country IN ('EIRE','Netherlands','Germany','France','Spain','Belgium',
                          'Switzerland','Portugal','Italy','Norway','Sweden','Denmark',
                          'Finland','Austria','Channel Islands','Poland','Greece','Cyprus',
                          'Iceland','Malta','Lithuania','Czech Republic','European Community')
              THEN 'Europe (ex-UK)'
         WHEN country = 'Unspecified' THEN 'Unspecified'
         ELSE 'Rest of World' END AS region
FROM (SELECT DISTINCT country FROM stg_sales_lines);

-- ---------- fact_orders (invoice grain, merchandise only, reversals removed) ---------
CREATE OR REPLACE TABLE fact_orders AS
SELECT
    invoice,
    customer_id,
    is_identified,
    ANY_VALUE(country)                                    AS country,
    MIN(invoice_ts)                                       AS order_ts,
    CAST(MIN(invoice_ts) AS DATE)                         AS order_date,
    ANY_VALUE(line_type)                                  AS order_type,   -- sale | cancellation
    COUNT(*)                                              AS line_count,
    COUNT(DISTINCT stock_code)                            AS distinct_products,
    SUM(quantity)                                         AS units,
    SUM(revenue)                                          AS order_value
FROM stg_sales_lines
WHERE is_product
  AND line_type IN ('sale', 'cancellation')
  AND NOT is_reversed
GROUP BY invoice, customer_id, is_identified;

-- ---------- dim_customer (identified customers only) --------------------------------
CREATE OR REPLACE TABLE dim_customer AS
WITH o AS (
    SELECT * FROM fact_orders WHERE is_identified AND order_type = 'sale'
)
SELECT
    o.customer_id,
    ANY_VALUE(l.customer_country)                         AS country,
    MIN(o.order_ts)                                       AS first_order_ts,
    MAX(o.order_ts)                                       AS last_order_ts,
    strftime(MIN(o.order_ts), '%Y-%m')                    AS cohort_month,
    -- Left-censoring flag: data starts 1 Dec 2009, so a customer "first seen" in
    -- Dec 2009 may well be an existing customer. Treat that cohort with caution.
    MIN(o.order_ts) < TIMESTAMP '2010-01-01'              AS is_left_censored
FROM o
JOIN (SELECT DISTINCT customer_id, customer_country FROM v_customer_lines) l
  ON l.customer_id = o.customer_id
GROUP BY o.customer_id;

-- =====================================================================================
-- 01_staging.sql — Load the cleaned line-level ledger into the warehouse
-- -------------------------------------------------------------------------------------
-- WHY: Python owns the messy parsing (Excel, mixed-type IDs, reversal matching).
--      SQL owns modelling and business logic from here on, so an analyst who only
--      knows SQL can audit every KPI.
-- Engine: DuckDB (ANSI-leaning). Portability notes in sql/README.md.
-- Run from the project root: python -m src.cie.warehouse
-- =====================================================================================

CREATE OR REPLACE TABLE stg_sales_lines AS
SELECT *
FROM read_parquet('data/processed/fact_sales_lines.parquet');

-- Parameters table: one row, used by every downstream query so the "as-of" date is
-- defined exactly once. Snapshot = day after the last recorded transaction.
CREATE OR REPLACE TABLE params AS
SELECT
    CAST(MAX(invoice_ts) AS DATE) + INTERVAL 1 DAY           AS snapshot_date,
    DATE '2011-11-30'                                         AS last_full_month_end,
    -- "Fiscal" years are defined Dec–Nov so both years contain 12 COMPLETE months.
    DATE '2009-12-01'                                         AS fy1_start,
    DATE '2010-11-30'                                         AS fy1_end,
    DATE '2010-12-01'                                         AS fy2_start,
    DATE '2011-11-30'                                         AS fy2_end
FROM stg_sales_lines;

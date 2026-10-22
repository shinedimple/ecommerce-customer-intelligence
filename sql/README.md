# SQL Layer

Run all scripts in order (from the project root): `python -m src.cie.warehouse`
Engine: **DuckDB** (in-process, reads Parquet directly). Result tables are exported to
`reports/tables/sql_*.csv`.

| Script | Builds | Business question |
|---|---|---|
| `01_staging.sql` | `stg_sales_lines`, `params` | Load cleaned ledger; define snapshot & fiscal years once |
| `02_star_schema.sql` | `v_customer_lines`, `dim_date`, `dim_product`, `dim_country`, `fact_orders`, `dim_customer` | Analytical data model |
| `03_kpi_overview.sql` | `kpi_monthly`, `kpi_fy_comparison`, `kpi_yoy_retention` | Is the business growing, and why? Are we keeping customers? |
| `04_rfm.sql` | `rfm_base`, `rfm_scores`, `rfm_segment_summary` | Who are our best / slipping / lost customers? |
| `05_cohorts.sql` | `cohort_activity`, `cohort_retention`, `cohort_avg_curve`, `cohort_revenue` | When do new customers drop off? |
| `06_churn_risk_rules.sql` | `churn_risk_rules`, `churn_risk_rules_summary` | Who is overdue vs their own buying rhythm? |
| `07_concentration_products_markets.sql` | `customer_concentration`, `product_performance`, `market_mix` | Key-account dependency; product returns; markets |
| `08_reconciliation.sql` | `revenue_bridge` | Why does this revenue differ from Finance's? (closes to £0.00) |

## SQL techniques demonstrated
Window functions (`NTILE`, `LAG`, `ROW_NUMBER`, running `SUM … ROWS UNBOUNDED PRECEDING`),
`FILTER (WHERE …)` conditional aggregation, CTE chains, date spines (`generate_series`),
cohort indexing with `DATE_DIFF('month', …)`, reconciliation with a zero-check row.

## Portability notes
| DuckDB construct | PostgreSQL | SQL Server / Snowflake |
|---|---|---|
| `read_parquet('…')` | load via `COPY`/external table | external stage / `OPENROWSET` |
| `SUM(x) FILTER (WHERE c)` | identical | `SUM(CASE WHEN c THEN x END)` |
| `DATE_DIFF('day', a, b)` | `b::date - a::date` | `DATEDIFF(day, a, b)` |
| `strftime(ts, '%Y-%m')` | `to_char(ts, 'YYYY-MM')` | `FORMAT(ts, 'yyyy-MM')` / `TO_CHAR` |
| `MEDIAN(x)` | `percentile_cont(0.5) WITHIN GROUP (ORDER BY x)` | same / `MEDIAN(x)` (Snowflake) |
| `ANY_VALUE(x)` | `MIN(x)` | `MIN(x)` / `ANY_VALUE(x)` |
| `CREATE OR REPLACE TABLE` | `DROP TABLE IF EXISTS` + `CREATE TABLE` | `CREATE OR ALTER` / identical (Snowflake) |

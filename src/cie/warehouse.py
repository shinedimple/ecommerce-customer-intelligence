"""
Step 4 — Build the warehouse and run the SQL analysis layer.

Executes sql/0*.sql in filename order against a local DuckDB file, then exports the
business-question tables to reports/tables/sql_<table>.csv for review.
"""
import os

import duckdb
import pandas as pd

from . import config as C

EXPORT_TABLES = [
    "kpi_monthly", "kpi_fy_comparison", "kpi_yoy_retention",
    "rfm_segment_summary", "cohort_retention", "cohort_avg_curve", "cohort_revenue",
    "churn_risk_rules_summary", "customer_concentration", "market_mix", "revenue_bridge",
]


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(C.WAREHOUSE))


def build() -> None:
    os.chdir(C.ROOT)  # SQL uses project-relative parquet paths
    con = connect()
    for f in sorted(C.SQL_DIR.glob("0*.sql")):
        con.execute(f.read_text())
        print(f"  ran {f.name}")
    for t in EXPORT_TABLES:
        con.table(t).df().to_csv(C.TABLES / f"sql_{t}.csv", index=False)
    con.close()


def query(sql: str) -> pd.DataFrame:
    con = connect()
    try:
        return con.execute(sql).df()
    finally:
        con.close()


if __name__ == "__main__":
    build()

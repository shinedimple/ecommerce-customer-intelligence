"""
Step 18 (data side) — Export the Power BI model.

Star schema (relationships defined in docs/04_dashboard_spec.md):
  fact_orders        (invoice grain)      -> dim_customer, dim_date, dim_country
  fact_sales_lines   (line grain, parquet) -> dim_product, dim_customer, dim_date
  dim_customer       (1 row / customer, includes all scores & segments = "customer 360")
  dim_product, dim_date, dim_country
  seg_playbook       (1 row / management segment: objective, action, KPI)
  kpi_monthly, clv_validation, churn_calibration (pre-aggregated support tables)

WHY pre-compute scores in Python instead of DAX: RFM quintiles, CLV and churn
probabilities are model outputs. Recomputing them in DAX would create a second,
divergent definition. Power BI's job is slicing and presenting, not modelling.
"""
import pandas as pd

from . import config as C
from .warehouse import query

OUT = C.POWERBI_DATA


def run():
    fo = query("SELECT * FROM fact_orders")
    fo.to_csv(OUT / "fact_orders.csv", index=False)

    lines = pd.read_parquet(C.CLEAN_PARQUET, columns=[
        "line_id", "invoice", "invoice_date", "stock_code", "quantity", "unit_price",
        "revenue", "customer_id", "is_identified", "country", "line_type", "item_type",
        "is_product", "is_reversed"])
    lines.to_parquet(OUT / "fact_sales_lines.parquet", index=False)

    for t in ("dim_date", "dim_product", "dim_country"):
        query(f"SELECT * FROM {t}").to_csv(OUT / f"{t}.csv", index=False)

    c = pd.read_parquet(C.DATA_PROCESSED / "customer_360.parquet").reset_index()
    keep = ["customer_id", "country", "cohort_month", "first_order_ts", "is_left_censored",
            "recency_days", "frequency", "monetary", "r_score", "f_score", "m_score",
            "rfm_cell", "rfm_segment", "clv_12m", "exp_purchases_12m",
            "exp_spend_per_purchase", "p_alive", "churn_prob_12m", "revenue_t12m",
            "orders_t12m", "avg_gap_days", "cadence_status", "is_active_12m", "is_new",
            "value_tier", "risk_tier", "at_risk_flag", "at_risk_reason", "revenue_at_risk",
            "management_segment"]
    c[keep].rename(columns={"monetary": "lifetime_net_revenue",
                            "frequency": "lifetime_orders"}).to_csv(
        OUT / "dim_customer.csv", index=False)

    pd.read_csv(C.TABLES / "action_playbook.csv").to_csv(OUT / "seg_playbook.csv", index=False)
    for src, dst in (("sql_kpi_monthly", "kpi_monthly"),
                     ("clv_validation_by_decile", "clv_validation_by_decile"),
                     ("churn_calibration", "churn_calibration"),
                     ("sql_cohort_retention", "cohort_retention"),
                     ("sql_revenue_bridge", "revenue_bridge")):
        pd.read_csv(C.TABLES / f"{src}.csv").to_csv(OUT / f"{dst}.csv", index=False)
    print(f"  Power BI tables written to {OUT.relative_to(C.ROOT)}")


if __name__ == "__main__":
    run()

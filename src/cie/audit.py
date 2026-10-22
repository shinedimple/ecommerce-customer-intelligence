"""
Step 3 — Data quality audit.

WHY: Management will make decisions off these numbers. Before any analysis we
quantify every data-quality issue in two currencies: ROWS affected and REVENUE
affected. A 22% missing-ID rate sounds alarming; knowing it is 15% of revenue tells
management exactly how much of the business customer analytics can and cannot see.

Outputs:
  reports/tables/data_quality_scorecard.csv
  reports/tables/non_product_codes.csv
  reports/tables/missing_id_by_month.csv
"""
import pandas as pd

from . import config as C
from .ingest import load_raw


def scorecard(raw: pd.DataFrame, clean: pd.DataFrame) -> pd.DataFrame:
    r = raw.copy()
    r["revenue"] = r.quantity * r.unit_price
    gross_sales = clean.loc[clean.line_type == "sale", "revenue"].sum()
    s1_inv = set(r.loc[r.source_sheet == "Year 2009-2010", "invoice"])
    overlap = (r.source_sheet == "Year 2010-2011") & r.invoice.isin(s1_inv)

    sale = clean[clean.line_type == "sale"]
    r2 = r[~overlap]
    key = ["invoice", "stock_code", "description", "quantity", "invoice_ts",
           "unit_price", "customer_id", "country"]
    dup = r2.duplicated(subset=key, keep="first")
    rows = [
        ("Completeness", "Missing Customer ID (all lines)",
         int(clean.customer_id.isna().sum()), len(clean),
         sale.loc[~sale.is_identified, "revenue"].sum(),
         "Cannot attribute to a customer. Excluded from RFM/CLV/churn; kept in company totals."),
        ("Completeness", "Missing Description", int(raw.description.isna().sum()), len(raw),
         0.0, "All are zero-price stock adjustments; no revenue impact."),
        ("Uniqueness", "Invoices duplicated across the two sheets (1–9 Dec 2010)",
         int(overlap.sum()), len(raw), r.loc[overlap, "revenue"].sum(),
         "Removed (R1). Otherwise these invoices are counted twice."),
        ("Uniqueness", "Exact duplicate lines within a sheet",
         int(dup.sum()), len(raw), r2.loc[dup, "revenue"].sum(),
         "Removed (R2). ASSUMPTION: system double-posts."),
        ("Validity", "Cancellation lines (invoice prefix 'C')",
         int((clean.line_type == "cancellation").sum()), len(clean),
         clean.loc[clean.line_type == "cancellation", "revenue"].sum(),
         "Kept as negative revenue. Matched reversals flagged (R5/R5b)."),
        ("Validity", "Cancellations matched to the exact sale they reverse",
         int((clean.is_reversed & (clean.line_type == "cancellation")).sum()), len(clean),
         clean.loc[clean.is_reversed & (clean.line_type == "sale"), "revenue"].sum(),
         "Pairs excluded from order counts; revenue nets to zero either way."),
        ("Validity", "Bad-debt write-off adjustments (prefix 'A')",
         int((clean.line_type == "bad_debt_adjustment").sum()), len(clean),
         clean.loc[clean.line_type == "bad_debt_adjustment", "revenue"].sum(),
         "Finance item; excluded from customer analytics."),
        ("Validity", "Negative-quantity stock adjustments (damaged/lost, price 0)",
         int((clean.line_type == "stock_adjustment").sum()), len(clean), 0.0,
         "Inventory events, not sales. Excluded."),
        ("Validity", "Zero-price lines with positive quantity",
         int((clean.line_type == "zero_price_line").sum()), len(clean), 0.0,
         "Free/sample items or keying errors. Excluded from revenue metrics."),
        ("Consistency", "Non-merchandise stock codes (postage, fees, manual, discount…)",
         int((~clean.is_product).sum()), len(clean),
         clean.loc[~clean.is_product & clean.line_type.isin(["sale", "cancellation"]),
                   "revenue"].sum(),
         "Kept for finance reconciliation; excluded from product & customer metrics."),
        ("Consistency", "Customers recorded in >1 country",
         int(clean[clean.is_identified].groupby("customer_id").country.nunique().gt(1).sum()),
         int(clean.customer_id.nunique()), 0.0, "Assigned modal country (R7)."),
        ("Timeliness", "Partial final month (Dec 2011 ends on the 9th)",
         int(clean.is_partial_month.sum()), len(clean),
         sale.loc[sale.is_partial_month, "revenue"].sum(),
         "Excluded from month-on-month trend charts; included in customer histories."),
    ]
    sc = pd.DataFrame(rows, columns=["dimension", "issue", "rows_affected", "rows_base",
                                     "revenue_affected_gbp", "treatment"])
    sc["pct_rows"] = (sc.rows_affected / sc.rows_base).round(4)
    sc["pct_of_gross_sales"] = (sc.revenue_affected_gbp / gross_sales).round(4)
    return sc


def run(clean: pd.DataFrame | None = None) -> pd.DataFrame:
    raw = load_raw()
    clean = pd.read_parquet(C.CLEAN_PARQUET) if clean is None else clean
    sc = scorecard(raw, clean)
    sc.to_csv(C.TABLES / "data_quality_scorecard.csv", index=False)

    npc = (clean[~clean.is_product]
           .groupby(["item_type", "stock_code"])
           .agg(lines=("revenue", "size"), net_revenue=("revenue", "sum"),
                example_description=("description", "first"))
           .reset_index().sort_values("lines", ascending=False))
    npc.to_csv(C.TABLES / "non_product_codes.csv", index=False)

    s = clean[(clean.line_type == "sale")]
    mm = (s.groupby("year_month")
          .apply(lambda g: pd.Series({
              "lines": len(g),
              "pct_lines_missing_id": (~g.is_identified).mean(),
              "pct_revenue_missing_id": g.loc[~g.is_identified, "revenue"].sum() / g.revenue.sum(),
          }), include_groups=False).reset_index())
    mm.to_csv(C.TABLES / "missing_id_by_month.csv", index=False)
    print(sc[["issue", "rows_affected", "pct_rows", "revenue_affected_gbp",
              "pct_of_gross_sales"]].to_string(index=False))
    return sc


if __name__ == "__main__":
    run()

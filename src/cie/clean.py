"""
Step 2 — Cleaning & transformation.

Design principle: FLAG, DON'T DELETE (except true duplicates).
Finance must be able to reconcile back to the raw ledger, so every raw line survives
into the fact table with a `line_type` and `item_type`. Analytical views then filter
on those flags. Only rows that are provably duplicated are removed, and every removal
is counted in a cleaning log.

Rules (each is justified in docs/assumptions_log.md):
  R1  Remove cross-sheet overlap: invoices dated 1–9 Dec 2010 appear in BOTH sheets.
  R2  Remove exact duplicate lines within a sheet (same invoice, product, qty, price,
      timestamp, customer). ASSUMPTION: these are system double-posts, not two
      identical scans — the data cannot prove this either way.
  R3  Classify each line: sale / cancellation / bad_debt_adjustment /
      stock_adjustment / zero_price_line.
  R4  Classify each item: product vs non-product (postage, fees, manual, discount…).
  R5  Match each cancellation line to the most recent earlier sale of the same
      customer + product + quantity + price, and flag both as `is_reversed`.
      WHY: several very large orders (up to 80,995 units) were keyed and cancelled
      within minutes. Netting them preserves revenue totals, but they would still
      inflate ORDER COUNTS and so distort RFM and CLV. Reversal matching fixes that.
  R6  Standardise descriptions (one canonical description per stock code).
  R7  Assign each customer one home country (modal country; 13 customers have >1).
"""
import numpy as np
import pandas as pd

from . import config as C
from .ingest import load_raw

NON_PRODUCT_MAP = {
    "POST": "postage", "DOT": "postage", "C2": "postage", "C3": "postage",
    "M": "manual_adjustment", "m": "manual_adjustment",
    "ADJUST": "manual_adjustment", "ADJUST2": "manual_adjustment",
    "D": "discount", "S": "samples", "B": "bad_debt",
    "BANK CHARGES": "fees", "AMAZONFEE": "fees", "CRUK": "fees",
    "TEST001": "test", "TEST002": "test",
}


def _item_type(code: pd.Series) -> pd.Series:
    code = code.astype("string").str.strip()
    cat = code.map(NON_PRODUCT_MAP)
    voucher = code.str.lower().str.startswith("gift")
    cat = cat.mask(voucher & cat.isna(), "gift_voucher")
    return cat.fillna("product")


def clean(raw: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = load_raw() if raw is None else raw
    log = []

    def note(rule, desc, before, after, extra=None):
        log.append({"rule": rule, "description": desc, "rows_before": before,
                    "rows_after": after, "rows_removed": before - after, "note": extra})

    df = raw.copy()
    df["stock_code"] = df["stock_code"].astype("string").str.strip()
    df["invoice"] = df["invoice"].astype("string").str.strip()

    # R1 — cross-sheet overlap -------------------------------------------------------
    s1_invoices = set(df.loc[df.source_sheet == "Year 2009-2010", "invoice"])
    overlap = (df.source_sheet == "Year 2010-2011") & df.invoice.isin(s1_invoices)
    n = len(df)
    df = df[~overlap]
    note("R1", "Drop invoices duplicated across the two sheets (1–9 Dec 2010)", n, len(df),
         f"{int(overlap.sum()):,} lines across "
         f"{raw.loc[overlap.values, 'invoice'].nunique():,} invoices")

    # R2 — exact duplicates within sheet ---------------------------------------------
    key = ["invoice", "stock_code", "description", "quantity", "invoice_ts",
           "unit_price", "customer_id", "country"]
    dup = df.duplicated(subset=key, keep="first")
    n = len(df)
    dup_rev = (df.loc[dup, "quantity"] * df.loc[dup, "unit_price"]).sum()
    df = df[~dup]
    note("R2", "Drop exact duplicate lines within a sheet", n, len(df),
         f"net revenue in removed lines: £{dup_rev:,.0f}")

    # R3 — line type -----------------------------------------------------------------
    first = df.invoice.str[0]
    lt = np.select(
        [first == "C",
         first == "A",
         (df.quantity < 0) & (df.unit_price == 0),
         (df.unit_price == 0),
         (df.quantity > 0) & (df.unit_price > 0)],
        ["cancellation", "bad_debt_adjustment", "stock_adjustment",
         "zero_price_line", "sale"],
        default="other",
    )
    df["line_type"] = lt
    df["item_type"] = _item_type(df.stock_code)
    df["is_product"] = df.item_type.eq("product")
    df["revenue"] = (df.quantity * df.unit_price).round(4)
    df["is_identified"] = df.customer_id.notna()

    # R5 — reversal matching ---------------------------------------------------------
    df = df.reset_index(drop=True)
    df["line_id"] = np.arange(len(df))
    df["is_reversed"] = False
    sales = df[(df.line_type == "sale") & df.is_identified][
        ["line_id", "customer_id", "stock_code", "quantity", "unit_price", "invoice_ts"]]
    canc = df[(df.line_type == "cancellation") & df.is_identified][
        ["line_id", "customer_id", "stock_code", "quantity", "unit_price", "invoice_ts"]].copy()
    canc["quantity"] = -canc["quantity"]
    sales = sales.sort_values("invoice_ts")
    canc = canc.sort_values("invoice_ts")
    m = pd.merge_asof(
        canc, sales, on="invoice_ts", by=["customer_id", "stock_code", "quantity", "unit_price"],
        direction="backward", suffixes=("_c", "_s"),
    ).dropna(subset=["line_id_s"])
    # A sale line may only be reversed once
    m = m.drop_duplicates(subset="line_id_s", keep="first")
    df.loc[df.line_id.isin(m.line_id_c), "is_reversed"] = True
    df.loc[df.line_id.isin(m.line_id_s.astype(int)), "is_reversed"] = True
    n_canc = int((df.line_type == "cancellation").sum())
    note("R5", "Flag cancellations matched to the sale they reverse (not removed)",
         len(df), len(df),
         f"{len(m):,} of {n_canc:,} cancellation lines matched to an original sale")

    # R5b — manual-code ('M') credits that exactly reverse a product sale ------------
    # e.g. customer 15098: £38,970 order credited back via stock code 'M' 3 minutes later.
    s2 = df[(df.line_type == "sale") & df.is_identified & df.is_product & ~df.is_reversed][
        ["line_id", "customer_id", "revenue", "invoice_ts"]].copy()
    s2["amt"] = s2.revenue.round(2)
    # Only credits not already paired by R5 (a credit may reverse at most one sale)
    c2 = df[(df.line_type == "cancellation") & df.is_identified & ~df.is_reversed
            & (df.item_type == "manual_adjustment")][
        ["line_id", "customer_id", "revenue", "invoice_ts"]].copy()
    c2["amt"] = (-c2.revenue).round(2)
    m2 = pd.merge_asof(
        c2.sort_values("invoice_ts"), s2.sort_values("invoice_ts"), on="invoice_ts",
        by=["customer_id", "amt"], direction="backward",
        tolerance=pd.Timedelta("7D"), suffixes=("_c", "_s"),
    ).dropna(subset=["line_id_s"]).drop_duplicates(subset="line_id_s")
    df.loc[df.line_id.isin(m2.line_id_c), "is_reversed"] = True
    df.loc[df.line_id.isin(m2.line_id_s.astype(int)), "is_reversed"] = True
    note("R5b", "Flag manual ('M') credits that exactly reverse a product sale within 7 days",
         len(df), len(df),
         f"{len(m2):,} pairs, £{m2.revenue_s.sum():,.0f} of sales reversed")

    # R6 — canonical description -----------------------------------------------------
    df["description"] = df.description.astype("string").str.strip().str.upper()
    prod_desc = (df[df.line_type == "sale"].dropna(subset=["description"])
                 .groupby(["stock_code", "description"]).size().rename("n").reset_index()
                 .sort_values(["stock_code", "n"], ascending=[True, False])
                 .drop_duplicates("stock_code").set_index("stock_code")["description"])
    df["product_name"] = df.stock_code.map(prod_desc).fillna(df.description)

    # R7 — customer home country -----------------------------------------------------
    home = (df[df.is_identified].groupby(["customer_id", "country"]).size()
            .rename("n").reset_index().sort_values(["customer_id", "n"], ascending=[True, False])
            .drop_duplicates("customer_id").set_index("customer_id")["country"])
    df["customer_country"] = df.customer_id.map(home)

    # Calendar helpers
    df["invoice_date"] = df.invoice_ts.dt.normalize()
    df["year_month"] = df.invoice_ts.dt.to_period("M").astype(str)
    df["is_partial_month"] = df.invoice_ts.dt.to_period("M") > C.LAST_FULL_MONTH

    cols = ["line_id", "invoice", "invoice_ts", "invoice_date", "year_month",
            "is_partial_month", "stock_code", "product_name", "description", "quantity",
            "unit_price", "revenue", "customer_id", "is_identified", "country",
            "customer_country", "line_type", "item_type", "is_product", "is_reversed",
            "source_sheet", "source_row"]
    df = df[cols]
    log = pd.DataFrame(log)
    return df, log


def analysis_lines(df: pd.DataFrame) -> pd.DataFrame:
    """
    The canonical customer-analytics view (mirrors sql/02_views.sql :: v_customer_lines).
    Identified customers, merchandise only, sales + unmatched cancellations
    (i.e. genuine partial returns), excluding reversed pairs.
    """
    return df[
        df.is_identified
        & df.is_product
        & df.line_type.isin(["sale", "cancellation"])
        & ~df.is_reversed
    ].copy()


def run() -> pd.DataFrame:
    df, log = clean()
    df.to_parquet(C.CLEAN_PARQUET, index=False)
    log.to_csv(C.TABLES / "cleaning_log.csv", index=False)
    print(log.to_string(index=False))
    return df


if __name__ == "__main__":
    run()

"""
Step 10 — RFM segmentation (Python mirror of sql/04_rfm.sql).

WHY two implementations: SQL is what a BI team would run in production; Python is
what the models consume. tests/test_consistency.py asserts they produce identical
segment counts, which guards against silent logic drift between the two.
See sql/04_rfm.sql for the scoring rationale (F uses business bins, not quintiles).
"""
import numpy as np
import pandas as pd

from . import config as C
from .features import load_lines


def _ntile(s: pd.Series, n: int = 5) -> pd.Series:
    """SQL NTILE(n) OVER (ORDER BY s, customer_id): equal-count buckets, ties by id."""
    order = s.reset_index().sort_values([s.name, "customer_id"]).customer_id
    k = len(order)
    # SQL NTILE: first (k % n) buckets get one extra row
    base, extra = divmod(k, n)
    sizes = [base + (1 if i < extra else 0) for i in range(n)]
    labels = np.repeat(np.arange(1, n + 1), sizes)
    return pd.Series(labels, index=order.values).reindex(s.index)


def segment(r: int, f: int) -> str:
    if r >= 5 and f >= 4: return "Champions"
    if r >= 3 and f >= 4: return "Loyal Customers"
    if r >= 4 and f in (2, 3): return "Potential Loyalists"
    if r == 5 and f == 1: return "New Customers"
    if r == 4 and f == 1: return "Promising"
    if r == 3 and f == 3: return "Need Attention"
    if r == 3 and f in (1, 2): return "About to Sleep"
    if r <= 2 and f == 5: return "Cannot Lose Them"
    if r <= 2 and f in (3, 4): return "At Risk"
    return "Hibernating"


def compute(lines: pd.DataFrame) -> pd.DataFrame:
    snapshot = lines.invoice_ts.max().normalize() + pd.Timedelta(days=1)
    g = lines.groupby("customer_id")
    base = pd.DataFrame({
        "recency_days": (snapshot - g.invoice_ts.max().dt.normalize()).dt.days,  # calendar days, as SQL DATE_DIFF
        "frequency": lines[lines.line_type == "sale"].groupby("customer_id").invoice.nunique(),
        "monetary": g.revenue.sum(),
    })
    base = base[base.frequency.fillna(0) > 0].copy()
    base.index.name = "customer_id"
    base["r_score"] = 6 - _ntile(base.recency_days.rename("recency_days"))
    base["f_score"] = pd.cut(base.frequency, [0, 1, 2, 4, 9, np.inf], labels=[1, 2, 3, 4, 5]).astype(int)
    base["m_score"] = _ntile(base.monetary.rename("monetary"))
    base["rfm_cell"] = (base.r_score.astype(str) + base.f_score.astype(str) + base.m_score.astype(str))
    base["rfm_segment"] = [segment(r, f) for r, f in zip(base.r_score, base.f_score)]
    return base


def run(lines: pd.DataFrame | None = None) -> pd.DataFrame:
    lines = load_lines() if lines is None else lines
    rfm = compute(lines)
    rfm.to_parquet(C.DATA_PROCESSED / "customer_rfm.parquet")
    print(rfm.rfm_segment.value_counts().to_string())
    return rfm


if __name__ == "__main__":
    run()

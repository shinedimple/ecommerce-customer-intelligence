"""
Point-in-time customer features.

WHY this module exists: every model in the project (RFM, BG/NBD, churn) must be
computable "as of" any cutoff date using ONLY data before that date. Building the
features in one function with an explicit `cutoff` argument is what makes the
holdout validation honest (no future information leaks into the past).

Units: BG/NBD inputs are in WEEKS (numerically stabler optimisation than days).
A "purchase occasion" is a distinct DAY with a sale — several invoices on the same
day are one occasion (standard CLV practice; avoids counting split invoices twice).
"""
import numpy as np
import pandas as pd

from . import config as C
from .clean import analysis_lines


def load_lines() -> pd.DataFrame:
    df = pd.read_parquet(C.CLEAN_PARQUET)
    return analysis_lines(df)


def daily_transactions(lines: pd.DataFrame) -> pd.DataFrame:
    """One row per customer per purchase day: net merchandise value that day."""
    sales = lines[lines.line_type == "sale"]
    d = (sales.groupby(["customer_id", "invoice_date"])
         .agg(value=("revenue", "sum"), invoices=("invoice", "nunique"))
         .reset_index())
    return d


def clv_inputs(lines: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """BG/NBD + Gamma-Gamma inputs as of `cutoff` (inclusive)."""
    d = daily_transactions(lines[lines.invoice_ts <= cutoff])
    g = d.groupby("customer_id")
    first = g.invoice_date.min()
    last = g.invoice_date.max()
    n_days = g.size()
    cut = cutoff.normalize()
    out = pd.DataFrame({
        "frequency": n_days - 1,                                     # repeat occasions
        "recency": (last - first).dt.days / 7.0,                     # t_x (weeks)
        "T": ((cut - first).dt.days + 1) / 7.0,                      # age (weeks)
        "first_purchase": first,
        "last_purchase": last,
    })
    # Mean value of REPEAT occasions only (Gamma-Gamma convention: first purchase excluded)
    d = d.sort_values(["customer_id", "invoice_date"])
    d["occ"] = d.groupby("customer_id").cumcount()
    rep = d[d.occ > 0].groupby("customer_id").value.mean()
    out["monetary_value"] = rep.reindex(out.index).fillna(0.0)
    return out


def future_actuals(lines: pd.DataFrame, start: pd.Timestamp, days: int) -> pd.DataFrame:
    """Actual purchase occasions and net revenue in (start, start + days]."""
    end = start + pd.Timedelta(days=days)
    win = lines[(lines.invoice_ts > start) & (lines.invoice_ts <= end)]
    d = daily_transactions(win)
    occ = d.groupby("customer_id").size().rename("actual_purchases")
    rev = win.groupby("customer_id").revenue.sum().rename("actual_revenue")
    return pd.concat([occ, rev], axis=1).fillna(0.0)


def behavioural_features(lines: pd.DataFrame, cutoff: pd.Timestamp,
                         window_days: int = 365) -> pd.DataFrame:
    """
    Features for the supervised churn model, computed over a fixed trailing window so
    that models trained at different cutoffs see comparable inputs.
    Population: customers with >= 1 sale in the trailing window.
    """
    start = cutoff - pd.Timedelta(days=window_days)
    hist = lines[lines.invoice_ts <= cutoff]
    w = hist[hist.invoice_ts > start]
    sales_w = w[w.line_type == "sale"]
    pop = sales_w.customer_id.unique()

    d_all = daily_transactions(hist)
    d_all = d_all[d_all.customer_id.isin(pop)].sort_values(["customer_id", "invoice_date"])
    d_all["gap"] = d_all.groupby("customer_id").invoice_date.diff().dt.days
    gaps = d_all.groupby("customer_id").gap.agg(["mean", "std"])

    g = sales_w.groupby("customer_id")
    f = pd.DataFrame(index=pd.Index(pop, name="customer_id"))
    last = hist[hist.line_type == "sale"].groupby("customer_id").invoice_ts.max()
    first = hist[hist.line_type == "sale"].groupby("customer_id").invoice_ts.min()
    f["recency_days"] = (cutoff - last.reindex(f.index)).dt.days
    f["tenure_days"] = (cutoff - first.reindex(f.index)).dt.days
    f["orders_w"] = g.invoice.nunique()
    f["purchase_days_w"] = g.invoice_date.nunique()
    f["revenue_w"] = w.groupby("customer_id").revenue.sum().reindex(f.index)
    f["aov_w"] = (g.revenue.sum() / f.orders_w)
    f["distinct_products_w"] = g.stock_code.nunique()
    gross = g.revenue.sum()
    ret = -w[w.line_type == "cancellation"].groupby("customer_id").revenue.sum()
    f["return_rate_w"] = (ret.reindex(f.index).fillna(0) / gross).clip(0, 1)
    # Momentum: last 90 days vs the 90 days before that
    r90 = w[w.invoice_ts > cutoff - pd.Timedelta(days=90)].groupby("customer_id").revenue.sum()
    p90 = w[(w.invoice_ts <= cutoff - pd.Timedelta(days=90))
            & (w.invoice_ts > cutoff - pd.Timedelta(days=180))].groupby("customer_id").revenue.sum()
    f["rev_last90"] = r90.reindex(f.index).fillna(0)
    f["rev_prev90"] = p90.reindex(f.index).fillna(0)
    f["momentum"] = np.log1p(f.rev_last90.clip(lower=0)) - np.log1p(f.rev_prev90.clip(lower=0))
    f["avg_gap_days"] = gaps["mean"].reindex(f.index)
    f["gap_cv"] = (gaps["std"] / gaps["mean"]).reindex(f.index)
    f["overdue_ratio"] = f.recency_days / f.avg_gap_days
    f["has_cadence"] = f.avg_gap_days.notna().astype(int)
    # Fill cadence features for customers with a single purchase day: neutral values
    # plus the has_cadence indicator, so the model can learn they are different.
    f["avg_gap_days"] = f.avg_gap_days.fillna(f.tenure_days)
    f["gap_cv"] = f.gap_cv.fillna(0)
    f["overdue_ratio"] = f.overdue_ratio.replace([np.inf, -np.inf], np.nan).fillna(1.0)
    country = hist.groupby("customer_id").customer_country.first()
    f["is_uk"] = (country.reindex(f.index) == "United Kingdom").astype(int)
    return f


def churn_label(lines: pd.DataFrame, index: pd.Index, cutoff: pd.Timestamp,
                window_days: int = C.CHURN_WINDOW_DAYS) -> pd.Series:
    """1 = no sale in (cutoff, cutoff + window]. Churn is INFERRED, never observed."""
    end = cutoff + pd.Timedelta(days=window_days)
    fut = set(lines[(lines.line_type == "sale") & (lines.invoice_ts > cutoff)
                    & (lines.invoice_ts <= end)].customer_id.unique())
    return pd.Series([0 if c in fut else 1 for c in index], index=index, name="churned")

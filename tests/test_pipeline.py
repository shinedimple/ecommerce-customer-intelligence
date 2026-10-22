"""
Data & logic tests. Run after the pipeline: `pytest -q`.
They encode the guarantees the analysis relies on, so a future change that breaks
one (e.g. re-introducing the cross-sheet duplicates) fails loudly.
"""
import duckdb
import numpy as np
import pandas as pd
import pytest

from src.cie import config as C
from src.cie.clean import analysis_lines


@pytest.fixture(scope="module")
def lines():
    return pd.read_parquet(C.CLEAN_PARQUET)


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(C.WAREHOUSE), read_only=True)
    yield c
    c.close()


def test_no_cross_sheet_duplicate_invoices(lines):
    by = lines.groupby("invoice").source_sheet.nunique()
    assert (by > 1).sum() == 0


def test_no_exact_duplicate_lines(lines):
    key = ["invoice", "stock_code", "description", "quantity", "invoice_ts",
           "unit_price", "customer_id", "country"]
    assert not lines.duplicated(subset=key).any()


def test_reversed_pairs_net_to_zero(lines):
    r = lines[lines.is_reversed]
    assert abs(r.revenue.sum()) < 0.01


def test_every_line_classified(lines):
    assert not (lines.line_type == "other").any()


def test_revenue_bridge_closes(con):
    b = con.execute("SELECT amount_gbp FROM revenue_bridge WHERE step LIKE 'Check%'").fetchone()[0]
    assert abs(b) < 0.01


def test_sql_python_rfm_agree(con):
    py = pd.read_parquet(C.DATA_PROCESSED / "customer_rfm.parquet")
    sq = con.execute("SELECT customer_id, rfm_segment, r_score, f_score, m_score "
                     "FROM rfm_scores").df().set_index("customer_id")
    j = py.join(sq, rsuffix="_sql", how="inner")
    assert len(j) == len(py) == len(sq)
    for col in ("rfm_segment", "r_score", "f_score", "m_score"):
        assert (j[col] == j[f"{col}_sql"]).all(), col


def test_analysis_view_matches_sql(con, lines):
    py = analysis_lines(lines).revenue.sum()
    sq = con.execute("SELECT SUM(revenue) FROM v_customer_lines").fetchone()[0]
    assert abs(py - sq) < 0.01


def test_segments_are_exhaustive_and_consistent():
    c = pd.read_parquet(C.DATA_PROCESSED / "customer_360.parquet")
    assert c.management_segment.notna().all()
    assert (c.revenue_at_risk >= 0).all()
    lapsed = c.management_segment.str.startswith("8")
    assert (c.loc[lapsed, "revenue_at_risk"] == 0).all()
    assert c.loc[~lapsed, "churn_prob_12m"].between(0, 1).all()


def test_churn_model_beats_recency_baseline():
    m = pd.read_csv(C.TABLES / "churn_model_comparison.csv")
    p = m[m.setting.str.contains("PRIMARY")].set_index("model").roc_auc
    assert p["logistic_regression"] > p["baseline: recency only"]


def test_bgnbd_parameters_valid():
    p = pd.read_csv(C.TABLES / "clv_params_final.csv", index_col=0)["value"]
    assert (p > 0).all() and p["a"] > 0 and p["q"] > 1   # q > 1 needed for finite mean spend


def test_no_leakage_features_before_cutoff():
    from src.cie.features import behavioural_features, load_lines
    L = load_lines()
    cut = pd.Timestamp("2010-12-09 23:59:59")
    f1 = behavioural_features(L, cut)
    f2 = behavioural_features(L[L.invoice_ts <= cut], cut)   # future removed
    pd.testing.assert_frame_equal(f1.sort_index(), f2.sort_index())

"""
Step 12 — Customer Lifetime Value.

MODEL CHOICE (WHY):
  This is a NON-CONTRACTUAL, CONTINUOUS-PURCHASE business: customers can buy at any
  time and never announce that they have left. The standard, peer-reviewed approach
  for this setting is:
    * BG/NBD (Fader, Hardie & Lee, 2005) — predicts HOW MANY purchases a customer
      will make and the probability they are still "alive" (active).
    * Gamma-Gamma (Fader, Hardie & Lee, 2005) — predicts the AVERAGE VALUE per
      purchase, shrinking noisy individual averages toward the population mean.
  CLV(12m) = Σ_months E[purchases in month k] × E[value per purchase] × discount_k

  Implemented directly with SciPy (the `lifetimes` package is unmaintained and breaks
  on current NumPy/pandas). Formulas follow the original papers.

WHAT IT IS / IS NOT:
  * It IS forward 12-month REVENUE value (management planning horizon).
  * It is NOT profit: the data contains no cost or margin. Multiply by gross margin
    if/when finance supplies it (the Excel scenario pack does exactly that).
  * It is NOT validated on a full 12 months — the longest clean holdout available
    is 6 months (see `validate`).

KEY MODEL ASSUMPTIONS (tested where the data allows):
  A1 While active, purchases follow a Poisson process (rate varies across customers).
  A2 After any purchase a customer may become permanently inactive.
  A3 Spend per purchase is independent of purchase frequency (Gamma-Gamma).
     -> tested: correlation reported in reports/tables/clv_assumption_checks.csv
  A4 No seasonality. VIOLATED here (Q4 Christmas peak). Consequence: 12-month
     aggregate is roughly right but the monthly phasing is not. Mitigated by using a
     12-month horizon, which contains one full seasonal cycle.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln, hyp2f1

from . import config as C
from .features import clv_inputs, daily_transactions, future_actuals, load_lines

WEEKS_PER_MONTH = 52.0 / 12.0


# ======================================================================================
# BG/NBD
# ======================================================================================
class BetaGeoModel:
    def __init__(self):
        self.params_ = None  # r, alpha, a, b

    @staticmethod
    def _negll(log_params, x, tx, T):
        r, alpha, a, b = np.exp(log_params)
        A1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
        A2 = gammaln(a + b) + gammaln(b + x) - gammaln(b) - gammaln(a + b + x)
        A3 = -(r + x) * np.log(alpha + T)
        with np.errstate(divide="ignore", invalid="ignore"):
            A4 = np.where(
                x > 0,
                np.log(a) - np.log(np.maximum(b + x - 1, 1e-12)) - (r + x) * np.log(alpha + tx),
                -np.inf,
            )
        ll = A1 + A2 + np.logaddexp(A3, A4)
        return -ll.sum()

    def fit(self, x, tx, T):
        x, tx, T = map(np.asarray, (x, tx, T))
        best = None
        for init in ([0.0, 1.0, 0.0, 0.0], [-0.5, 2.0, -1.0, 1.0]):
            res = minimize(self._negll, x0=np.array(init), args=(x, tx, T),
                           method="Nelder-Mead", options={"maxiter": 20000, "xatol": 1e-8,
                                                           "fatol": 1e-8})
            if best is None or res.fun < best.fun:
                best = res
        self.params_ = dict(zip(["r", "alpha", "a", "b"], np.exp(best.x)))
        self.loglik_ = -best.fun
        return self

    def expected_purchases(self, t, x, tx, T):
        """E[# purchases in (T, T+t] | x, t_x, T]."""
        p = self.params_
        r, alpha, a, b = p["r"], p["alpha"], p["a"], p["b"]
        x, tx, T = map(np.asarray, (x, tx, T))
        hyp = hyp2f1(r + x, b + x, a + b + x - 1, t / (alpha + T + t))
        num = (a + b + x - 1) / (a - 1) * (1 - ((alpha + T) / (alpha + T + t)) ** (r + x) * hyp)
        den = 1 + (x > 0) * (a / np.maximum(b + x - 1, 1e-12)) * ((alpha + T) / (alpha + tx)) ** (r + x)
        return num / den

    def p_alive(self, x, tx, T):
        p = self.params_
        r, alpha, a, b = p["r"], p["alpha"], p["a"], p["b"]
        x, tx, T = map(np.asarray, (x, tx, T))
        den = 1 + (x > 0) * (a / np.maximum(b + x - 1, 1e-12)) * ((alpha + T) / (alpha + tx)) ** (r + x)
        return 1.0 / den


# ======================================================================================
# Gamma-Gamma
# ======================================================================================
class GammaGammaModel:
    def __init__(self):
        self.params_ = None  # p, q, v

    @staticmethod
    def _negll(log_params, x, m):
        p, q, v = np.exp(log_params)
        ll = (gammaln(p * x + q) - gammaln(p * x) - gammaln(q) + q * np.log(v)
              + (p * x - 1) * np.log(m) + (p * x) * np.log(x) - (p * x + q) * np.log(x * m + v))
        return -ll.sum()

    def fit(self, x, m):
        x, m = np.asarray(x, float), np.asarray(m, float)
        res = minimize(self._negll, x0=np.log([1.0, 1.0, 100.0]), args=(x, m),
                       method="Nelder-Mead", options={"maxiter": 20000})
        self.params_ = dict(zip(["p", "q", "v"], np.exp(res.x)))
        return self

    def expected_spend(self, x, m):
        p, q, v = self.params_["p"], self.params_["q"], self.params_["v"]
        x, m = np.asarray(x, float), np.asarray(m, float)
        pop_mean = p * v / (q - 1)
        cond = (p * (v + x * m)) / (p * x + q - 1)
        return np.where(x > 0, cond, pop_mean)


# ======================================================================================
# Pipeline helpers
# ======================================================================================
def fit_models(inp: pd.DataFrame):
    bg = BetaGeoModel().fit(inp.frequency, inp.recency, inp["T"])
    rep = inp[(inp.frequency > 0) & (inp.monetary_value > 0)]
    gg = GammaGammaModel().fit(rep.frequency, rep.monetary_value)
    return bg, gg


def predict_clv(inp: pd.DataFrame, bg, gg, months: int = 12,
                annual_rate: float = C.ANNUAL_DISCOUNT_RATE) -> pd.DataFrame:
    out = inp.copy()
    mr = (1 + annual_rate) ** (1 / 12) - 1
    spend = gg.expected_spend(out.frequency.values,
                              out.monetary_value.clip(lower=0).values)
    # Customers whose repeat purchases net to <= 0 get the population mean spend
    spend = np.where(out.monetary_value.values > 0, spend, gg.expected_spend(0, 0))
    clv = np.zeros(len(out))
    prev = np.zeros(len(out))
    for k in range(1, months + 1):
        cum = bg.expected_purchases(k * WEEKS_PER_MONTH, out.frequency, out.recency, out["T"])
        clv += (cum - prev) * spend / (1 + mr) ** k
        prev = cum
    out["exp_purchases_12m"] = prev
    out["exp_spend_per_purchase"] = spend
    out["p_alive"] = bg.p_alive(out.frequency, out.recency, out["T"])
    out["clv_12m"] = clv
    return out


def validate(lines: pd.DataFrame) -> dict:
    """
    Out-of-sample test: fit on data up to CALIBRATION_END, predict the next
    HOLDOUT_DAYS, compare with what actually happened. Benchmarked against a naive
    run-rate model (each customer repeats their historical purchase rate), because a
    sophisticated model is only worth its complexity if it beats the simple one.
    """
    cut = C.CALIBRATION_END
    inp = clv_inputs(lines, cut)
    bg, gg = fit_models(inp)
    t = C.HOLDOUT_DAYS / 7.0
    act = future_actuals(lines, cut, C.HOLDOUT_DAYS).reindex(inp.index).fillna(0)
    pred_n = bg.expected_purchases(t, inp.frequency, inp.recency, inp["T"])
    spend = gg.expected_spend(inp.frequency, inp.monetary_value.clip(lower=0))
    spend = np.where(inp.monetary_value > 0, spend, gg.expected_spend(0, 0))
    pred_rev = pred_n * spend

    # Naive benchmark: historical purchase-occasion rate x horizon; historical mean value
    naive_rate = (inp.frequency + 1) / inp["T"]
    naive_n = naive_rate * t
    d = daily_transactions(lines[lines.invoice_ts <= cut]).groupby("customer_id").value.mean()
    naive_rev = naive_n * d.reindex(inp.index).fillna(0).clip(lower=0)

    res = pd.DataFrame({"actual_n": act.actual_purchases, "pred_n": pred_n, "naive_n": naive_n,
                        "actual_rev": act.actual_revenue, "pred_rev": pred_rev,
                        "naive_rev": naive_rev, "frequency": inp.frequency})

    def mae(a, b):
        return float(np.mean(np.abs(a - b)))

    summary = {
        "calibration_end": str(cut.date()),
        "holdout_days": C.HOLDOUT_DAYS,
        "customers": len(res),
        "actual_purchases_total": float(res.actual_n.sum()),
        "bgnbd_pred_purchases_total": float(res.pred_n.sum()),
        "naive_pred_purchases_total": float(res.naive_n.sum()),
        "bgnbd_purchase_mae": mae(res.actual_n, res.pred_n),
        "naive_purchase_mae": mae(res.actual_n, res.naive_n),
        "actual_revenue_total": float(res.actual_rev.sum()),
        "model_pred_revenue_total": float(res.pred_rev.sum()),
        "naive_pred_revenue_total": float(res.naive_rev.sum()),
        "model_revenue_mae": mae(res.actual_rev, res.pred_rev),
        "naive_revenue_mae": mae(res.actual_rev, res.naive_rev),
        "spearman_rev_model": float(res[["actual_rev", "pred_rev"]].corr("spearman").iloc[0, 1]),
        "spearman_rev_naive": float(res[["actual_rev", "naive_rev"]].corr("spearman").iloc[0, 1]),
    }
    # Top-20% capture: of actual holdout revenue, how much sits with the customers the
    # model ranked in its top 20%? (What a CRM team actually cares about.)
    k = int(len(res) * 0.2)
    tot = res.actual_rev.clip(lower=0).sum()
    summary["top20_capture_model"] = float(
        res.nlargest(k, "pred_rev").actual_rev.clip(lower=0).sum() / tot)
    summary["top20_capture_naive"] = float(
        res.nlargest(k, "naive_rev").actual_rev.clip(lower=0).sum() / tot)

    # Calibration by frequency bucket (classic BG/NBD diagnostic)
    res["freq_bucket"] = pd.cut(res.frequency, [-1, 0, 1, 2, 4, 9, 19, 10_000],
                                labels=["0", "1", "2", "3-4", "5-9", "10-19", "20+"])
    by_f = res.groupby("freq_bucket", observed=True)[["actual_n", "pred_n", "naive_n"]].mean()
    by_f["customers"] = res.groupby("freq_bucket", observed=True).size()
    res["pred_decile"] = pd.qcut(res.pred_rev.rank(method="first"), 10, labels=range(1, 11))
    by_d = res.groupby("pred_decile", observed=True)[["actual_rev", "pred_rev"]].sum()
    return {"summary": summary, "by_frequency": by_f.reset_index(),
            "by_decile": by_d.reset_index(), "params": {**bg.params_, **gg.params_},
            "detail": res}


def backtest_12m(lines: pd.DataFrame) -> dict:
    """
    Direct test of the 12-month horizon: calibrate on Dec-2009..Dec-2010 (only 12
    months of history) and predict Dec-2010..Dec-2011. This is the ONLY full 12-month
    window available, and its calibration period is short and left-censored, so it
    shows how the model behaves when history is thin. Reported, not hidden.
    """
    cut = pd.Timestamp("2010-12-09 23:59:59")
    inp = clv_inputs(lines, cut)
    bg, gg = fit_models(inp)
    p = predict_clv(inp, bg, gg, annual_rate=0.0)
    act = future_actuals(lines, cut, 365).reindex(inp.index).fillna(0)
    return {
        "calibration_window": "2009-12-01 to 2010-12-09 (12 months)",
        "customers": len(inp),
        "pred_purchases": float(p.exp_purchases_12m.sum()),
        "actual_purchases": float(act.actual_purchases.sum()),
        "pred_revenue": float(p.clv_12m.sum()),
        "actual_revenue": float(act.actual_revenue.sum()),
        "revenue_error_pct": float(p.clv_12m.sum() / act.actual_revenue.sum() - 1),
        "bgnbd_b_param": float(bg.params_["b"]),
        "spearman_rev": float(pd.concat([p.clv_12m, act.actual_revenue], axis=1)
                              .corr("spearman").iloc[0, 1]),
    }


def assumption_checks(inp: pd.DataFrame) -> pd.DataFrame:
    rep = inp[(inp.frequency > 0) & (inp.monetary_value > 0)]
    return pd.DataFrame([
        {"check": "Gamma-Gamma independence: Pearson corr(frequency, monetary_value)",
         "value": round(float(rep[["frequency", "monetary_value"]].corr().iloc[0, 1]), 4),
         "guidance": "|r| < 0.3 is usually treated as acceptable"},
        {"check": "Gamma-Gamma independence: Spearman corr(frequency, monetary_value)",
         "value": round(float(rep[["frequency", "monetary_value"]].corr("spearman").iloc[0, 1]), 4),
         "guidance": "rank-based; robust to the very long spend tail"},
        {"check": "Share of customers with zero repeat purchases",
         "value": round(float((inp.frequency == 0).mean()), 4),
         "guidance": "these receive population-average spend"},
    ])


def run(lines: pd.DataFrame | None = None) -> pd.DataFrame:
    lines = load_lines() if lines is None else lines
    val = validate(lines)
    pd.Series(val["summary"]).to_csv(C.TABLES / "clv_validation_summary.csv", header=["value"])
    val["by_frequency"].to_csv(C.TABLES / "clv_validation_by_frequency.csv", index=False)
    val["by_decile"].to_csv(C.TABLES / "clv_validation_by_decile.csv", index=False)
    pd.Series(val["params"]).to_csv(C.TABLES / "clv_params_calibration.csv", header=["value"])
    bt = backtest_12m(lines)
    pd.Series(bt).to_csv(C.TABLES / "clv_backtest_12m.csv", header=["value"])
    val["detail"].to_parquet(C.DATA_PROCESSED / "clv_validation_detail.parquet")

    snapshot = lines.invoice_ts.max().normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    inp = clv_inputs(lines, snapshot)
    bg, gg = fit_models(inp)
    pd.Series({**bg.params_, **gg.params_}).to_csv(C.TABLES / "clv_params_final.csv",
                                                    header=["value"])
    assumption_checks(inp).to_csv(C.TABLES / "clv_assumption_checks.csv", index=False)
    out = predict_clv(inp, bg, gg)
    # Discount-rate sensitivity (the rate is an assumption, so show what it moves)
    sens = []
    for rate in (0.0, 0.05, 0.10, 0.15, 0.20):
        sens.append({"annual_discount_rate": rate,
                     "total_clv_12m": float(predict_clv(inp, bg, gg, annual_rate=rate).clv_12m.sum())})
    pd.DataFrame(sens).to_csv(C.TABLES / "clv_discount_sensitivity.csv", index=False)
    out.to_parquet(C.DATA_PROCESSED / "customer_clv.parquet")
    s = val["summary"]
    print(f"  CLV holdout: actual purchases {s['actual_purchases_total']:.0f} | "
          f"BG/NBD {s['bgnbd_pred_purchases_total']:.0f} | naive {s['naive_pred_purchases_total']:.0f}")
    print(f"  CLV holdout revenue: actual £{s['actual_revenue_total']:,.0f} | "
          f"model £{s['model_pred_revenue_total']:,.0f} | naive £{s['naive_pred_revenue_total']:,.0f}")
    print(f"  12m backtest (thin history): revenue error {bt['revenue_error_pct']:+.1%}")
    print(f"  Total 12m CLV (current base): £{out.clv_12m.sum():,.0f}")
    return out


if __name__ == "__main__":
    run()

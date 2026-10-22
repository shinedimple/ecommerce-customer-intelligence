"""
Step 13 — Churn / risk model.

DEFINITION (ASSUMPTION): churned = no merchandise order in the next 365 days.
  Non-contractual business: churn is never observed, it is inferred from silence.
  WHY 365 and not 180: many accounts are seasonal (autumn gift/wholesale buyers).
  At a December cutoff, 54% of customers are silent for the next 180 days, but many
  return for the next peak — a 180-day label would call them "churned" wrongly.
  365 days also matches the revenue-at-risk calculation (annual revenue x P(lost
  for a year)), so the probability and the money are on the same horizon.
  COST of 365: only one cutoff (Dec-2010) has a full year of future data, so the
  primary model is validated by cross-validation only. A 180-day variant with an
  out-of-time test is run as a robustness check on the RANKING.

DESIGN (WHY):
  * Seasonality: the business peaks Sep–Nov (gift/wholesale buying). The label for a
    June cutoff covers the peak; for a December cutoff it covers the quiet half-year.
    Base churn rates therefore differ by cutoff. We SCORE customers as of Dec-2011,
    so we TRAIN on the seasonally matched Dec-2010 cutoff.
  * Validation: (a) 5-fold stratified CV at the training cutoff (in-season),
    (b) out-of-time test at Jun-2011 (different season → a stress test of ranking,
    not of calibration).
  * Baselines: a model must beat (1) "days since last order" alone, and (2) the
    BG/NBD P(alive), otherwise its extra complexity is not justified.
  * Features use a fixed trailing 365-day window, and tenure is capped at 365 days,
    because training history (from Dec-2009) is shorter than scoring history.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from . import config as C
from .clv import BetaGeoModel
from .features import behavioural_features, churn_label, clv_inputs, load_lines

TRAIN_CUTOFF = pd.Timestamp("2010-12-09 23:59:59")
OOT_CUTOFF = pd.Timestamp("2011-06-09 23:59:59")

FEATURES = ["recency_days", "tenure_capped", "orders_w", "purchase_days_w", "revenue_w",
            "aov_w", "distinct_products_w", "return_rate_w", "momentum", "avg_gap_days",
            "gap_cv", "overdue_ratio", "has_cadence", "is_uk"]
LOG_FEATURES = ["recency_days", "tenure_capped", "orders_w", "purchase_days_w", "revenue_w",
                "aov_w", "distinct_products_w", "avg_gap_days", "overdue_ratio"]


def _prep(f: pd.DataFrame) -> pd.DataFrame:
    X = f.copy()
    X["tenure_capped"] = X.tenure_days.clip(upper=365)
    for c in LOG_FEATURES:
        X[c] = np.log1p(X[c].clip(lower=0))
    return X[FEATURES]


def dataset(lines, cutoff, window_days):
    f = behavioural_features(lines, cutoff)
    y = churn_label(lines, f.index, cutoff, window_days)
    return f, _prep(f), y


def bgnbd_risk(lines, cutoff, index):
    inp = clv_inputs(lines, cutoff)
    bg = BetaGeoModel().fit(inp.frequency, inp.recency, inp["T"])
    pa = pd.Series(bg.p_alive(inp.frequency, inp.recency, inp["T"]), index=inp.index)
    return 1 - pa.reindex(index)


def _metrics(name, y, p, setting):
    top = pd.Series(p, index=y.index).rank(pct=True, method="first") > 0.9
    return {"setting": setting, "model": name, "roc_auc": roc_auc_score(y, p),
            "pr_auc": average_precision_score(y, p),
            "brier": brier_score_loss(y, np.clip(p, 0, 1)) if p.max() <= 1 else np.nan,
            "base_rate": float(y.mean()),
            "top_decile_churn_rate": float(y[top].mean()),
            "top_decile_lift": float(y[top].mean() / y.mean())}


def models():
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
    gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300,
                                        l2_regularization=1.0, random_state=C.RANDOM_STATE)
    return {"logistic_regression": lr, "gradient_boosting": gb}


def run(lines: pd.DataFrame | None = None) -> pd.DataFrame:
    lines = load_lines() if lines is None else lines
    skf = StratifiedKFold(5, shuffle=True, random_state=C.RANDOM_STATE)
    rows = []

    # ---- Robustness experiment: 180-day label, CV + out-of-time -----------------
    f_tr, X_tr, y_tr = dataset(lines, TRAIN_CUTOFF, 180)
    f_te, X_te, y_te = dataset(lines, OOT_CUTOFF, 180)
    for setting, f, y, cut in (("180d label | in-season CV (Dec-2010)", f_tr, y_tr, TRAIN_CUTOFF),
                               ("180d label | out-of-time (Jun-2011)", f_te, y_te, OOT_CUTOFF)):
        r = f.recency_days.values.astype(float)
        m = _metrics("baseline: recency only", y, r / r.max(), setting)
        m["brier"] = np.nan  # a scaled rank is not a probability
        rows.append(m)
        rows.append(_metrics("baseline: BG/NBD 1 - P(alive)", y,
                             bgnbd_risk(lines, cut, f.index).values, setting))
    for name, mdl in models().items():
        p_cv = cross_val_predict(mdl, X_tr, y_tr, cv=skf, method="predict_proba")[:, 1]
        rows.append(_metrics(name, y_tr, p_cv, "180d label | in-season CV (Dec-2010)"))
        mdl.fit(X_tr, y_tr)
        rows.append(_metrics(name, y_te, mdl.predict_proba(X_te)[:, 1],
                             "180d label | out-of-time (Jun-2011)"))

    # ---- Primary experiment: 365-day label, CV at Dec-2010 -----------------------
    f_p, X_p, y_p = dataset(lines, TRAIN_CUTOFF, C.CHURN_WINDOW_DAYS)
    setting = "365d label | in-season CV (Dec-2010) [PRIMARY]"
    r = f_p.recency_days.values.astype(float)
    m = _metrics("baseline: recency only", y_p, r / r.max(), setting)
    m["brier"] = np.nan
    rows.append(m)
    rows.append(_metrics("baseline: BG/NBD 1 - P(alive)", y_p,
                         bgnbd_risk(lines, TRAIN_CUTOFF, f_p.index).values, setting))
    cv_preds, fitted = {}, {}
    for name, mdl in models().items():
        p_cv = cross_val_predict(mdl, X_p, y_p, cv=skf, method="predict_proba")[:, 1]
        cv_preds[name] = p_cv
        rows.append(_metrics(name, y_p, p_cv, setting))
        fitted[name] = mdl.fit(X_p, y_p)
    res = pd.DataFrame(rows)
    res.to_csv(C.TABLES / "churn_model_comparison.csv", index=False)

    # Model selection: prefer the interpretable model unless the complex one wins
    # primary CV AUC by > 0.01 (a pre-declared rule, not chosen after the fact).
    cv = res[res.setting == setting].set_index("model")
    chosen = ("gradient_boosting"
              if cv.loc["gradient_boosting", "roc_auc"] - cv.loc["logistic_regression", "roc_auc"] > 0.01
              else "logistic_regression")

    # Calibration (reliability) table: matters because probabilities are multiplied
    # by revenue to get revenue at risk.
    cal = pd.DataFrame({"p": cv_preds[chosen], "y": y_p.values})
    cal["bin"] = pd.qcut(cal.p, 10, labels=False, duplicates="drop")
    cal = cal.groupby("bin").agg(mean_predicted=("p", "mean"), observed_rate=("y", "mean"),
                                 customers=("y", "size")).reset_index()
    cal.to_csv(C.TABLES / "churn_calibration.csv", index=False)

    lr = fitted["logistic_regression"]
    coefs = pd.DataFrame({"feature": FEATURES,
                          "coef_standardised": lr[-1].coef_[0]}).sort_values(
        "coef_standardised", key=np.abs, ascending=False)
    coefs["note"] = ("recency_days, avg_gap_days and overdue_ratio are collinear "
                     "(log overdue = log recency - log gap): interpret them jointly")
    coefs.to_csv(C.TABLES / "churn_lr_coefficients.csv", index=False)

    # Observed churn rate by recency band (the plain-English driver table)
    drv = pd.DataFrame({"recency_days": f_p.recency_days, "churned": y_p,
                        "purchase_days_w": f_p.purchase_days_w})
    drv["recency_band"] = pd.cut(drv.recency_days, [-1, 30, 60, 90, 180, 365],
                                 labels=["0-30", "31-60", "61-90", "91-180", "181-365"])
    drv["frequency_band"] = pd.cut(drv.purchase_days_w, [0, 1, 2, 4, 9, 10_000],
                                   labels=["1", "2", "3-4", "5-9", "10+"])
    pd.concat([
        drv.groupby("recency_band", observed=True).churned.agg(["mean", "size"])
           .reset_index().rename(columns={"recency_band": "band"}).assign(driver="recency_days"),
        drv.groupby("frequency_band", observed=True).churned.agg(["mean", "size"])
           .reset_index().rename(columns={"frequency_band": "band"}).assign(driver="purchase_days_12m"),
    ]).rename(columns={"mean": "observed_churn_rate", "size": "customers"}).to_csv(
        C.TABLES / "churn_drivers_observed.csv", index=False)

    # Score the current base as of the snapshot with the seasonally matched model
    snap = lines.invoice_ts.max().normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    f_now = behavioural_features(lines, snap)
    scores = pd.DataFrame(index=f_now.index)
    scores["churn_prob_12m"] = fitted[chosen].predict_proba(_prep(f_now))[:, 1]
    scores["churn_model"] = chosen
    scores = scores.join(f_now[["recency_days", "revenue_w", "orders_w", "overdue_ratio",
                                "momentum"]].rename(columns={"revenue_w": "revenue_t12m",
                                                             "orders_w": "orders_t12m"}))
    scores.to_parquet(C.DATA_PROCESSED / "customer_churn_scores.parquet")
    pd.Series({"chosen_model": chosen, "label": "no order in next 365 days",
               "train_cutoff": str(TRAIN_CUTOFF.date()), "train_customers": len(y_p),
               "train_churn_rate": float(y_p.mean()),
               "cv_roc_auc": float(cv.loc[chosen, "roc_auc"]),
               "cv_brier": float(cv.loc[chosen, "brier"]),
               "scored_customers": len(scores),
               "scoring_population": "customers with >=1 order in the 365 days to snapshot",
               "mean_score_now": float(scores.churn_prob_12m.mean())}
              ).to_csv(C.TABLES / "churn_model_card.csv", header=["value"])
    print(res.round(3).to_string(index=False))
    print(f"  chosen: {chosen}")
    return scores


if __name__ == "__main__":
    run()

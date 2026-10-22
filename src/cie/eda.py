"""
Step 9 — Exploratory analysis & report figures.

Every figure answers a named business question (in its title) and is saved to
reports/figures/ for the executive report, README and notebooks.
Source tables are the SQL outputs and model outputs — no figure recomputes a KPI
with different logic, so the charts and the dashboard cannot disagree.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
import seaborn as sns

from . import config as C
from .warehouse import query

NAVY, TEAL, CORAL, GREY, GOLD = "#1F3A5F", "#2A9D8F", "#E76F51", "#9AA5B1", "#E9C46A"
plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 150, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 10, "axes.titleweight": "bold",
                     "axes.titlesize": 11})
GBP = mtick.FuncFormatter(lambda x, _: f"£{x/1e6:.1f}M" if abs(x) >= 1e6 else f"£{x/1e3:.0f}k")


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(C.FIGURES / f"{name}.png", bbox_inches="tight")
    plt.close(fig)


def monthly_trend():
    m = pd.read_csv(C.TABLES / "sql_kpi_monthly.csv")
    m["guest_sales"] = m.gross_merch_sales - m.identified_sales
    fig, ax = plt.subplots(figsize=(10, 4))
    x = pd.to_datetime(m.year_month)
    ax.bar(x, m.identified_sales, width=20, color=NAVY, label="Identified customers")
    ax.bar(x, m.guest_sales, width=20, bottom=m.identified_sales, color=GOLD, label="Guest / no ID")
    ax.yaxis.set_major_formatter(GBP)
    ax.set_title("Q: Is the business growing? Monthly gross merchandise sales (complete months)")
    ax.legend(frameon=False, loc="upper left")
    _save(fig, "01_monthly_sales_identified_vs_guest")


def fy_comparison():
    f = pd.read_csv(C.TABLES / "sql_kpi_fy_comparison.csv").set_index("fiscal_year")
    metrics = {"Identified sales": "identified_sales", "Guest sales": "guest_sales",
               "Active customers": "active_customers", "Orders / customer": "orders_per_customer",
               "AOV (identified)": "identified_aov"}
    chg = pd.Series({k: f.loc["FY2011", v] / f.loc["FY2010", v] - 1 for k, v in metrics.items()})
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.barh(chg.index, chg.values, color=[CORAL if v < 0 else TEAL for v in chg.values])
    for i, v in enumerate(chg.values):
        ax.text(v + (0.005 if v >= 0 else -0.005), i, f"{v:+.1%}", va="center",
                ha="left" if v >= 0 else "right")
    ax.axvline(0, color="black", lw=0.8)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_xlim(min(chg.min() * 1.4, -0.1), max(chg.max() * 1.4, 0.1))
    ax.set_title("Q: Where did growth come from? FY2011 vs FY2010 (Dec–Nov)")
    ax.invert_yaxis()
    _save(fig, "02_fy_growth_drivers")


def missing_id():
    m = pd.read_csv(C.TABLES / "missing_id_by_month.csv")
    m = m[m.year_month <= "2011-11"]
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.plot(pd.to_datetime(m.year_month), m.pct_revenue_missing_id, color=CORAL, marker="o")
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_ylim(0, None)
    ax.set_title("Q: How much revenue can customer analytics NOT see? Share of sales with no Customer ID")
    _save(fig, "03_missing_customer_id_share")


def cohort_heatmap():
    r = pd.read_csv(C.TABLES / "sql_cohort_retention.csv")
    r = r[(r.months_since_first <= 12) & (~r.is_left_censored)]
    p = r.pivot(index="cohort_month", columns="months_since_first", values="retention_rate")
    p = p.drop(columns=0)
    sizes = r.drop_duplicates("cohort_month").set_index("cohort_month").cohort_size
    p.index = [f"{i} (n={sizes[i]})" for i in p.index]
    fig, ax = plt.subplots(figsize=(11, 7))
    sns.heatmap(p, annot=True, fmt=".0%", cmap="Blues", cbar=False, ax=ax, annot_kws={"size": 7})
    ax.set_xlabel("Months since first order")
    ax.set_ylabel("Acquisition cohort")
    ax.set_title("Q: Do customers come back? Monthly cohort retention "
                 "(Dec-2009 cohort excluded: left-censored)")
    _save(fig, "04_cohort_retention_heatmap")


def retention_curve():
    a = pd.read_csv(C.TABLES / "sql_cohort_avg_curve.csv")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(a.months_since_first, a.weighted_retention, marker="o", color=NAVY)
    for x, y in zip(a.months_since_first, a.weighted_retention):
        ax.text(x, y + 0.006, f"{y:.0%}", ha="center", fontsize=8)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_ylim(0, 0.3)
    ax.set_xlabel("Months since first order")
    ax.set_title("Q: When do we lose new customers? ~79% do not order in month 1")
    _save(fig, "05_average_retention_curve")


def pareto():
    c = pd.read_parquet(C.DATA_PROCESSED / "customer_rfm.parquet")
    v = c.monetary.clip(lower=0).sort_values(ascending=False).values
    cum = np.cumsum(v) / v.sum()
    x = np.arange(1, len(v) + 1) / len(v)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(x, cum, color=NAVY)
    for t in (0.01, 0.1, 0.2):
        y = cum[int(t * len(v)) - 1]
        ax.scatter([t], [y], color=CORAL, zorder=3)
        ax.annotate(f"Top {t:.0%} → {y:.0%} of revenue", (t, y), textcoords="offset points",
                    xytext=(10, -12))
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_xlabel("Customers (ranked by net revenue)")
    ax.set_ylabel("Cumulative share of revenue")
    ax.set_title("Q: How dependent are we on a few customers?")
    _save(fig, "06_customer_concentration_pareto")


def rfm_segments():
    s = pd.read_csv(C.TABLES / "sql_rfm_segment_summary.csv").sort_values("pct_revenue")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    y = np.arange(len(s))
    ax.barh(y - 0.2, s.pct_customers, height=0.4, color=GREY, label="% of customers")
    ax.barh(y + 0.2, s.pct_revenue, height=0.4, color=NAVY, label="% of net revenue")
    ax.set_yticks(y, s.rfm_segment)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Q: Who are our customers? RFM segments — share of base vs share of revenue")
    _save(fig, "07_rfm_segments")


def clv_validation():
    f = pd.read_csv(C.TABLES / "clv_validation_by_frequency.csv")
    d = pd.read_csv(C.TABLES / "clv_validation_by_decile.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    x = np.arange(len(f))
    axes[0].bar(x - 0.27, f.actual_n, 0.27, color=NAVY, label="Actual")
    axes[0].bar(x, f.pred_n, 0.27, color=TEAL, label="BG/NBD")
    axes[0].bar(x + 0.27, f.naive_n, 0.27, color=GREY, label="Naive run-rate")
    axes[0].set_xticks(x, f.freq_bucket)
    axes[0].set_xlabel("Repeat purchases in calibration period")
    axes[0].set_ylabel("Avg purchases in 6-month holdout")
    axes[0].legend(frameon=False)
    axes[0].set_title("Holdout: purchase counts by customer history")
    axes[1].bar(d.pred_decile - 0.2, d.actual_rev, 0.4, color=NAVY, label="Actual revenue")
    axes[1].bar(d.pred_decile + 0.2, d.pred_rev, 0.4, color=TEAL, label="Predicted revenue")
    axes[1].yaxis.set_major_formatter(GBP)
    axes[1].set_xlabel("Predicted-value decile (10 = highest)")
    axes[1].legend(frameon=False)
    axes[1].set_title("Holdout: ranking works; top decile under-predicted")
    fig.suptitle("Q: Can we trust the CLV model? Out-of-sample test (calibrate to Jun-2011, "
                 "test Jun–Dec 2011)", fontweight="bold")
    _save(fig, "08_clv_validation")


def churn_diagnostics():
    cal = pd.read_csv(C.TABLES / "churn_calibration.csv")
    drv = pd.read_csv(C.TABLES / "churn_drivers_observed.csv")
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    axes[0].plot([0, 1], [0, 1], ls="--", color=GREY)
    axes[0].plot(cal.mean_predicted, cal.observed_rate, marker="o", color=NAVY)
    axes[0].set_xlabel("Predicted 12m churn probability")
    axes[0].set_ylabel("Observed churn rate")
    axes[0].set_title("Calibration (5-fold CV)")
    for ax, drv_name, title in ((axes[1], "recency_days", "Churn by days since last order"),
                                (axes[2], "purchase_days_12m", "Churn by purchase days in last 12m")):
        d = drv[drv.driver == drv_name]
        ax.bar(d.band.astype(str), d.observed_churn_rate, color=CORAL)
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
        ax.set_title(title)
    fig.suptitle("Q: Who is likely to stop buying? (label: no order in next 12 months, "
                 "Dec-2010 cutoff)", fontweight="bold")
    _save(fig, "09_churn_model_diagnostics")


def value_risk_grid():
    g = pd.read_csv(C.TABLES / "value_risk_grid_revenue_at_risk.csv", index_col=0)
    n = pd.read_csv(C.TABLES / "value_risk_grid_customers.csv", index_col=0)
    lab = g.map(lambda v: f"£{v/1e3:,.0f}k") + "\n" + n.map(lambda v: f"{int(v):,} cust")
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    sns.heatmap(g, annot=lab, fmt="", cmap="Reds", cbar=False, ax=ax, linewidths=1)
    ax.set_xlabel("Churn-probability tier")
    ax.set_ylabel("Value tier (trailing-12m revenue)")
    ax.set_title("Q: Where is revenue at risk? Probability-weighted £ at risk")
    _save(fig, "10_value_risk_grid")


def management_segments():
    s = pd.read_csv(C.TABLES / "management_segments.csv")
    s = s[~s.management_segment.str.startswith("8")]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    y = np.arange(len(s))
    ax.barh(y - 0.2, s.revenue_t12m, 0.4, color=NAVY, label="Trailing-12m revenue")
    ax.barh(y + 0.2, s.revenue_at_risk, 0.4, color=CORAL, label="Revenue at risk (prob.-weighted)")
    ax.set_yticks(y, [f"{a}  (n={b:,})" for a, b in zip(s.management_segment, s.customers)])
    ax.xaxis.set_major_formatter(GBP)
    ax.invert_yaxis()
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Q: What should we do, and for whom? Management segments")
    _save(fig, "11_management_segments")


def ordering_pattern():
    d = query("""SELECT EXTRACT(isodow FROM order_ts) AS dow, EXTRACT(hour FROM order_ts) AS hr,
                        COUNT(*) AS orders
                 FROM fact_orders WHERE order_type='sale' GROUP BY 1, 2""")
    p = d.pivot(index="dow", columns="hr", values="orders").fillna(0)
    p.index = [["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(i) - 1] for i in p.index]
    fig, ax = plt.subplots(figsize=(10, 3.2))
    sns.heatmap(p, cmap="Blues", ax=ax, cbar_kws={"label": "orders"})
    ax.set_xlabel("Hour of day")
    ax.set_title("Q: When do customers order? (timing for outreach & staffing; "
                 "virtually no Saturday trading: 30 orders in 2 years)")
    _save(fig, "12_order_timing")


def run():
    for f in (monthly_trend, fy_comparison, missing_id, cohort_heatmap, retention_curve,
              pareto, rfm_segments, clv_validation, churn_diagnostics, value_risk_grid,
              management_segments, ordering_pattern):
        f()
        print(f"  figure: {f.__name__}")


if __name__ == "__main__":
    run()

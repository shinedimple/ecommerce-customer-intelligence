"""
Steps 14–17 — High-value/high-risk customers, revenue at risk, management segments,
and the action playbook.

KEY DESIGN DECISIONS (WHY):
  * VALUE tier = trailing-12-month net revenue (what is at stake today), NOT predicted
    CLV. CLV already discounts customers who are drifting away, so tiering on CLV would
    demote exactly the high spenders management most needs to rescue (double-counting
    risk). CLV is kept as a separate "future value" field for prioritisation.
  * RISK tier = calibrated 12-month churn probability from the supervised model.
  * REVENUE AT RISK (per customer) = trailing-12m revenue x P(no order in next 12m).
      ASSUMPTIONS: (1) a customer who churns would otherwise have repeated last year's
      spend; (2) partial decline ("shrinkage") by customers who stay is NOT counted.
      So it is an EXPOSURE measure, not a forecast of losses, and it understates the
      total retention problem (net revenue retention was 81%, which includes shrinkage).
  * Customers with no order in the last 12 months are reported as "Lapsed (>12m)":
      their revenue is already gone, so it is not "at risk" — it is a win-back pool.
"""
import numpy as np
import pandas as pd

from . import config as C
from .warehouse import query

SEGMENT_ORDER = [
    "1. Protect - Key Accounts",
    "2. Rescue - High Value at Risk",
    "3. Develop - Core Growth",
    "4. Win Back - Core at Risk",
    "5. Nurture - New Customers",
    "6. Automate - Low Value Active",
    "7. Deprioritise - Low Value Lapsing",
    "8. Lapsed (>12m) - Win-back Pool",
]

PLAYBOOK = pd.DataFrame([
    {"management_segment": SEGMENT_ORDER[0],
     "objective": "Retain and deepen share of wallet",
     "action": "Named account owner; quarterly business review; early access to new ranges; "
               "volume-tier pricing reviewed annually",
     "channel": "Account manager (phone / visit)",
     "success_kpi": "Net revenue retention of segment >= 100%",
     "spend_guidance": "Highest cost-to-serve justified; cap at a set % of segment margin"},
    {"management_segment": SEGMENT_ORDER[1],
     "objective": "Stop the loss before it happens (highest £ priority)",
     "action": "Personal outreach within 2 weeks ranked by revenue at risk; find the reason "
               "(price, range, service, competitor); targeted incentive only if reason is price",
     "channel": "Account manager call, then tailored email",
     "success_kpi": "Share of segment placing an order within 90 days; £ recovered",
     "spend_guidance": "Incentive per account <= margin x revenue at risk x expected save rate"},
    {"management_segment": SEGMENT_ORDER[2],
     "objective": "Grow order frequency / basket",
     "action": "Replenishment reminders timed to each customer's own buying cadence; "
               "cross-sell of categories they have not bought",
     "channel": "Automated email + sales team for top of tier",
     "success_kpi": "Orders per customer; AOV; migration to High value",
     "spend_guidance": "Low-cost automation first; human time for top decile only"},
    {"management_segment": SEGMENT_ORDER[3],
     "objective": "Re-activate before they lapse",
     "action": "Triggered win-back when overdue ratio > 1.5x their normal gap; "
               "reorder-your-bestsellers email; time-limited offer",
     "channel": "Automated email sequence",
     "success_kpi": "Reactivation rate within 60 days",
     "spend_guidance": "Offer value capped by expected margin of one average order"},
    {"management_segment": SEGMENT_ORDER[4],
     "objective": "Convert first order into second order",
     "action": "Onboarding series; second-order incentive inside 60 days; "
               "capture company/contact details",
     "channel": "Automated email",
     "success_kpi": "2nd-order rate within 90 days of first",
     "spend_guidance": "Moderate — a 2nd order is the strongest predictor of retention"},
    {"management_segment": SEGMENT_ORDER[5],
     "objective": "Serve profitably at low cost",
     "action": "Self-service, standard newsletters, minimum-order thresholds",
     "channel": "Newsletter / website",
     "success_kpi": "Cost-to-serve per £ revenue",
     "spend_guidance": "Minimal; no discretionary incentives"},
    {"management_segment": SEGMENT_ORDER[6],
     "objective": "Let go gracefully; learn why",
     "action": "One low-cost reactivation email; include in lost-customer survey sample",
     "channel": "Email",
     "success_kpi": "Survey response insights",
     "spend_guidance": "Near zero"},
    {"management_segment": SEGMENT_ORDER[7],
     "objective": "Opportunistic reactivation",
     "action": "Seasonal campaign before the Sep–Nov peak; high-historic-value lapsed "
               "accounts get a personal call",
     "channel": "Seasonal email; calls for top historical spenders",
     "success_kpi": "Reactivated customers and £ revenue",
     "spend_guidance": "Only for accounts with high historical value"},
])


def build() -> pd.DataFrame:
    rfm = pd.read_parquet(C.DATA_PROCESSED / "customer_rfm.parquet")
    clv = pd.read_parquet(C.DATA_PROCESSED / "customer_clv.parquet")
    churn = pd.read_parquet(C.DATA_PROCESSED / "customer_churn_scores.parquet")
    dim = query("SELECT customer_id, country, first_order_ts, cohort_month, "
                "is_left_censored FROM dim_customer").set_index("customer_id")
    rules = query("SELECT customer_id, avg_gap_days, cadence_status FROM churn_risk_rules"
                  ).set_index("customer_id")

    c = rfm.join(dim, how="left")
    c = c.join(clv[["clv_12m", "exp_purchases_12m", "exp_spend_per_purchase", "p_alive"]])
    c = c.join(churn[["churn_prob_12m", "revenue_t12m", "orders_t12m", "momentum"]])
    c = c.join(rules)
    snapshot = pd.Timestamp(query("SELECT snapshot_date FROM params").iloc[0, 0])

    c["is_active_12m"] = c.churn_prob_12m.notna()
    c["revenue_t12m"] = c.revenue_t12m.fillna(0.0)
    c["is_new"] = (snapshot - c.first_order_ts).dt.days <= C.NEW_CUSTOMER_DAYS

    # Value tier: rank on trailing-12m revenue among customers active in last 12m
    act = c.is_active_12m
    pct = c.loc[act, "revenue_t12m"].rank(pct=True, method="first", ascending=False)
    c["value_tier"] = "Lapsed"
    c.loc[act, "value_tier"] = np.select(
        [pct <= C.VALUE_TOP_SHARE, pct <= C.VALUE_TOP_SHARE + C.VALUE_MID_SHARE],
        ["High", "Mid"], "Low")

    c["risk_tier"] = "Lapsed"
    c.loc[act, "risk_tier"] = np.select(
        [c.loc[act, "churn_prob_12m"] >= C.CHURN_HIGH_RISK,
         c.loc[act, "churn_prob_12m"] >= C.CHURN_MEDIUM_RISK], ["High", "Medium"], "Low")

    c["revenue_at_risk"] = (c.revenue_t12m.clip(lower=0) * c.churn_prob_12m).fillna(0.0)

    # Value-scaled "at risk" trigger (see config: asymmetric cost of errors)
    quiet = c.recency_days >= C.MIN_SILENCE_DAYS_FOR_CADENCE_ALERT
    overdue = c.cadence_status.isin(["Slipping", "Lapsed"]) & quiet
    lapsed_cad = c.cadence_status.eq("Lapsed") & quiet
    p = c.churn_prob_12m.fillna(1.0)
    c["at_risk_flag"] = np.select(
        [c.value_tier == "High", c.value_tier == "Mid", c.value_tier == "Low"],
        [(p >= C.AT_RISK_HIGH_VALUE_PROB) | overdue,
         (p >= C.AT_RISK_OTHER_PROB) | lapsed_cad,
         (p >= C.AT_RISK_OTHER_PROB)], False).astype(bool)
    c["at_risk_reason"] = np.select(
        [~c.at_risk_flag,
         (p >= C.AT_RISK_OTHER_PROB),
         (p >= C.AT_RISK_HIGH_VALUE_PROB) & (c.value_tier == "High") & overdue,
         (p >= C.AT_RISK_HIGH_VALUE_PROB) & (c.value_tier == "High")],
        ["", "High churn probability", "Elevated probability + overdue on cadence",
         "Elevated churn probability"], "Overdue vs own buying cadence")

    def seg(r):
        if not r.is_active_12m:
            return SEGMENT_ORDER[7]
        if r.is_new:
            return SEGMENT_ORDER[4]
        if r.value_tier == "High":
            return SEGMENT_ORDER[1] if r.at_risk_flag else SEGMENT_ORDER[0]
        if r.value_tier == "Mid":
            return SEGMENT_ORDER[3] if r.at_risk_flag else SEGMENT_ORDER[2]
        return SEGMENT_ORDER[6] if r.at_risk_flag else SEGMENT_ORDER[5]

    c["management_segment"] = c.apply(seg, axis=1)
    c["historic_revenue"] = c.monetary
    c.index.name = "customer_id"
    return c


def summaries(c: pd.DataFrame) -> dict:
    seg = (c.groupby("management_segment")
           .agg(customers=("monetary", "size"),
                revenue_t12m=("revenue_t12m", "sum"),
                revenue_at_risk=("revenue_at_risk", "sum"),
                clv_12m=("clv_12m", "sum"),
                avg_churn_prob=("churn_prob_12m", "mean"),
                flagged_accounts=("at_risk_flag", "sum"),
                historic_revenue=("historic_revenue", "sum"))
           .reindex(SEGMENT_ORDER).reset_index())
    expo = c[c.at_risk_flag].groupby("management_segment").revenue_t12m.sum()
    seg["flagged_exposure_t12m"] = seg.management_segment.map(expo).fillna(0.0)
    seg["pct_customers"] = seg.customers / seg.customers.sum()
    seg["pct_revenue_t12m"] = seg.revenue_t12m / seg.revenue_t12m.sum()
    seg["pct_revenue_at_risk"] = seg.revenue_at_risk / seg.revenue_at_risk.sum()
    seg = seg.merge(PLAYBOOK, on="management_segment", how="left")

    grid = (c[c.is_active_12m].pivot_table(index="value_tier", columns="risk_tier",
                                           values="revenue_at_risk", aggfunc="sum")
            .reindex(index=["High", "Mid", "Low"], columns=["High", "Medium", "Low"]))
    grid_n = (c[c.is_active_12m].pivot_table(index="value_tier", columns="risk_tier",
                                             values="monetary", aggfunc="size")
              .reindex(index=["High", "Mid", "Low"], columns=["High", "Medium", "Low"]))

    # Scenario: what a retention programme could recover (save rate is an ASSUMPTION)
    rar_total = c.revenue_at_risk.sum()
    hvhr = c.loc[c.management_segment == SEGMENT_ORDER[1], "revenue_at_risk"].sum()
    scen = pd.DataFrame([{"save_rate": s,
                          "recovered_revenue_all_at_risk": rar_total * s,
                          "recovered_revenue_rescue_segment_only": hvhr * s}
                         for s in (0.10, 0.20, 0.30)])

    # Concentration of risk: how many accounts hold half of all revenue at risk?
    r = c.revenue_at_risk.sort_values(ascending=False)
    cum = r.cumsum() / r.sum()
    conc = pd.DataFrame([{"share_of_revenue_at_risk": t,
                          "accounts_needed": int((cum < t).sum() + 1)} for t in (0.25, 0.5, 0.8)])

    cols = ["country", "management_segment", "value_tier", "risk_tier", "revenue_t12m",
            "churn_prob_12m", "revenue_at_risk", "clv_12m", "recency_days", "frequency",
            "avg_gap_days", "cadence_status", "at_risk_reason", "rfm_segment", "historic_revenue"]
    # Ranked by EXPOSURE (trailing-12m revenue): an account-manager call protects the
    # whole account, so the biggest accounts come first. Probability-weighted risk
    # would bury large accounts that are overdue but have a modest model probability.
    hvhr_list = (c[c.management_segment == SEGMENT_ORDER[1]]
                 .sort_values("revenue_t12m", ascending=False)[cols].head(100)
                 .reset_index())
    hvhr_list.insert(0, "priority_rank", range(1, len(hvhr_list) + 1))

    rfm_x = pd.crosstab(c.rfm_segment, c.management_segment)
    return {"segments": seg, "risk_grid_gbp": grid, "risk_grid_customers": grid_n,
            "scenarios": scen, "risk_concentration": conc, "hvhr_top100": hvhr_list,
            "rfm_vs_management": rfm_x}


def run() -> pd.DataFrame:
    c = build()
    c.to_parquet(C.DATA_PROCESSED / "customer_360.parquet")
    s = summaries(c)
    s["segments"].to_csv(C.TABLES / "management_segments.csv", index=False)
    s["risk_grid_gbp"].to_csv(C.TABLES / "value_risk_grid_revenue_at_risk.csv")
    s["risk_grid_customers"].to_csv(C.TABLES / "value_risk_grid_customers.csv")
    s["scenarios"].to_csv(C.TABLES / "retention_scenarios.csv", index=False)
    s["risk_concentration"].to_csv(C.TABLES / "revenue_at_risk_concentration.csv", index=False)
    s["hvhr_top100"].to_csv(C.TABLES / "high_value_high_risk_top100.csv", index=False)
    s["rfm_vs_management"].to_csv(C.TABLES / "rfm_vs_management_segments.csv")
    PLAYBOOK.to_csv(C.TABLES / "action_playbook.csv", index=False)
    pd.set_option("display.width", 220)
    print(s["segments"][["management_segment", "customers", "revenue_t12m", "revenue_at_risk",
                         "clv_12m", "avg_churn_prob"]].round(2).to_string(index=False))
    print(f"  TOTAL revenue at risk: £{c.revenue_at_risk.sum():,.0f} "
          f"of £{c.revenue_t12m.clip(lower=0).sum():,.0f} trailing-12m revenue")
    print(s["risk_grid_gbp"].round(0))
    print(s["risk_concentration"])
    return c


if __name__ == "__main__":
    run()

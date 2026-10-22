"""
Builds the six narrative notebooks from source (so they are version-controllable as
code) and executes them. Run from project root:  python notebooks/_build_notebooks.py
Notebooks contain NO business logic — they read pipeline outputs and explain them.
"""
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks"

SETUP = """import sys, pandas as pd
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()
sys.path.insert(0, str(ROOT))
from IPython.display import Image, display
pd.set_option('display.width', 200); pd.set_option('display.max_columns', 30)
pd.set_option('display.float_format', lambda v: f'{v:,.3f}')
T = ROOT / 'reports' / 'tables'; F = ROOT / 'reports' / 'figures'
def fig(name): display(Image(filename=str(F / f'{name}.png')))"""

BOOKS = {
"01_data_audit_and_cleaning": [
("md", """# 01 · Data audit & cleaning
**Business question:** *Can management trust these numbers, and how much of the business can customer analytics actually see?*

Logic lives in `src/cie/ingest.py`, `clean.py`, `audit.py`. This notebook presents the evidence."""),
("code", SETUP),
("md", "## 1. Data-quality scorecard — every issue in rows **and** pounds"),
("code", "pd.read_csv(T / 'data_quality_scorecard.csv')[['dimension','issue','rows_affected','pct_rows','revenue_affected_gbp','pct_of_gross_sales','treatment']]"),
("md", """**Read-out**
* The two source sheets overlap for 1–9 Dec 2010: every one of those invoices appears twice. Removed.
* 22.8% of lines have no Customer ID, but that is **15.1% of gross sales** — customer analytics sees ~85% of revenue.
* Some very large orders were keyed and cancelled minutes later. They net to zero in revenue but would inflate order counts, so they are matched and flagged (rules R5/R5b) rather than simply netted."""),
("md", "## 2. Cleaning log"),
("code", "pd.read_csv(T / 'cleaning_log.csv')"),
("md", "## 3. Non-merchandise codes kept for finance, excluded from customer metrics"),
("code", "pd.read_csv(T / 'non_product_codes.csv').head(20)"),
("md", "## 4. Revenue bridge — ledger to analytics base (must close to £0)"),
("code", "pd.read_csv(T / 'sql_revenue_bridge.csv')"),
("code", "fig('03_missing_customer_id_share')"),
("md", """## What should management do differently?
1. **Make customer identification a KPI.** 15% of sales (and a rising share of growth — see notebook 02) cannot be attributed to a customer, so it cannot be retained, targeted or valued. Require an account/email at checkout or incentivise guest-to-account conversion.
2. **Fix the order-entry process** that allows large orders to be keyed and immediately cancelled; it distorts operational reporting.
3. **Adopt the revenue bridge** as the standard reconciliation between finance revenue and customer-analytics revenue, so the two teams stop debating whose number is right."""),
],
"02_business_kpis_and_eda": [
("md", """# 02 · Business health KPIs & exploratory analysis
**Business question:** *Is the business growing — and is growth coming from more customers, more orders, or bigger orders?*

Fiscal years are defined **Dec–Nov** so both years have 12 complete months (Dec-2011 is partial)."""),
("code", SETUP),
("code", "pd.read_csv(T / 'sql_kpi_fy_comparison.csv')"),
("code", "fig('02_fy_growth_drivers')"),
("code", "fig('01_monthly_sales_identified_vs_guest')"),
("md", """**Read-out (calculated):** merchandise revenue grew +1.7%, but identified-customer sales fell −2.5% while guest sales rose +32%. Orders per customer fell −4.4%; AOV was flat (+0.6%). Sales are strongly seasonal — Sep–Nov is the peak."""),
("code", "pd.read_csv(T / 'sql_kpi_yoy_retention.csv').T"),
("md", "**Read-out:** only 64% of FY2010 customers bought again in FY2011; net revenue retention was 81%. Customers who did not return took ~£1.0M of prior-year revenue with them."),
("code", "fig('06_customer_concentration_pareto'); pd.read_csv(T / 'sql_customer_concentration.csv')"),
("code", "pd.read_csv(T / 'sql_market_mix.csv')"),
("code", "fig('12_order_timing')"),
("md", """## What should management do differently?
1. **Stop reading headline growth as healthy.** Growth came from unidentifiable buyers while the identified base shrank. Report identified and guest revenue separately every month.
2. **Treat retention as the primary growth lever**: a 64% customer retention rate and 81% NRR mean the business must replace ~19% of its revenue every year just to stand still.
3. **Run a key-account programme**: the top 1% of customers generate ~31% of revenue — losing a handful would be material.
4. **Time outreach to buying behaviour**: ~78% of orders are placed between 10:00 and 16:00 (peak at noon), and there is virtually no Saturday trading."""),
],
"03_rfm_and_cohorts": [
("md", """# 03 · RFM segmentation & cohort retention
**Business questions:** *Who are our best customers? When do new customers drop off?*

RFM scoring (see `sql/04_rfm.sql`): R and M are quintiles; **F uses business bins** (1 / 2 / 3–4 / 5–9 / 10+ orders) because ~27% of customers have exactly one order and quintiles would split identical customers arbitrarily. SQL and Python implementations are tested to agree customer-by-customer."""),
("code", SETUP),
("code", "pd.read_csv(T / 'sql_rfm_segment_summary.csv')"),
("code", "fig('07_rfm_segments')"),
("md", "**Read-out:** Champions (14% of customers) and Loyal Customers (18%) generate ~79% of net revenue. Hibernating customers are 28% of the base but 4% of revenue."),
("code", "fig('04_cohort_retention_heatmap')"),
("code", "fig('05_average_retention_curve')"),
("md", """**Read-out and caveats**
* Only ~21% of new customers order again in the month after their first order.
* Retention follows the **calendar**, not customer age: diagonal bands of high retention line up with the Sep–Nov peak for every cohort.
* Cohorts acquired in the 2010 peak retain worse over the following six months (13% vs 22%), but those months are the quiet season and they return for the next peak at similar rates — so this is **seasonality, not lower-quality customers**. Two years of data cannot fully separate the two.
* The Dec-2009 cohort is excluded: it is left-censored (contains existing customers whose earlier history is missing). Early-2010 cohorts are partly affected too."""),
("code", "pd.read_csv(T / 'rfm_vs_management_segments.csv', index_col=0)"),
("md", """**Why RFM is not the final segmentation:** RFM is backward-looking. 72 'Champions' are low-spend frequent buyers, and 78 'Loyal Customers' are already drifting (Rescue segment). Management segments (notebook 06) combine current value with forward-looking risk.

## What should management do differently?
1. **Engineer the second order**: the biggest drop-off happens straight after the first purchase. A second-order programme for new customers within 60 days is the highest-leverage lifecycle intervention.
2. **Plan retention around the season**: re-engage the base before September, not after Christmas.
3. **Judge acquisition cohorts on a like-for-like season**, not on raw month-N retention."""),
],
"04_customer_lifetime_value": [
("md", """# 04 · Customer lifetime value (BG/NBD + Gamma-Gamma)
**Business question:** *What is each customer likely to be worth over the next 12 months, and can we trust that number?*

Model: BG/NBD (purchase count + drop-out) × Gamma-Gamma (spend per purchase), implemented from the original papers in `src/cie/clv.py`. CLV = **revenue**, not profit (no cost/margin data), 12-month horizon, 10% annual discount rate (assumption)."""),
("code", SETUP),
("md", "## 1. Out-of-sample test: calibrate to 9 Jun 2011, predict the next 6 months"),
("code", "pd.read_csv(T / 'clv_validation_summary.csv', index_col=0)"),
("code", "fig('08_clv_validation')"),
("md", "## 2. Direct 12-month backtest (only 12 months of calibration history available)"),
("code", "pd.read_csv(T / 'clv_backtest_12m.csv', index_col=0)"),
("md", """**Read-out — honest assessment**
* **Purchase counts:** BG/NBD predicted 7,566 holdout purchases vs 7,722 actual (−2%); a naive run-rate model predicted 14,167 (+83%).
* **Revenue:** under-predicted by 15% on the 6-month holdout (which contains the Christmas peak).
* **12-month backtest:** with only 12 months of history the model **over-predicted revenue by 34%** — the drop-out parameter cannot be learned from a short, left-censored history.
* **Ranking:** customers the model ranked in the top 20% delivered 76% of actual holdout revenue.

**Conclusion:** use CLV to **rank and prioritise** customers with confidence; treat the absolute £ total as a range, not a point forecast."""),
("code", "pd.read_csv(T / 'clv_assumption_checks.csv')"),
("code", "pd.read_csv(T / 'clv_discount_sensitivity.csv')"),
("code", "pd.read_csv(T / 'clv_params_final.csv', index_col=0)"),
("md", """## What should management do differently?
1. **Allocate retention and service effort by predicted value**, not by last year's revenue alone — the model's ranking is reliable.
2. **Do not put the £ CLV total in a budget as a forecast.** Present it as a range cross-checked against net revenue retention (81%).
3. **Ask Finance for gross margin** by product line; until then, no CLV-based spending limit can be set in profit terms."""),
],
"05_churn_risk_model": [
("md", """# 05 · Churn-risk model
**Business question:** *Which customers are likely to stop buying in the next 12 months?*

Churn is **inferred** (no order in the next 365 days) — customers never formally leave. Why 365 not 180 days: many accounts are seasonal; at a December cutoff 54% of customers are silent for 180 days but many return for the next peak. Training cutoff Dec-2010 is seasonally matched to today's Dec-2011 scoring date."""),
("code", SETUP),
("code", "pd.read_csv(T / 'churn_model_comparison.csv')"),
("md", """**Read-out**
* Logistic regression: CV ROC-AUC **0.785** vs 0.714 for 'days since last order' alone. Gradient boosting adds nothing, so the interpretable model is kept (pre-declared rule).
* The 180-day variant holds its AUC out-of-time (0.78 at a June cutoff) → the ranking generalises across seasons.
* **BG/NBD P(alive) ranks churn worse than random (AUC ~0.38).** It assigns P(alive)=1 to one-time buyers — who churn most. It is therefore *not* used for risk."""),
("code", "fig('09_churn_model_diagnostics')"),
("code", "pd.read_csv(T / 'churn_calibration.csv')"),
("md", "Predicted probabilities match observed churn within ~3 percentage points in every decile. This matters: probabilities are multiplied by revenue to get revenue at risk."),
("code", "pd.read_csv(T / 'churn_lr_coefficients.csv')"),
("code", "pd.read_csv(T / 'churn_model_card.csv', index_col=0)"),
("md", """## What should management do differently?
1. **Trigger outreach from each customer's own rhythm**, not a fixed 'inactive for 90 days' rule. Buying cadence and tenure are the strongest risk signals.
2. **The first repeat purchases are decisive:** customers with one purchase day in a year churn at 61%; with 5–9 purchase days, 11%.
3. **Refresh scores monthly** and track the model's calibration; retrain each December (seasonal alignment)."""),
],
"06_revenue_at_risk_and_actions": [
("md", """# 06 · Revenue at risk, management segments & action plan
**Business question:** *How much revenue is at risk, where, and what should we do about it?*

* **Revenue at risk** = trailing-12m revenue × P(no order in next 12m). An *exposure* measure: it excludes shrinkage by customers who stay.
* **Value tier** = trailing-12m revenue (not CLV — CLV already discounts at-risk customers and would hide them).
* **At-risk trigger scales with value**: high-value accounts are flagged at ≥25% probability *or* when ≥30 days overdue against their own cadence; others at ≥50%."""),
("code", SETUP),
("code", "s = pd.read_csv(T / 'management_segments.csv'); s[['management_segment','customers','revenue_t12m','revenue_at_risk','flagged_accounts','clv_12m','avg_churn_prob','pct_revenue_t12m','pct_revenue_at_risk']]"),
("code", "fig('11_management_segments')"),
("code", "fig('10_value_risk_grid')"),
("code", "pd.read_csv(T / 'revenue_at_risk_concentration.csv')"),
("md", """**Read-out (calculated)**
* **£887k** of **£7.94M** trailing-12m revenue (11.2%) is at risk. Cross-check: churned customers took £1.02M of prior-year revenue last year — same order of magnitude.
* Risk is **diffuse**: 978 accounts hold half of it. Account managers alone cannot address it; most needs automated, cadence-triggered programmes.
* **Rescue segment:** 107 high-value accounts, £472k of trailing revenue, flagged now."""),
("code", "pd.read_csv(T / 'high_value_high_risk_top100.csv').head(15)"),
("code", "pd.read_csv(T / 'action_playbook.csv')"),
("code", "pd.read_csv(T / 'retention_scenarios.csv')"),
("md", """Scenario values use **assumed** save rates. The Excel model (`excel/retention_investment_model.xlsx`) lets Finance set margin, save rates and contact costs; under illustrative assumptions the Rescue outreach breaks even at an ~12% save rate, while calling every low-risk key account does not pay back.

## What should management do differently?
1. **This month:** account managers call the 107 Rescue accounts, largest first (list provided), and record the reason for any slowdown.
2. **Next quarter:** launch cadence-triggered win-back emails for Mid-value at-risk and a second-order programme for new customers.
3. **Measure causally:** hold out a random 10–20% of each targeted segment so the true save rate is measured, not assumed.
4. **Stop spending discretionary incentives** on the Low-value Lapsing segment."""),
],
}


def build():
    ep = ExecutePreprocessor(timeout=300, kernel_name="python3")
    for name, cells in BOOKS.items():
        nb = nbf.v4.new_notebook()
        nb.cells = [nbf.v4.new_markdown_cell(c) if t == "md" else nbf.v4.new_code_cell(c)
                    for t, c in cells]
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3",
                                     "language": "python"}
        ep.preprocess(nb, {"metadata": {"path": str(NB)}})
        nbf.write(nb, NB / f"{name}.ipynb")
        print(f"  notebook: {name}.ipynb")


if __name__ == "__main__":
    build()

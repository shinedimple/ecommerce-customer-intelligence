# 02 · KPI Definitions

One definition per KPI, implemented once in SQL (`sql/03_kpi_overview.sql`) and mirrored in
DAX (`powerbi/dax_measures.dax`). If a number in the dashboard disagrees with the SQL output
table, the dashboard is wrong.

**Global conventions**
* **Merchandise** = stock codes classified as products. Postage, fees, manual adjustments,
  discounts, vouchers, samples and test lines are excluded (kept in the ledger for finance).
* **Reversed pairs** (an order and the cancellation that exactly reverses it) are excluded from
  order counts; they net to £0 either way.
* **Fiscal year (FY)** = December–November, so both years contain 12 complete months.
  FY2010 = Dec-2009…Nov-2010; FY2011 = Dec-2010…Nov-2011. December 2011 (to the 9th) is partial.
* **Identified customer** = line has a Customer ID. Guest lines count in company totals only.
* **Snapshot date** = 10 Dec 2011 (day after the last transaction), used for all "as-of" metrics.

## A. Business health

| KPI | Formula | Grain | Why it matters | Caveat |
|---|---|---|---|---|
| Gross Merch Sales | Σ value of merchandise sale orders | order | Top-line demand | Excludes postage/fees |
| Returns Value | − Σ value of merchandise cancellation lines (unmatched) | order | Leakage | Only returns recorded as C-invoices |
| Return Rate | Returns Value ÷ Gross Merch Sales | period | Product/service quality | Partial returns only; reversed pairs excluded |
| Net Merch Revenue | Gross Merch Sales − Returns Value | period | Headline revenue for this project | ≠ finance revenue (see revenue bridge) |
| Identified Share | Identified sales ÷ Gross Merch Sales | period | How much of the business analytics can see | Guests may be repeat buyers we cannot link |
| Orders | Count of merchandise sale invoices | period | Volume | One invoice = one order |
| AOV | Gross Merch Sales ÷ Orders | period | Basket size | Skewed by wholesale orders; median also reported |

## B. Customer base

| KPI | Formula | Why | Caveat |
|---|---|---|---|
| Active Customers | Distinct identified customers with ≥1 sale order in period | Size of base | Identified only |
| New Customers | Customers whose first-ever order falls in period | Acquisition | Left-censored before ~2010 |
| Orders per Customer | Identified orders ÷ Active Customers | Frequency | — |
| Customer Retention Rate (YoY) | Customers active in FY_t and FY_t+1 ÷ customers active in FY_t | Loyalty | Two years of data → one YoY point (FY10→FY11 = **63.9%**) |
| Net Revenue Retention (NRR) | FY_t+1 revenue from FY_t customers ÷ their FY_t revenue | Combines churn + shrinkage + expansion | FY10→FY11 = **80.8%** |
| Revenue Concentration | Share of net revenue from top N / top x% customers | Key-account dependency | Lifetime revenue, positive-revenue customers |

## C. Customer value & risk (model outputs, pre-computed per customer)

| KPI | Definition | Source | Caveat |
|---|---|---|---|
| Recency | Calendar days from last order to snapshot | RFM | — |
| Frequency | Distinct merchandise sale invoices (lifetime) | RFM | — |
| Monetary | Lifetime net merchandise revenue | RFM | Net of returns |
| RFM scores | R, M quintiles; F business bins 1/2/3–4/5–9/10+ | `sql/04_rfm.sql` | F not quintiles (27% single-order customers) |
| Revenue T12M | Net merchandise revenue in the 365 days to snapshot | churn features | Value tier basis |
| Predicted CLV 12M | Σ monthly E[purchases] × E[spend] × discount (10% p.a.) | BG/NBD + Gamma-Gamma | **Revenue**, not profit; absolute level uncertain (see model validation) — use for ranking |
| P(alive) | BG/NBD probability the customer is still active | BG/NBD | **Not used for risk**: =1 for one-time buyers by construction |
| Churn Probability 12M | P(no order in next 365 days) | Logistic regression | Calibrated to ±3pp; seasonally matched training |
| Cadence Status | Recency ÷ own average gap: ≤1.5 On track, ≤3 Slipping, >3 Lapsed | `sql/06` | Needs ≥3 orders |
| Revenue at Risk | Revenue T12M × Churn Probability 12M | segments | Exposure measure; excludes shrinkage of retained customers |
| Flagged Exposure | Revenue T12M of customers with `at_risk_flag` | segments | Value-scaled trigger (see assumptions log) |

## D. Programme KPIs (to track after launch — not computable from this dataset)

| KPI | Definition | Target owner |
|---|---|---|
| Save rate | Treated at-risk customers who order within 90 days − same rate in random hold-out group | CRM |
| Second-order rate | New customers placing a 2nd order within 90 days | CRM |
| Segment NRR | NRR computed per management segment | Commercial |
| Retention ROI | (Incremental gross profit − programme cost) ÷ programme cost | Finance |
| Identified share of sales | As above, monthly | E-commerce |

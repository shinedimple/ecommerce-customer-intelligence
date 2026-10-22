# 05 · Feasibility — What This Dataset Can and Cannot Support

Stated plainly so that no result is over-claimed.

## Fields available
`Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID, Country` —
1,067,371 lines, 1 Dec 2009 – 9 Dec 2011, two Excel sheets (overlapping 1–9 Dec 2010).

## ✅ Supported (done in this project)

| Analysis | Confidence | Why it is supported |
|---|---|---|
| Revenue, orders, AOV, returns KPIs | High | Complete transaction ledger |
| Revenue reconciliation (ledger → analytics) | High | Every line is classified; bridge closes to £0.00 |
| RFM segmentation | High | Needs only dates, invoices, values |
| Cohort retention | Medium-high | 24 months of history; earliest cohorts left-censored |
| Customer concentration | High | Customer-level revenue |
| Predictive CLV (revenue) | **Medium for ranking, low-medium for £ level** | Validated: counts −2% on 6-month holdout, but revenue −15% (6m) / +34% (12m thin-history backtest) |
| Churn-risk scoring | Medium-high | One full-year labelled window; CV AUC 0.785, well calibrated |
| Revenue at risk | Medium | Product of two validated quantities; excludes shrinkage |
| Product return rates, market mix, order timing | High (descriptive) | Direct from ledger |

## ⚠️ Supported only with material caveats

| Analysis | Caveat |
|---|---|
| "New customer" counts before ~mid-2010 | Customers first seen in Dec-2009/early 2010 may be long-standing (left-censoring) |
| Year-on-year retention | Only **one** YoY observation (FY10→FY11) — no trend |
| Out-of-time validation of the 12-month churn label | Only one cutoff has a full future year; primary model validated by cross-validation. A 180-day variant was tested out-of-time |
| Seasonality effects | Two peaks observed; cannot separate cohort quality from calendar effects reliably |
| Customer type (wholesale vs retail) | Not labelled; could only be inferred from order size, which would be an assumption |

## ❌ Not supported (and not attempted)

| Requested / typical analysis | Missing data | What would be needed |
|---|---|---|
| **Profit-based CLV**, margin by segment | No cost of goods / margin | Product-level COGS or category margins from Finance |
| **CAC, LTV:CAC, marketing ROI** | No marketing spend, no acquisition channel | Spend by channel; first-touch attribution |
| **Causal effect of any intervention** | No campaign / treatment data | Randomised hold-out groups in future campaigns |
| **Demographic or firmographic segmentation** | Only country is known | CRM attributes (business type, size, region) |
| **Reasons for churn** | No survey, complaints, service or price data | Lost-customer survey; service logs; competitor pricing |
| **Guest-customer behaviour** | 15.1% of sales have no ID | Mandatory accounts or email-based identity resolution |
| **True churn** | Non-contractual; churn is never observed | — (inherent; handled by probabilistic definition) |
| **Price elasticity / promotion effects** | No promotion flags; list vs paid price unknown | Promotion calendar, price history |
| **Inventory / fulfilment analysis** | Only damaged/lost adjustments visible | Stock and delivery data |
| **A native Power BI `.pbix`** | Tooling, not data | Built in Power BI Desktop from the provided spec |

## Implication for how results should be used
* Use **rankings and segments** operationally now (they are validated).
* Use **£ totals** (CLV, revenue at risk, recovered revenue) as **ranges for planning**, not
  budget commitments, until margin data and a measured save rate are available.
* The single highest-value data investment is **customer identification** — it enlarges the
  base every other analysis runs on.

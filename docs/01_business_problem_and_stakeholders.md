# 01 · Business Problem, Stakeholders & Questions

## Context
The client is a UK-based online retailer of giftware and homeware whose customers are a
mix of wholesalers and individual buyers (per the UCI dataset documentation — the data itself
does not label customer type). Revenue is in GBP (also per dataset documentation). The data
covers every recorded transaction line from **1 Dec 2009 to 9 Dec 2011**.

## The problem management asked us to solve
> "Revenue looks flat-to-up, but we have no view of *which* customers drive it, who we are
> losing, or what that is worth. We spend sales and marketing effort evenly across the base.
> Tell us where to focus."

Restated as an analytics brief:

1. **Diagnose** — Is growth healthy? Where does it come from (customers × frequency × basket)?
2. **Value** — What is each customer worth today and over the next 12 months?
3. **Risk** — Who is likely to stop buying, and how much revenue does that put at risk?
4. **Act** — Which customers should receive which intervention, and is it worth the cost?

## Stakeholders

| Stakeholder | What they need from this project | Primary deliverable |
|---|---|---|
| **Managing Director / CEO** | Is the business healthy? Where is the biggest £ lever? | Executive report; dashboard page 1 |
| **Commercial / Sales Director** | Which key accounts to call this month; account-manager capacity | Rescue call list; value × risk page |
| **Marketing / CRM Manager** | Segments, triggers and messages for automated programmes | Management segments + playbook |
| **Finance Director / FP&A** | Reconciled revenue, revenue at risk, ROI of retention spend | Revenue bridge; Excel scenario model |
| **E-commerce / Operations** | Customer ID capture, order-entry errors, order timing | Data-quality scorecard |
| **Data / BI team** | Maintainable, testable pipeline and model | Repo, SQL layer, tests, model cards |

## Business questions → where they are answered

| # | Question | Analysis | Location |
|---|---|---|---|
| Q1 | How much of the business can customer analytics see? | Data-quality audit, revenue bridge | `sql/08`, notebook 01 |
| Q2 | Is the business growing, and why? | FY KPI decomposition | `sql/03`, notebook 02 |
| Q3 | How dependent are we on a few customers? | Pareto concentration | `sql/07`, notebook 02 |
| Q4 | Who are our best / slipping / lost customers? | RFM | `sql/04`, notebook 03 |
| Q5 | When do new customers drop off? | Cohort retention | `sql/05`, notebook 03 |
| Q6 | What will each customer be worth next year? | BG/NBD + Gamma-Gamma CLV | `src/cie/clv.py`, notebook 04 |
| Q7 | Who is likely to stop buying? | Churn model + cadence rules | `src/cie/churn.py`, `sql/06`, notebook 05 |
| Q8 | How much revenue is at risk, and where? | Revenue at risk, value × risk grid | `src/cie/segments.py`, notebook 06 |
| Q9 | What should we do, for whom, and does it pay? | Management segments, playbook, scenario model | notebook 06, Excel |

## Success criteria for the project
* Every KPI reconciles to the ledger (revenue bridge closes to £0.00 — achieved).
* Every model is validated out-of-sample against a simple baseline (achieved; results reported
  including where the model is weak).
* Every finding ends in an owner-able action (see executive report).

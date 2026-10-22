# 04 · Power BI Dashboard Specification

> **Scope note:** a `.pbix` file cannot be generated outside Power BI Desktop. This repository
> provides everything needed to build it in ~2–3 hours: the model tables (`powerbi/data/`),
> relationships (below), the DAX library (`powerbi/dax_measures.dax`), page-by-page visual
> specs, and validation checks. Screenshots of the finished dashboard should be added to
> `reports/figures/dashboard_*.png` once built.

## 1. Build guide

1. **Get data**
   * Text/CSV: `dim_customer`, `dim_date`, `dim_product`, `dim_country`, `fact_orders`,
     `seg_playbook`, `kpi_monthly`, `cohort_retention`, `churn_calibration`,
     `clv_validation_by_decile`, `revenue_bridge`.
   * Parquet: `fact_sales_lines.parquet` (only needed for the product page).
2. **Types (Power Query):** `customer_id` and `stock_code` as **Text** (never numbers — codes
   like `85123A` exist); dates as Date; booleans as True/False.
3. **Relationships** (all many-to-one, single direction, dimension → fact):

| From (many) | To (one) |
|---|---|
| `fact_orders[order_date]` | `dim_date[date_key]` |
| `fact_orders[customer_id]` | `dim_customer[customer_id]` |
| `fact_orders[country]` | `dim_country[country]` |
| `fact_sales_lines[invoice_date]` | `dim_date[date_key]` |
| `fact_sales_lines[stock_code]` | `dim_product[stock_code]` |
| `fact_sales_lines[customer_id]` | `dim_customer[customer_id]` |
| `dim_customer[management_segment]` | `seg_playbook[management_segment]` (one side = playbook) |

   Guest orders have a blank `customer_id`; they correctly fall into the blank member.
4. **Mark `dim_date` as date table**; sort `month_label` by `year_month`; sort
   `management_segment` alphabetically (segment names are numbered 1–8 for this reason).
5. **Measures:** create table `_Measures`; paste measures from `powerbi/dax_measures.dax`.
6. **What-if parameters:** `Save Rate` (0–0.5, default 0.2) and `Gross Margin`
   (0.2–0.6, default 0.4, labelled **ASSUMPTION**).
7. **Validate before publishing** (must match exactly):

| Check | Expected (from `reports/tables/`) |
|---|---|
| Net Merch Revenue, FY2011 | £9,299,887 |
| Identified Sales, FY2010 / FY2011 | £8,175,241 / £7,969,508 |
| Active Customers, FY2011 | 4,284 |
| Revenue at Risk (all) | £887,322 |
| Customers in Rescue segment | 107 |

## 2. Pages

Theme: navy `#1F3A5F` (value), teal `#2A9D8F` (good), coral `#E76F51` (risk), gold
`#E9C46A` (guest/unknown). Every page carries the `Data As-Of Label` measure in a footer card.
Global slicers (sync across pages): Fiscal Year, Region, Value Tier.

### Page 1 — Executive Overview ("Is the business healthy?")
| Visual | Fields | Purpose |
|---|---|---|
| 6 KPI cards | Net Merch Revenue (+YoY %), Active Customers, Orders per Customer, AOV, Identified Share %, Revenue at Risk | Headline |
| Stacked column | `dim_date[year_month]` × Identified Sales / Guest Sales (complete months) | Growth source |
| Clustered bar | FY2010 vs FY2011 for Identified Sales, Guest Sales, Active Customers | YoY bridge |
| Text box (dynamic) | `Revenue at Risk Title` | The headline sentence for management |

### Page 2 — Customer Base & Retention ("Are we keeping customers?")
| Visual | Fields |
|---|---|
| Matrix heatmap | `cohort_retention`: rows cohort_month, columns months_since_first, values retention_rate (conditional formatting); filter `is_left_censored = False` |
| Line | Average retention by months_since_first |
| Card pair | Customer retention 63.9%, NRR 80.8% (from `kpi_yoy_retention` — static cards with source note) |
| Column | New vs Returning Customers by month |

### Page 3 — Segmentation ("Who are our customers?")
| Visual | Fields |
|---|---|
| Treemap | `dim_customer[rfm_segment]` sized by `lifetime_net_revenue` |
| Bar | Customers vs revenue share by RFM segment |
| Table | Management segment × Customers, Revenue T12M, Predicted CLV 12M, Avg Churn Probability |
| Scatter | x = `recency_days`, y = `lifetime_orders` (log), size = `revenue_t12m`, legend = `management_segment` |

### Page 4 — Value × Risk ("Where is revenue at risk?")
| Visual | Fields |
|---|---|
| Matrix 3×3 | rows `value_tier` (High/Mid/Low), cols `risk_tier` (High/Medium/Low), values Revenue at Risk + Customers; red conditional formatting |
| Bar | Revenue T12M vs Revenue at Risk by management segment |
| Cards | Flagged At-Risk Accounts, Flagged Exposure T12M, Rescue Segment Exposure |
| Card + slicer | Save Rate, Gross Margin parameters → Recovered Revenue / Recovered Gross Profit (scenario) |

### Page 5 — Action List ("Who do we call this week?")  *(Row-level security for account managers)*
| Visual | Fields |
|---|---|
| Table | customer_id, country, revenue_t12m, churn_prob_12m, recency_days, avg_gap_days, cadence_status, at_risk_reason, clv_12m — filtered to `at_risk_flag = TRUE`, sorted by revenue_t12m desc |
| Slicer | management_segment (default: Rescue) |
| Card (from `seg_playbook`) | objective, action, channel, success_kpi for the selected segment |
| Drill-through | to a customer detail page (order history from `fact_orders`) |

### Page 6 — Model Trust ("Can we rely on the scores?")
| Visual | Fields |
|---|---|
| Line (with diagonal reference) | `churn_calibration`: mean_predicted vs observed_rate |
| Clustered column | `clv_validation_by_decile`: actual vs predicted revenue |
| Table | `revenue_bridge` (reconciliation) |
| Text | Model card summary: label definition, AUC 0.785, CLV = revenue not profit, refresh cadence |

## 3. Refresh & governance
* Refresh cadence: monthly (rerun `python pipeline.py`, then refresh dataset).
* Retrain churn model each December (seasonal alignment); monitor calibration monthly.
* RLS on page 5: account managers see only their accounts (requires an account-owner mapping
  that is **not** in this dataset).

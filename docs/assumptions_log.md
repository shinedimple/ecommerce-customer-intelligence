# Assumptions & Decisions Log

Every analytical decision that could change a result, with the reason, the alternative that
was rejected, and how sensitive the result is. **C** = calculated from data, **A** = assumption,
**D** = design decision (a judgement, not a fact).

## Data preparation

| ID | Type | Decision | Why | Alternative rejected | Impact / sensitivity |
|---|---|---|---|---|---|
| R1 | C | Drop sheet-2 invoices that also appear in sheet 1 | All 1,088 invoices dated 1–9 Dec 2010 appear in both sheets, line-for-line | Keep both | Would double-count 22,523 lines / £377k |
| R2 | **A** | Drop exact duplicate lines within a sheet | Treated as system double-posts | Keep (treat as two identical scans) | 11,812 lines / £54k (0.3% of sales) — immaterial either way |
| R3 | D | Classify lines (sale, cancellation, bad-debt, stock adjustment, zero-price) instead of deleting | Finance must reconcile to ledger | Delete negatives/zeros | None on totals; enables revenue bridge |
| R4 | D | Exclude postage, fees, manual, discount, voucher, sample, test codes from customer metrics | They are not merchandise demand | Include | £75.7k net; `DCGS*` codes verified as real products and kept |
| R5 | D | Match each cancellation to the latest earlier sale with same customer, product, qty, price | Keyed-then-cancelled orders (up to 80,995 units) inflate order counts | Net revenue only | 6,091 pairs; changes frequency for affected customers, not revenue |
| R5b | D | Also match manual ('M') credits that exactly equal a product sale within 7 days | e.g. a £38,970 order credited back via code M within minutes | Ignore | 9 pairs / £39.1k; remaining manual credits cannot be tied to orders (limitation) |
| R7 | D | One home country per customer (modal) | 13 customers appear in 2 countries | Split | Negligible |
| — | **A** | Currency is GBP; business is a UK online giftware retailer with many wholesale customers | Per UCI dataset documentation, not verifiable from the data | — | Labels only |

## Business calendar

| Type | Decision | Why |
|---|---|---|
| D | Fiscal year = Dec–Nov | Gives two complete 12-month years; calendar 2011 would be missing most of December |
| D | Dec-2011 excluded from monthly trend charts | Only 9 days; would look like a collapse |
| D | Dec-2009 cohort excluded from retention averages | Left-censored |

## Segmentation

| Type | Decision | Why |
|---|---|---|
| D | F score uses business bins, not quintiles | ~27% of customers have 1 order; quintiles would assign identical customers different scores |
| D | Management segments use trailing-12m revenue for value | CLV already discounts at-risk customers — tiering on it would hide the ones to rescue |
| D | Value tiers: top 20% High, next 30% Mid, bottom 50% Low (active customers) | Common, explainable split; the top 20% (850 accounts) hold 73% of trailing-12m revenue |
| **A** | At-risk trigger scales with value: High = churn ≥25% OR overdue on own cadence (≥30 days silent); Mid = ≥50% OR cadence lapsed; Low = ≥50% | High-value accounts rarely exceed 50% probability (median 6%), yet a miss is expensive and a false alarm costs one call. **Tunable** in `config.py` |
| **A** | New customer = first order within 90 days | Aligned with a 60–90-day second-order programme |

## Models

| Type | Decision | Why | Sensitivity / evidence |
|---|---|---|---|
| D | BG/NBD + Gamma-Gamma for CLV | Standard for non-contractual, continuous purchasing | Beats naive run-rate (purchase MAE 1.04 vs 1.91) |
| D | Purchase occasion = customer-day | Several invoices in a day are one decision | Standard practice |
| **A** | 12-month horizon | Planning horizon, not "lifetime" | — |
| **A** | 10% annual discount rate | Placeholder cost of capital | 0% → £8.62M, 20% → £7.82M total CLV (±5%) |
| **A** | CLV = revenue (no margin) | No cost data | Multiply by margin when available (Excel model) |
| C | CLV reliability | 6m holdout: counts −2%, revenue −15%; 12m thin-history backtest: revenue +34% | → use for ranking; £ total as a range |
| **A** | Churn = no order in next 365 days | Seasonal buyers make 180 days misleading in December; matches annual revenue-at-risk | 180-day variant: same ranking quality (AUC 0.78 in- and out-of-time) |
| D | Train churn model at Dec-2010 cutoff | Seasonally matched to Dec-2011 scoring date | June-cutoff base rate differs (43% vs 54% for 180d label) |
| D | Choose logistic regression unless GBM beats it by >0.01 AUC | Pre-declared to avoid cherry-picking; interpretability | GBM 0.782 vs LR 0.785 → LR |
| D | Do not use BG/NBD P(alive) for risk | Ranks churn worse than random (AUC 0.375) | Documented in model comparison |
| **A** | Revenue at risk = trailing-12m revenue × churn probability | A churned customer would otherwise have repeated last year's spend | Excludes shrinkage → **understates** the retention problem (NRR 81%) |

## Scenario model (Excel) — all ASSUMPTIONS, illustrative only
Gross margin 40%; save rates 3–25% by segment; cost per contact £0.50 (automated) to £40
(account manager); overhead £5,000. None of these come from the data; each is a yellow input
cell to be replaced by the business, and save rates must be measured with hold-out groups.

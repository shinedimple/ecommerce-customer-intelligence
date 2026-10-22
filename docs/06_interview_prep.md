# 06 · Interview Preparation

Answers use this project's real numbers and decisions. Learn the reasoning, not the wording.
Structure most answers as **Situation → Decision → Why → Result → Limitation**.

---

## A. The pitch (have these ready word-perfect)

**Q1. Walk me through this project in two minutes.**
> I took two years of raw transaction data from an online giftware retailer (about 1.07M lines)
> and built a customer intelligence pipeline to answer one management question: where should we
> focus to protect and grow revenue?
>
> I first audited the data. I found the two source sheets overlap, so 1,088 invoices were duplicated, and that
> orders of up to 81,000 units were keyed and cancelled minutes later. I built a revenue bridge
> that reconciles the ledger to the analytics base to the penny.
>
> The main finding: headline revenue grew 1.7%, but sales to identifiable customers fell 2.5% while
> guest sales rose 32%, and only 64% of customers came back year-on-year.
>
> I then built and validated a customer lifetime value model and a churn model, estimated £887k of
> next year's revenue at risk, and translated that into eight segments with actions. The top
> priority is 107 high-value accounts worth £472k a year that are drifting.
>
> Everything is reproducible with one command and covered by tests.

**Q2. What was the single most important insight?**
> That growth was hiding a shrinking customer base. Identified-customer sales fell while guest
> sales grew 32%. That changes the first recommendation from "run a retention campaign" to "fix
> customer identification", because 15% of sales can't be retained if we can't see who made them.

**Q3. What would you do differently with more time or data?**
> - Get gross margin, so CLV and the retention budget are in profit terms.
> - Run the first programmes with random hold-out groups, to measure save rates instead of assuming them.
> - Add reasons-for-churn data from the rescue calls.
> - With a third year of data, validate the 12-month CLV properly. The current backtest only had 12 months of calibration history.

---

## B. Data quality & cleaning (Data Analyst)

**Q4. What data-quality issues did you find, and how did you prioritise them?**
> I quantified every issue in rows **and pounds**, because row counts mislead:
> - 22.8% of lines lack a Customer ID, but that's only 15.1% of revenue.
> - 22,523 lines (£377k) were duplicated across the two sheets.
> - 11,812 exact duplicates sat within the sheets (£54k).
> - There were 19,104 cancellation lines, 6 bad-debt write-offs and 3,393 stock adjustments.
> - About 5,800 lines were non-merchandise (postage, fees, manual adjustments).
>
> I prioritised by revenue impact and by whether the issue would bias a model.

**Q5. Why not just drop negative quantities, like most tutorials do?**
> Three reasons:
> - Returns are real economic events. Dropping them overstates revenue by about £1.46M.
> - Some negatives are stock write-offs ("damaged", "lost") with zero price. They aren't returns at all.
> - Netting isn't enough either. An 80,995-unit order cancelled 12 minutes later nets to zero revenue but
>   still counts as an order, which inflates frequency and therefore CLV.
>
> So I matched each cancellation to the sale it reverses (same customer, product, quantity, price)
> and excluded both from order counts. That matched 6,091 pairs.

**Q6. How did you know the sheets overlapped?**
> The date ranges overlapped from 1 to 9 December 2010. I checked the invoice numbers in that window: all
> 1,088 appeared in both sheets with identical lines. I removed them by invoice, not by date,
> and added a test that no invoice appears in both sheets.

**Q7. Tell me about a cleaning decision you got wrong at first.**
> I initially treated stock codes starting "DCGS" as non-merchandise because they looked unusual.
> When I checked descriptions, they were real products sold through a dotcom gift shop ("girls
> party bag", "dog collar"), so I kept them.
>
> Separately, a unit test caught that my manual-credit matching could reuse a credit already
> paired with another line. The imbalance was only £9, but reversed pairs must net to exactly
> zero, so I fixed the logic rather than loosening the test.

---

## C. SQL

**Q8. How did you calculate cohort retention in SQL?**
> - Take each customer's first-order month from `dim_customer`.
> - Take the distinct active months from `fact_orders`.
> - Compute `DATE_DIFF('month', cohort_month, active_month)` as the cohort index.
> - Divide distinct active customers by cohort size.
>
> I excluded the December 2009 cohort from averages because it's left-censored: it contains existing
> customers whose earlier purchases are outside the data.

**Q9. Explain your RFM SQL. Why not quintiles for Frequency?**
> R and M use `NTILE(5)` window functions, with `customer_id` as a tiebreaker for determinism.
> F uses business bins (1 / 2 / 3–4 / 5–9 / 10+ orders), because 27% of customers have exactly one
> order. Quintiles would put identical single-order customers into different F scores purely by
> sort order.
>
> I reimplemented it in Python and a test asserts both give identical scores for all 5,839 customers.

**Q10. How do you make sure your revenue matches Finance's?**
> A bridge query (`sql/08_reconciliation.sql`) walks from total ledger revenue to the analytics base:
> - remove bad-debt write-offs;
> - remove non-merchandise lines;
> - remove guest sales;
> - remove manually reversed sales.
>
> A final row checks the steps sum to zero. It closes to £0.00, and that is also a test.

**Q11. Write a query to find customers overdue relative to their usual buying gap.**
> Use `LAG(order_ts) OVER (PARTITION BY customer_id ORDER BY order_ts)` to get the gaps, then average
> them per customer. Divide days-since-last-order by that average: above 1.5 is "slipping", above 3 is
> "lapsed". Require at least 3 orders for the average to mean anything. (`sql/06_churn_risk_rules.sql`.)

---

## D. Statistics & modelling

**Q12. Why BG/NBD and Gamma-Gamma for CLV?**
> The business is **non-contractual** (customers never cancel, they just stop) and purchases can
> happen at any time. BG/NBD models purchase frequency and the probability a customer has
> silently dropped out. Gamma-Gamma models spend per purchase and pulls noisy individual averages
> toward the population mean.
>
> I implemented both from the original papers with SciPy, because the common `lifetimes`
> library is unmaintained and breaks on current pandas/NumPy.

**Q13. How did you validate CLV, and was it any good?**
> I calibrated on data to June 2011 and predicted the next six months.
> - **Purchase counts:** 7,566 predicted vs 7,722 actual (−2%). A naive run-rate model said 14,167 (+83%).
> - **Revenue:** under-predicted by 15%.
> - **12-month backtest:** with only 12 months of history, it over-predicted revenue by 34%. The drop-out
>   parameter can't be learned from a short, left-censored history.
> - **Ranking:** the model's top 20% of customers delivered 76% of actual revenue.
>
> So my conclusion was: use it to rank and prioritise, and present the £ total as a range. I'd rather
> say that than put an unvalidated £8.2M in a budget.

**Q14. What assumptions do those models make, and did you check them?**
> - **Gamma-Gamma assumes spend is independent of frequency.** I checked: Pearson 0.14, Spearman 0.25.
>   That's weak, acceptable, and reported.
> - **BG/NBD assumes no seasonality**, which is violated here. I mitigated it by using a 12-month
>   horizon that contains one full seasonal cycle, and I flagged it.

**Q15. How did you define churn when customers never cancel?**
> As no order in the next 365 days. I started with 180 days, but at a December cutoff 54% of
> customers are silent for 180 days, and many are seasonal buyers who return for the autumn peak.
> 365 days also matches the revenue-at-risk calculation, which multiplies annual revenue by the
> probability of losing the customer for a year.
>
> The trade-off: only one cutoff has a full future year, so I validated with cross-validation. I also
> ran a 180-day version with an out-of-time test to show the ranking generalises across seasons
> (AUC 0.78 both in and out of time).

**Q16. Why logistic regression rather than gradient boosting?**
> I declared the rule before seeing results: use the complex model only if it beats logistic
> regression by more than 0.01 AUC. It didn't (0.782 vs 0.785), so I kept the interpretable,
> well-calibrated model.
>
> Both beat the "days since last order" baseline (0.714). A model must beat the simple rule a
> manager would otherwise use.

**Q17. Something surprising in the modelling?**
> BG/NBD's probability-alive score ranked churn *worse than random* (AUC 0.375). By construction it
> gives one-time buyers P(alive) = 1, because they've never shown a gap. But one-time buyers are the
> most likely to never return. So I used it only for CLV, never for risk. It's a good example of a
> textbook metric being wrong for a specific use.

**Q18. Why does calibration matter here?**
> Because I multiply probabilities by revenue. If the model says 40% and the true rate is 20%,
> revenue at risk is doubled. Predicted and observed churn agree within about 3 percentage points in
> every decile, which is what makes the £ figure defensible.

**Q19. How did you prevent data leakage?**
> Every feature is computed by one function with an explicit cutoff date, using only earlier data.
> A test recomputes the features after physically deleting all post-cutoff rows and asserts
> identical output.

---

## E. Business, finance & strategy (BA / Management / Commercial)

**Q20. How did you calculate revenue at risk, and what are its weaknesses?**
> Each active customer's trailing-12-month revenue times their probability of placing no order in the
> next 12 months. That gives £887k, 11% of the £7.94M run-rate.
>
> Weaknesses:
> - It assumes a lost customer would otherwise have repeated last year's spend.
> - It ignores shrinkage among customers who stay. NRR of 81% shows shrinkage is material, so it
>   understates the problem.
>
> Cross-check: churned customers actually took £1.02M of prior-year revenue last year, the same order of magnitude.

**Q21. Why not tier value by CLV?**
> CLV already discounts customers who are drifting away. If I tiered on it, a £50k account that's
> going quiet would drop out of the high-value tier and off the rescue list. Value tier uses current
> revenue (what's at stake); CLV is kept as a separate field for prioritisation.

**Q22. Initially only one high-value customer was "at risk". What did you do?**
> I treated it as a threshold problem, not good news. High-value accounts rarely exceed a 50% churn
> probability (median 6%), yet losing one costs thousands, while a false alarm costs one phone call.
>
> So the trigger scales with value: key accounts are flagged at 25% probability or when 30+ days
> overdue against their *own* buying rhythm. That produced 107 accounts.
>
> I also added the 30-day minimum after spotting that the top account was flagged for being just
> 10 days quiet after the Christmas peak.

**Q23. How would you prioritise the Rescue list?**
> By exposure (trailing revenue), not probability-weighted risk. An account-manager call protects
> the whole account. Weighting by probability buried a £56k-a-year account that normally orders
> weekly and had been silent 39 days, just because its model probability was 5%.

**Q24. Is a retention programme worth it? You have no cost data.**
> I built an Excel scenario model where margin, save rates and contact costs are explicit, yellow
> input cells. Under illustrative assumptions (40% margin, £40 per account-manager call):
> - Rescue outreach breaks even at an 11.7% save rate.
> - Automated programmes return several times their cost.
> - Calling every low-risk key account loses money.
>
> The real answer is to measure it: hold out 10–20% of each segment at random.

**Q25. The top 1% of customers is 31% of revenue. Opportunity or risk?**
> Both. It's concentration risk — losing a few accounts is material. It also means targeted
> key-account management has high leverage. That's why the Protect and Rescue segments get human
> attention and the long tail gets automation.

**Q26. What would you present to the CEO in one slide?**
> Four things:
> - Growth came from customers we can't see; our identified base shrank 2.5%.
> - £0.89M of next year's revenue is at risk.
> - 107 key accounts need a call this month.
> - Three decisions: rescue programme, automated retention, fix customer ID.

---

## F. Power BI / DAX

**Q27. How would you model this in Power BI?**
> A star schema:
> - **Facts:** `fact_orders` at invoice grain and `fact_sales_lines` at line grain.
> - **Dimensions:** customer, date, product, country, with single-direction many-to-one relationships.
> - **Scores:** model outputs are pre-computed in Python and stored on `dim_customer`, so there's
>   one definition. DAX only aggregates.
>
> Before publishing, I'd check the FY totals match the SQL outputs exactly.

**Q28. Write a DAX measure for YoY revenue growth.**
```DAX
Net Merch Revenue PY = CALCULATE([Net Merch Revenue], DATEADD(dim_date[date_key], -12, MONTH))
Net Merch Revenue YoY % = DIVIDE([Net Merch Revenue] - [Net Merch Revenue PY], [Net Merch Revenue PY])
```
> `DIVIDE` handles divide-by-zero. `dim_date` must be marked as a date table.

**Q29. How would you let managers explore retention scenarios?**
> What-if parameters for save rate and gross margin feeding `Recovered Revenue` and
> `Recovered Gross Profit`. The margin parameter is labelled as an assumption on the page.

---

## G. Critical / behavioural questions

**Q30. What are the biggest limitations of your analysis?**
> - No margin data, so CLV is revenue, not profit.
> - No marketing or campaign data, so no CAC or causal claims.
> - 15% of sales unattributable.
> - Only one year-on-year observation.
> - Left-censoring of early cohorts.
> - CLV £ totals that are directionally uncertain.
>
> I documented each in a feasibility note and an assumptions log, and separated calculated results from assumptions throughout.

**Q31. How did you avoid "inventing facts"?**
> - Every number in the report traces to a CSV in `reports/tables/`.
> - Assumptions are labelled as such: margin, save rates, contact costs, discount rate.
> - Where the data couldn't answer a question, I said so rather than guessing. For example,
>   whether new customers fell or just started checking out as guests is unanswerable here.

**Q32. How would you put this into production?**
> - Monthly pipeline run on new transactions.
> - Scores pushed to the CRM.
> - Model retrained every December for seasonal alignment.
> - Calibration monitored monthly, with an alert if predicted vs observed drifts more than 5 points.
> - Hold-out groups on every campaign so save rates feed back into the ROI model.

---

## Numbers to memorise
| Metric | Value |
|---|---|
| Raw lines / after de-duplication | 1,067,371 / 1,033,036 |
| Revenue without Customer ID | 15.1% |
| FY11 vs FY10: total / identified / guest | +1.7% / −2.5% / +32.1% |
| Customer retention / NRR | 63.9% / 80.8% |
| Top 10 / top 1% / top 20% revenue share | 16% / 31% / 77% |
| Month-1 repeat rate, new customers | 21% |
| CLV holdout: counts / revenue / 12m backtest | −2% / −15% / +34% |
| Churn model CV AUC (vs recency) | 0.785 (0.714) |
| Revenue at risk | £887k of £7.94M (11.2%) |
| Rescue segment | 107 accounts, £472k/yr |

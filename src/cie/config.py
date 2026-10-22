"""
Central configuration for the Customer Intelligence & LTV Engine.

Every analytical parameter that changes a result lives here, so that a reviewer can
see (and challenge) each assumption in one place instead of hunting through code.
Each parameter carries a note on WHY it has its value.
"""
from pathlib import Path
import pandas as pd

# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
POWERBI_DATA = ROOT / "powerbi" / "data"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
TABLES = REPORTS / "tables"
SQL_DIR = ROOT / "sql"
WAREHOUSE = DATA_PROCESSED / "warehouse.duckdb"

RAW_XLSX = DATA_RAW / "online_retail_II.xlsx"
RAW_PARQUET = DATA_INTERIM / "raw_combined.parquet"
CLEAN_PARQUET = DATA_PROCESSED / "fact_sales_lines.parquet"

for _p in (DATA_INTERIM, DATA_PROCESSED, POWERBI_DATA, FIGURES, TABLES):
    _p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------------------
# Business calendar
# --------------------------------------------------------------------------------------
# The data ends on 2011-12-09. Treating 9 December as a full month would make December
# 2011 look like a collapse, so month-level trend charts exclude it (flag, not delete).
LAST_FULL_MONTH = pd.Period("2011-11", freq="M")

# Snapshot ("as-of") date for RFM and risk scoring = day after the last transaction.
# Set in code from data (max date + 1 day) — kept here only as documentation.
SNAPSHOT_RULE = "max(InvoiceDate) + 1 day"

# --------------------------------------------------------------------------------------
# Cleaning rules
# --------------------------------------------------------------------------------------
# Stock codes that are NOT merchandise (fees, postage, manual adjustments, samples,
# vouchers, test lines). Identified by auditing the StockCode/Description pairs,
# see reports/tables/non_product_codes.csv. They are kept in the fact table with a
# flag so finance can still reconcile totals, but excluded from product and
# customer-behaviour metrics.
NON_PRODUCT_CODES = {
    "POST", "DOT", "M", "C2", "D", "S", "B", "CRUK", "PADS", "BANK CHARGES",
    "AMAZONFEE", "ADJUST", "ADJUST2", "TEST001", "TEST002", "GIFT", "SP1002",
}
NON_PRODUCT_PREFIXES = ("GIFT_", "gift_", "DCGS", "BANK")

# --------------------------------------------------------------------------------------
# Customer analytics parameters
# --------------------------------------------------------------------------------------
# Holdout window used to VALIDATE the CLV and churn models out-of-sample.
# 6 months is long enough to contain a meaningful number of repeat orders for a
# business whose median repeat gap is ~2 months, while leaving 18 months to learn from.
CALIBRATION_END = pd.Timestamp("2011-06-09 23:59:59")
HOLDOUT_DAYS = 183

# Forward horizon for predictive CLV. 12 months is a management planning horizon
# (annual budget) — NOT a claim about true customer lifetime.
CLV_HORIZON_DAYS = 365

# Annual discount rate for CLV. ASSUMPTION: 10% is a common placeholder cost of
# capital; the company's real WACC is not in the data. Sensitivity is reported.
ANNUAL_DISCOUNT_RATE = 0.10

# Gross margin is NOT in the data. CLV is therefore reported as REVENUE CLV.
# A margin parameter is exposed only for the scenario workbook; default None means
# "do not convert to profit" in the Python outputs.
ASSUMED_GROSS_MARGIN = None

# Churn label for the supervised risk model: customer places no order in the
# 365 days after the cutoff. 365 (not 180) because many accounts are seasonal —
# see src/cie/churn.py docstring and docs/assumptions_log.md.
CHURN_WINDOW_DAYS = 365

# Customers need >= this many distinct invoices before a "personal cadence" is
# meaningful for the overdue-ratio risk signal.
MIN_ORDERS_FOR_CADENCE = 3

# Risk tiers on the supervised 12-month churn probability (business thresholds,
# tunable). NOTE: BG/NBD P(alive) is deliberately NOT used for risk tiers — it assigns
# P(alive)=1 to one-time buyers and ranked churn worse than random in validation.
CHURN_HIGH_RISK = 0.50
CHURN_MEDIUM_RISK = 0.25

# "At risk" trigger scales with account value (asymmetric cost of errors):
#   High value : churn prob >= 0.25 OR overdue vs own cadence (Slipping / Lapsed)
#   Mid value  : churn prob >= 0.50 OR cadence Lapsed
#   Low value  : churn prob >= 0.50
# WHY: high spenders almost never reach a 50% churn probability (median 6%), yet
# losing one costs thousands. A false alarm costs one account-manager call; a miss
# costs the account. So the trigger is more sensitive where the stakes are higher.
AT_RISK_HIGH_VALUE_PROB = 0.25
AT_RISK_OTHER_PROB = 0.50
# The cadence trigger also needs a minimum ABSOLUTE silence: a 10-day gap for an
# account that orders every 5 days (e.g. just after the Christmas peak) is noise,
# and false alarms erode account managers' trust in the list.
MIN_SILENCE_DAYS_FOR_CADENCE_ALERT = 30

# Value tiers on predicted 12-month CLV (share of customers, ranked).
VALUE_TOP_SHARE = 0.20      # "High value"
VALUE_MID_SHARE = 0.30      # next 30% = "Mid value"; remaining 50% = "Low value"

# New-customer window: first order within this many days of the snapshot.
NEW_CUSTOMER_DAYS = 90

RANDOM_STATE = 42

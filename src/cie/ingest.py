"""
Step 1 — Ingestion.

WHY: The source is a 45 MB Excel workbook with two sheets (2009-10 and 2010-11).
Reading Excel takes minutes; every later step reads a Parquet copy in seconds.
Ingestion deliberately does NO cleaning — it only standardises column names and
types and records which sheet a row came from, so data-quality issues remain
visible to the audit step.
"""
import pandas as pd

from . import config as C

COLS = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_ts",
    "Price": "unit_price",
    "Customer ID": "customer_id",
    "Country": "country",
}


def load_raw(force: bool = False) -> pd.DataFrame:
    if C.RAW_PARQUET.exists() and not force:
        return pd.read_parquet(C.RAW_PARQUET)

    frames = []
    for sheet in ("Year 2009-2010", "Year 2010-2011"):
        # Read identifier columns as text: StockCode/Invoice mix numbers and letters
        # ('C489449', '85123A'); letting Excel infer types would corrupt them.
        df = pd.read_excel(
            C.RAW_XLSX, sheet_name=sheet,
            dtype={"Invoice": str, "StockCode": str, "Description": str, "Country": str},
            engine="openpyxl",
        )
        df["source_sheet"] = sheet
        df["source_row"] = range(2, len(df) + 2)  # Excel row number for traceability
        frames.append(df)

    raw = pd.concat(frames, ignore_index=True).rename(columns=COLS)
    raw["customer_id"] = raw["customer_id"].astype("Int64").astype("string")
    raw["invoice_ts"] = pd.to_datetime(raw["invoice_ts"])
    raw.to_parquet(C.RAW_PARQUET, index=False)
    return raw


if __name__ == "__main__":
    df = load_raw(force=True)
    print(df.shape)
    print(df.dtypes)

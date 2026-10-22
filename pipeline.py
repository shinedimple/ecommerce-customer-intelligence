"""
One-command, reproducible build of the whole project.

    python pipeline.py            # full run (first run reads Excel: ~5-10 min)
    python pipeline.py --from clv # resume from a step

Each step reads the previous step's persisted output, so any step can be rerun alone
(e.g. `python -m src.cie.churn`). Random seeds are fixed in src/cie/config.py.
"""
import argparse
import time

from src.cie import (audit, churn, clean, clv, eda, excel_pack, export_powerbi, ingest,
                     rfm, segments, warehouse)

STEPS = [
    ("ingest", lambda: ingest.load_raw(force=False)),
    ("clean", clean.run),
    ("audit", audit.run),
    ("warehouse", warehouse.build),      # SQL layer: star schema + business queries
    ("rfm", rfm.run),
    ("clv", clv.run),
    ("churn", churn.run),
    ("segments", segments.run),          # value x risk, revenue at risk, playbook
    ("eda", eda.run),                    # figures
    ("powerbi", export_powerbi.run),
    ("excel", excel_pack.build),
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="ingest",
                    choices=[s for s, _ in STEPS])
    args = ap.parse_args()
    names = [s for s, _ in STEPS]
    for name, fn in STEPS[names.index(args.start):]:
        t = time.time()
        print(f"[{name}]")
        fn()
        print(f"[{name}] done in {time.time() - t:.1f}s\n")

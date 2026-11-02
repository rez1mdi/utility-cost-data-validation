"""Generate a SYNTHETIC utility invoice and meter-reading dataset.

All values are randomly generated for demonstration. No real institution's
data is used. The script deliberately plants common data problems
(duplicates, missing values, billing mismatches, outliers) so the
validation pipeline has something to find.
"""
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
OUT = Path(__file__).resolve().parents[1] / "data" / "raw"

BUILDINGS = {
    "B01": ("Library", 1.6),
    "B02": ("Science Hall", 2.2),
    "B03": ("Student Center", 1.3),
    "B04": ("Residence Hall A", 1.0),
    "B05": ("Residence Hall B", 1.0),
    "B06": ("Arts Building", 0.8),
}
UTILITIES = {  # utility: (base monthly usage, unit, rate per unit)
    "Electric": (60_000, "kWh", 0.098),
    "Gas": (4_000, "therm", 0.92),
    "Water": (350, "kgal", 11.40),
}
MONTHS = pd.period_range("2024-07", "2026-06", freq="M")


def seasonal_factor(utility: str, month: int) -> float:
    if utility == "Electric":   # summer cooling peak
        return 1 + 0.30 * np.cos((month - 7) / 12 * 2 * np.pi)
    if utility == "Gas":        # winter heating peak
        return 1 + 0.60 * np.cos((month - 1) / 12 * 2 * np.pi)
    return 1 + 0.10 * np.cos((month - 9) / 12 * 2 * np.pi)  # water: semester


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    meters, invoices = [], []
    inv_id = 1000
    for bcode, (bname, size) in BUILDINGS.items():
        for util, (base, unit, rate) in UTILITIES.items():
            for p in MONTHS:
                usage = base * size * seasonal_factor(util, p.month) * RNG.normal(1, 0.05)
                usage = round(max(usage, 0), 1)
                meters.append({"building_id": bcode, "building_name": bname, "utility": util,
                               "unit": unit, "period": str(p), "meter_usage": usage})
                billed = usage
                amount = round(billed * rate, 2)
                inv_id += 1
                invoices.append({"invoice_id": f"INV-{inv_id}", "building_id": bcode, "utility": util,
                                 "period": str(p), "billed_usage": billed, "rate": rate,
                                 "amount_usd": amount})
    m, i = pd.DataFrame(meters), pd.DataFrame(invoices)

    # ---- plant data-quality problems ----
    idx = RNG.choice(i.index, 6, replace=False)
    i.loc[idx[:3], "billed_usage"] = (i.loc[idx[:3], "billed_usage"] * 1.18).round(1)  # usage mismatch
    i.loc[idx[3:], "amount_usd"] = (i.loc[idx[3:], "amount_usd"] * 1.25).round(2)      # amount != usage x rate
    i = pd.concat([i, i.sample(3, random_state=1)], ignore_index=True)                  # duplicate invoices
    i.loc[RNG.choice(i.index, 2, replace=False), "amount_usd"] = np.nan                 # missing amounts
    m.loc[RNG.choice(m.index, 2, replace=False), "meter_usage"] = np.nan                # missing reads
    spike = RNG.choice(m.index, 2, replace=False)
    m.loc[spike, "meter_usage"] = m.loc[spike, "meter_usage"] * 4                       # meter spikes
    return m, i


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    meters, invoices = build()
    meters.to_csv(OUT / "meter_readings.csv", index=False)
    invoices.to_csv(OUT / "utility_invoices.csv", index=False)
    print(f"Wrote {len(meters)} meter rows and {len(invoices)} invoice rows to {OUT}")

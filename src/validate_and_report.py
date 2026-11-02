"""Validate utility invoices against meter readings, then build a clean
reporting table and a monthly cost-trend summary.

Steps
1. Load raw invoices and meter readings (Pandas).
2. Run data-quality checks and write every issue to an exceptions file.
3. Load clean data into SQLite and build the reporting table with SQL.
4. Export summary tables and a trend chart for a Power BI-style report.
"""
from pathlib import Path
import sqlite3

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "output"
SQL_FILE = ROOT / "sql" / "reporting_queries.sql"
USAGE_TOLERANCE = 0.02   # billed usage may differ from the meter by up to 2%
AMOUNT_TOLERANCE = 0.01  # amount must equal usage x rate within $0.01


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    inv = pd.read_csv(RAW / "utility_invoices.csv")
    met = pd.read_csv(RAW / "meter_readings.csv")
    return inv, met


def check_quality(inv: pd.DataFrame, met: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean invoices joined to meters, exceptions)."""
    issues = []

    def flag(rows: pd.DataFrame, check: str, detail: str) -> None:
        for _, r in rows.iterrows():
            issues.append({"invoice_id": r.get("invoice_id"), "building_id": r["building_id"],
                           "utility": r["utility"], "period": r["period"], "check": check,
                           "detail": detail})

    dup = inv[inv.duplicated("invoice_id", keep="first")]
    flag(dup, "duplicate_invoice", "Invoice ID appears more than once; extra copy removed")
    inv = inv.drop_duplicates("invoice_id", keep="first")

    flag(inv[inv["amount_usd"].isna()], "missing_amount", "Invoice has no billed amount")
    flag(met[met["meter_usage"].isna()], "missing_meter_read", "No meter reading for this period")

    df = inv.merge(met, on=["building_id", "utility", "period"], how="left", validate="one_to_one")

    calc = (df["billed_usage"] * df["rate"]).round(2)
    bad_amt = df[df["amount_usd"].notna() & ((df["amount_usd"] - calc).abs() > AMOUNT_TOLERANCE)]
    flag(bad_amt, "amount_mismatch", "Billed amount does not equal billed usage x rate")

    diff = (df["billed_usage"] - df["meter_usage"]) / df["meter_usage"]
    bad_use = df[df["meter_usage"].notna() & (diff.abs() > USAGE_TOLERANCE)]
    flag(bad_use, "usage_mismatch", "Billed usage differs from meter reading by more than 2%")

    # outlier: meter usage more than 3x the building/utility median
    med = df.groupby(["building_id", "utility"])["meter_usage"].transform("median")
    flag(df[df["meter_usage"] > 3 * med], "meter_outlier", "Meter reading over 3x the usual level")

    exceptions = pd.DataFrame(issues)
    bad_ids = set(exceptions.loc[exceptions["check"] != "duplicate_invoice", "invoice_id"].dropna())
    bad_keys = set(map(tuple, exceptions.loc[exceptions["check"].isin(["missing_meter_read", "meter_outlier"]),
                                             ["building_id", "utility", "period"]].values))
    keep = ~df["invoice_id"].isin(bad_ids) & ~df[["building_id", "utility", "period"]].apply(tuple, axis=1).isin(bad_keys)
    return df[keep].copy(), exceptions


def build_reports(clean: pd.DataFrame) -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(":memory:")
    clean.to_sql("clean_invoices", con, index=False)
    queries = [q.strip() for q in SQL_FILE.read_text().split(";") if q.strip()]
    names = ["monthly_cost_by_utility", "building_cost_summary", "year_over_year"]
    reports = {}
    for name, q in zip(names, queries):
        sql = "\n".join(line for line in q.splitlines() if not line.strip().startswith("--"))
        reports[name] = pd.read_sql_query(sql, con)
    con.close()
    return reports


def chart(monthly: pd.DataFrame) -> None:
    pivot = monthly.pivot(index="period", columns="utility", values="avg_cost_per_building_usd")
    ax = pivot.plot(figsize=(10, 4.5), linewidth=2)
    ax.set_title("Average monthly cost per building, by utility (synthetic data)")
    ax.set_xlabel("Month"); ax.set_ylabel("Cost per building (USD)")
    ax.grid(alpha=0.3)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(OUT / "monthly_cost_trend.png", dpi=120)
    plt.close()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    inv, met = load()
    clean, exceptions = check_quality(inv, met)
    exceptions.to_csv(OUT / "exceptions.csv", index=False)
    clean.to_csv(OUT / "clean_reporting_table.csv", index=False)
    reports = build_reports(clean)
    for name, df in reports.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
    chart(reports["monthly_cost_by_utility"])

    print(f"Raw invoices: {len(inv)} | clean rows: {len(clean)} | issues found: {len(exceptions)}")
    print(exceptions["check"].value_counts().to_string())


if __name__ == "__main__":
    main()

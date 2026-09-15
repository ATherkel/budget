"""Audit frozen report arithmetic only; never imports bank data or derives coverage."""
import json
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIVATE = HERE.parents[1] / "imports" / ".dashboard-11"


def total(rows):
    return sum((D(t["amount"]) for t in rows), D(0))


def audit(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    for report in data["reports"]:
        m = report["measures"]
        income = total(report["incomeTransactions"])
        expenses = D(0)
        all_entries = list(report["incomeTransactions"])
        for category in report["categories"]:
            rows = category["transactions"]
            assert D(category["netSpending"]) == -total(rows)
            assert D(category["purchases"]) == -total([t for t in rows if t["kind"] == "expense"])
            assert D(category["refunds"]) == total([t for t in rows if t["kind"] == "refund"])
            assert D(category["netSpending"]) == D(category["purchases"]) - D(category["refunds"])
            expenses += D(category["netSpending"])
            all_entries += rows
        assert income == D(m["income"])
        assert expenses == D(m["expenses"])
        assert income - expenses == D(m["netCashFlow"]) == D(m["savings"])
        expected_rate = ((income - expenses) / income * 100).quantize(D(".01"), rounding=ROUND_HALF_UP) if income > 0 else None
        assert (D(m["savingsRate"]) if m["savingsRate"] is not None else None) == expected_rate
        for key in ("unclassified", "adjustments", "transfers"):
            g = report[key]
            assert g["count"] == len(g["transactions"])
            assert D(g["moneyIn"]) == total([t for t in g["transactions"] if D(t["amount"]) > 0])
            assert D(g["moneyOut"]) == total([t for t in g["transactions"] if D(t["amount"]) < 0])
            all_entries += g["transactions"]
        ids = [t["id"] for t in all_entries]
        assert len(ids) == len(set(ids)), "Entry appears in more than one reporting bucket"
        account_entries = [t for a in report["accounts"] for t in a["transactions"]]
        assert sorted(ids) == sorted(t["id"] for t in account_entries)
        for account in report["accounts"]:
            assert all(t["accountId"] == account["id"] for t in account["transactions"])
            assert all(report["period"]["start"] <= t["date"] <= report["period"]["end"] for t in account["transactions"])
            if account["quietConfirmed"]:
                assert account["coverage"]["status"] == "complete" and not account["transactions"]
            if account["coverage"]["status"] == "no_data":
                assert account["balance"]["amount"] is None
            if account["openingBalance"] is not None:
                assert D(account["openingBalance"]) + total(account["transactions"]) == D(account["balance"]["amount"])
        if data["kind"] == "synthetic":
            # Hand-checked constants, independent of the report-construction formula.
            expected = {
                "2026-07": ("36000.00", "15990.00", "20010.00"),
                "2026-08": ("36000.00", "24630.00", "11370.00"),
                "2026-09": ("36000.00", "15110.00", "20890.00"),
            }[report["period"]["id"]]
            assert tuple(m[k] for k in ("income", "expenses", "netCashFlow")) == expected
        else:
            baseline = json.loads((PRIVATE / "arithmetic-baseline.json").read_text())[report["period"]["id"]]
            assert D(baseline["income"]) == income
            assert -(D(baseline["expense"]) + D(baseline["refund"])) == expenses
            for kind in ("unknown", "adjustment", "transfer"):
                assert D(baseline[kind]) == total([t for t in all_entries if t["kind"] == kind])
    source_label = "opdigtet eksempel" if data["kind"] == "synthetic" else "privat lokalt eksempel"
    print(f"OK: {source_label}, {len(data['reports'])} måneder. Regnestykker, entydige rapportgrupper, kontodetaljer og særlige tilfælde kontrolleret.")


audit(HERE / "example.json")
if (PRIVATE / "reports.json").exists():
    audit(PRIVATE / "reports.json")

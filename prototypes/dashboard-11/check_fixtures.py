"""Audit frozen report arithmetic only; never imports bank data or derives coverage."""
import json
from itertools import combinations
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


def audit_scopes(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = sorted(a["id"] for a in data["availableAccounts"])
    expected_scopes = {scope for n in range(1, len(ids) + 1) for scope in combinations(ids, n)}
    assert {tuple(v["accountIds"]) for v in data["views"]} == expected_scopes
    for view in data["views"]:
        selected = set(view["accountIds"])
        assert {r["period"]["id"] for r in view["reports"]} == {r["period"]["id"] for r in data["reports"]}
        for r in view["reports"]:
            original = next(b for b in data["reports"] if b["period"]["id"] == r["period"]["id"])
            assert {a["id"] for a in r["accounts"]} == selected
            incomplete = [a for a in original["accounts"] if a["id"] in selected and a["coverage"]["status"] != "complete"]
            assert set(r["coverage"]["incompleteAccountIds"]) == {a["id"] for a in incomplete}
            no_data = all(a["coverage"]["status"] == "no_data" for a in r["accounts"])
            assert r["coverage"]["status"] == ("no_data" if no_data else "partial" if incomplete else "complete")
            rows = [t for a in original["accounts"] if a["id"] in selected for t in a["transactions"]]
            reported = r["incomeTransactions"] + [t for c in r["categories"] for t in c["transactions"]] + [t for g in ("unclassified", "adjustments", "transfers") for t in r[g]["transactions"]]
            assert sorted(t["id"] for t in rows) == sorted(t["id"] for t in reported)
            if no_data:
                assert all(r["measures"][k] is None for k in ("income", "expenses", "netCashFlow", "savings", "savingsRate"))
                assert all(r[g][k] is None for g in ("unclassified", "adjustments", "transfers") for k in ("moneyIn", "moneyOut"))
                assert not reported
                continue
            # Recompute from the original account entries, not the scoped category totals.
            income = total([t for t in rows if t["kind"] == "income"])
            expenses = -total([t for t in rows if t["kind"] in ("expense", "refund")])
            assert D(r["measures"]["income"]) == income
            assert D(r["measures"]["expenses"]) == expenses
            assert D(r["measures"]["netCashFlow"]) == D(r["measures"]["savings"]) == income - expenses
            rate = ((income-expenses)/income*100).quantize(D('.01'), rounding=ROUND_HALF_UP) if income>0 else None
            assert (D(r["measures"]["savingsRate"]) if r["measures"]["savingsRate"] is not None else None) == rate
            assert sum((D(c["netSpending"]) for c in r["categories"]), D(0)) == expenses
            for c in r["categories"]:
                assert D(c["netSpending"]) == -total(c["transactions"])
                assert D(c["purchases"]) - D(c["refunds"]) == D(c["netSpending"])
            for group, kind in (("unclassified", "unknown"), ("adjustments", "adjustment"), ("transfers", "transfer")):
                matching = [t for t in rows if t["kind"] == kind]
                assert r[group]["count"] == len(matching)
                assert D(r[group]["moneyIn"]) == total([t for t in matching if D(t["amount"])>0])
                assert D(r[group]["moneyOut"]) == total([t for t in matching if D(t["amount"])<0])
    if data["kind"] == "synthetic":
        common = next(v for v in data["views"] if v["accountIds"] == ["common"])
        august = next(r for r in common["reports"] if r["period"]["id"] == "2026-08")
        assert august["measures"]["expenses"] == "0.00" and august["accounts"][0]["quietConfirmed"]
        september = next(r for r in common["reports"] if r["period"]["id"] == "2026-09")
        assert september["measures"]["expenses"] is None
        mine = next(v for v in data["views"] if v["accountIds"] == ["mine"])
        july = next(r for r in mine["reports"] if r["period"]["id"] == "2026-07")
        assert july["measures"]["expenses"] == "15990.00" and july["transfers"]["moneyOut"] == "-5000.00"
    print(f"OK: {len(data['views'])} kontovalg × {len(data['reports'])} måneder, herunder datadækning og udeladte interne overførsler.")


for path in (HERE / "example.json", PRIVATE / "reports.json"):
    if path.exists():
        audit(path)
        audit_scopes(path)

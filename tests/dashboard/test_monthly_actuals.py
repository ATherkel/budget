# Copyright 2026 Therkel
"""Enkel's monthly actuals: the report's figures, Categories and trust notes.

Expected values are the worked examples in `report-contract.md`, over the
synthetic worked-example publication; the dashboard is driven in-process.
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult, GoldTransaction
from budget.gold.store import GoldStore
from budget.profiles import Profile
from tests.analytics.test_monthly_overview import LATER_GOLD, PERSON
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import Page, read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

# The worked examples' reference date: May is the current month.
REFERENCE_DATE = "2026-05-14"


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    return profile


@pytest.fixture
def client(profile: Profile) -> TestClient:
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


def report(
    client: TestClient,
    month: str,
    accounts: tuple[str, ...] = (CURRENT, SAVINGS),
    reference_date: str = REFERENCE_DATE,
) -> Page:
    """Return the report fragment the page's form asks for."""
    response = client.get(
        "/report",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": reference_date,
            "account": list(accounts),
            "month": month,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return read(response.text)


def test_the_report_shows_income_expenses_and_money_left_in_danish_kroner(
    client: TestClient,
) -> None:
    # February: income 25,000.00, expenses 9,020.00, net cash flow 15,980.00.
    february = report(client, "2026-02")

    assert (
        february.text_of("income"),
        february.text_of("expenses"),
        february.text_of("money-left"),
    ) == ("25.000,00 kr.", "9.020,00 kr.", "15.980,00 kr.")


def test_every_category_is_listed_in_the_order_the_report_gives(
    client: TestClient,
) -> None:
    # February: rent 8,500.00, then groceries 520.00 (640.00 less a 120.00 Refund).
    february = report(client, "2026-02")

    assert february.text_of("categories") == "Rent 8.500,00 kr. Groceries 520,00 kr."


def test_money_left_below_zero_carries_a_minus_sign(client: TestClient) -> None:
    # March: income 0.00 and expenses 1,000.00 leave -1,000.00, written with
    # the minus sign the report contract writes, not a hyphen.
    march = report(client, "2026-03")

    assert march.text_of("money-left") == "\N{MINUS SIGN}1.000,00 kr."


def test_a_partial_report_names_its_incomplete_accounts_and_links_the_explanation(
    client: TestClient,
) -> None:
    # February is partial: Joint current's month has a balance break. The link
    # keeps the page's pinned context and selection.
    february = report(client, "2026-02")

    assert (
        "Joint current" in (february.text_of("coverage-note") or ""),
        "Joint savings" in (february.text_of("coverage-note") or ""),
        february.attributes("coverage-explanation").get("href"),
    ) == (
        True,
        False,
        (
            "/explanation?publication=1&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-02"
        ),
    )


def test_only_a_month_that_may_still_change_is_labelled_provisional(
    client: TestClient,
) -> None:
    # May is the reference date's month; February is closed and settled.
    may, february = report(client, "2026-05"), report(client, "2026-02")

    assert (
        may.text_of("provisional-label"),
        february.text_of("provisional-label"),
    ) == ("Foreløbige tal", None)


def test_unclassified_money_keeps_its_quiet_note_and_explanation_link(
    client: TestClient,
) -> None:
    # March has one Unclassified transaction of -450.00; February has none.
    # Its amounts now show in the Ukategoriseret bucket (#380); the note stays.
    march, february = report(client, "2026-03"), report(client, "2026-02")

    assert (
        march.text_of("unclassified-note") is not None,
        march.attributes("unclassified-explanation").get("href"),
        february.text_of("unclassified-note"),
    ) == (
        True,
        (
            "/explanation?publication=1&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-03"
        ),
        None,
    )


# Synthetic Unclassified money in April on Joint current: +1,000.00 in and
# -600.00 and -400.00 out, which would net to zero.
OFFSETTING = tuple(
    GoldTransaction(
        transaction_id=f"current-offset-{index}",
        account_id=CURRENT,
        transaction_date=date(2026, 4, 10),
        account_sequence=100 + index,
        amount=Decimal(amount),
        description="UNKNOWN",
        transaction_type="unknown",
        transfer_group_id=None,
        balance_after=None,
        balance_check="missing_balance",
    )
    for index, amount in enumerate(("1000.00", "-600.00", "-400.00"))
)


@pytest.fixture
def offsetting_client(tmp_path: Path) -> TestClient:
    profile = dashboard_profile(tmp_path)
    records = replace(RECORDS, transactions=(*RECORDS.transactions, *OFFSETTING))
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, records), RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    return client


def test_offsetting_unclassified_money_shows_signed_in_and_out_never_netted(
    offsetting_client: TestClient,
) -> None:
    # April: income 25,000.00 and rent 8,500.00 are classified; the three
    # Unclassified amounts sum to +1,000.00 in and -1,000.00 out.
    april = report(offsetting_client, "2026-04", accounts=(CURRENT,))

    assert (
        april.text_of("unclassified"),
        april.text_of("unclassified-in"),
        april.text_of("unclassified-out"),
        april.text_of("income"),
        april.text_of("expenses"),
        april.text_of("money-left"),
    ) == (
        "Ukategoriseret Ind +1.000,00 kr. Ud \N{MINUS SIGN}1.000,00 kr.",
        "+1.000,00 kr.",
        "\N{MINUS SIGN}1.000,00 kr.",
        "25.000,00 kr.",
        "8.500,00 kr.",
        "16.500,00 kr.",
    )


def test_a_known_zero_of_unclassified_money_shows_zero_without_a_sign(
    client: TestClient,
) -> None:
    # February: no Unclassified transactions, so 0.00 in and 0.00 out are known.
    february = report(client, "2026-02")

    assert (
        february.text_of("unclassified-in"),
        february.text_of("unclassified-out"),
    ) == ("0,00 kr.", "0,00 kr.")


def test_unclassified_money_without_evidence_shows_as_unknown_never_as_zero(
    client: TestClient,
) -> None:
    # June on 3 June: no account has evidence yet, so both sides are unknown.
    june = report(client, "2026-06", reference_date="2026-06-03")

    assert (
        june.text_of("unclassified"),
        june.text_of("unclassified-in"),
        june.text_of("unclassified-out"),
    ) == (
        "Ukategoriseret Ind Ingen data endnu Ud Ingen data endnu",
        "Ingen data endnu",
        "Ingen data endnu",
    )


def test_unclassified_money_follows_the_selected_accounts_on_load_and_update(
    client: TestClient,
) -> None:
    # March's -450.00 Unclassified payment is on Joint current, so selecting
    # Joint savings alone leaves a known zero on both sides.
    def opened(accounts: tuple[str, ...]) -> Page:
        response = client.get(
            "/",
            params={
                "publication": str(PUBLICATION.publication_id),
                "reference_date": REFERENCE_DATE,
                "account": list(accounts),
                "month": "2026-03",
            },
        )
        assert response.status_code == 200
        return read(response.text)

    pages = (
        opened((CURRENT, SAVINGS)),
        opened((SAVINGS,)),
        report(client, "2026-03"),
        report(client, "2026-03", accounts=(SAVINGS,)),
    )

    assert [
        (page.text_of("unclassified-in"), page.text_of("unclassified-out"))
        for page in pages
    ] == [
        ("0,00 kr.", "\N{MINUS SIGN}450,00 kr."),
        ("0,00 kr.", "0,00 kr."),
        ("0,00 kr.", "\N{MINUS SIGN}450,00 kr."),
        ("0,00 kr.", "0,00 kr."),
    ]


def explanation(
    client: TestClient, month: str, accounts: tuple[str, ...] = (CURRENT, SAVINGS)
) -> Page:
    """Return the explanation page a report's link opens."""
    response = client.get(
        "/explanation",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": REFERENCE_DATE,
            "account": list(accounts),
            "month": month,
        },
    )
    assert response.status_code == 200
    return read(response.text)


def test_the_explanation_names_the_incomplete_and_unsettled_months_of_the_pinned_report(
    client: TestClient,
) -> None:
    # May is the current month, both accounts' May rows are partial and their
    # late bookings unsettled. The page keeps the pin and shows no amounts.
    may = explanation(client, "2026-05")
    coverage = may.text_of("explanation-coverage") or ""
    provisional = may.text_of("explanation-provisional") or ""

    assert (
        "Joint current" in coverage and "Joint savings" in coverage,
        "maj 2026" in coverage,
        "indeværende måned" in provisional,
        "Joint current" in provisional and "Joint savings" in provisional,
        "kr." in may.visible(),
        may.attributes("back-to-report").get("href"),
    ) == (
        True,
        True,
        True,
        True,
        False,
        (
            "/?publication=1&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-05"
        ),
    )


def test_the_explanation_says_whether_the_report_has_unclassified_money(
    client: TestClient,
) -> None:
    # March has Unclassified money and February has none; neither shows its
    # amounts or count, which belong to Kontrol.
    march, february = explanation(client, "2026-03"), explanation(client, "2026-02")

    assert (
        march.text_of("explanation-unclassified") is not None,
        "450" in march.visible(),
        february.text_of("explanation-unclassified"),
    ) == (True, False, None)


def test_a_month_without_data_shows_its_figures_as_unknown_never_as_zero(
    client: TestClient,
) -> None:
    # June on 3 June: selectable, but no account has evidence for it yet.
    june = report(client, "2026-06", reference_date="2026-06-03")

    assert (
        june.text_of("income"),
        june.text_of("expenses"),
        june.text_of("money-left"),
        "0,00" in june.visible(),
    ) == ("Ingen data endnu", "Ingen data endnu", "Ingen data endnu", False)


def test_a_confirmed_quiet_month_shows_zero_without_a_trust_note(
    client: TestClient,
) -> None:
    # March, Joint savings only: coverage complete and nothing happened, so
    # zero is a known zero and no note is owed.
    quiet = report(client, "2026-03", accounts=(SAVINGS,))

    assert (
        quiet.text_of("income"),
        quiet.text_of("expenses"),
        quiet.text_of("money-left"),
        quiet.text_of("coverage-note"),
        quiet.text_of("unclassified-note"),
    ) == ("0,00 kr.", "0,00 kr.", "0,00 kr.", None, None)


def test_a_report_without_data_names_its_accounts_and_links_the_explanation(
    client: TestClient,
) -> None:
    # June on 3 June: neither account has evidence yet.
    june = report(client, "2026-06", reference_date="2026-06-03")
    note = june.text_of("coverage-note") or ""

    assert (
        "Joint current" in note and "Joint savings" in note,
        june.attributes("coverage-explanation").get("href"),
    ) == (
        True,
        (
            "/explanation?publication=1&reference_date=2026-06-03"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-06"
        ),
    )


def test_the_provisional_label_links_the_explanation_of_why(
    client: TestClient,
) -> None:
    # A month can be provisional with complete coverage, so the label needs
    # its own way to the reasons.
    may = report(client, "2026-05")

    assert may.attributes("provisional-explanation").get("href") == (
        "/explanation?publication=1&reference_date=2026-05-14"
        f"&account={CURRENT}&account={SAVINGS}&month=2026-05"
    )


def test_the_explanation_of_a_fully_covered_report_lists_no_incomplete_months(
    client: TestClient,
) -> None:
    # March, Joint savings only: coverage is complete.
    quiet = explanation(client, "2026-03", accounts=(SAVINGS,))

    assert quiet.text_of("explanation-coverage") is None


def test_an_explanation_of_an_invalid_selection_says_why_and_offers_the_overview(
    client: TestClient,
) -> None:
    # July lies after the pinned date's month, so no report answers it.
    july = explanation(client, "2026-07")

    assert (
        "Den valgte måned ligger uden for de måneder, der kan vælges."
        in july.visible(),
        july.attributes("back-to-overview").get("href"),
    ) == (True, "/")


def test_the_explanation_of_a_superseded_publication_offers_the_newer_figures(
    profile: Profile, client: TestClient
) -> None:
    # A newer build becomes current after the page pinned publication 1.
    with GoldStore(profile) as store:
        newer = replace(PUBLICATION, publication_id=2)
        store.publish(GoldResult(newer, RECORDS), RECIPE, CONFIGURATION)

    february = explanation(client, "2026-02")

    assert (
        "Der findes nyere tal." in february.visible(),
        february.attributes("newer-figures").get("href"),
    ) == (True, "/")


def test_an_account_outside_its_history_is_not_named_as_incomplete(
    tmp_path: Path,
) -> None:
    # The contract's later account, Person current, starts in April. In
    # February only Joint current is incomplete; Person current has nothing
    # that could be missing.
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(LATER_GOLD, RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC))
    )
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    february = report(client, "2026-02", accounts=(CURRENT, PERSON))
    note = february.text_of("coverage-note") or ""

    assert ("Joint current" in note, "Person current" in note) == (True, False)


def test_the_explanation_sends_a_reader_who_is_not_logged_in_to_log_in(
    profile: Profile,
) -> None:
    # It names accounts and their trust, so it is as private as the report.
    stranger = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )

    response = stranger.get(
        "/explanation",
        params={
            "publication": "1",
            "reference_date": REFERENCE_DATE,
            "account": [CURRENT],
            "month": "2026-02",
        },
    )

    assert (response.status_code, response.headers.get("location")) == (
        303,
        "/login",
    )


def test_the_trust_notes_read_as_quiet_danish_sentences_without_counts(
    client: TestClient,
) -> None:
    # The whole text, so neither an amount nor a count can slip in.
    march = report(client, "2026-03")
    june = report(client, "2026-06", reference_date="2026-06-03")

    assert (march.text_of("unclassified-note"), june.text_of("coverage-note")) == (
        (
            "Nogle betalinger er endnu ikke placeret i en kategori, så penge "
            "tilbage kan ændre sig. Om betalinger uden kategori"
        ),
        (
            "Der er ingen data endnu fra Joint current og Joint savings. "
            "Hvorfor tallene er ufuldstændige"
        ),
    )


def test_a_month_outside_every_selected_accounts_history_says_so_on_both_pages(
    tmp_path: Path,
) -> None:
    # Person current starts in April, so February lies outside its history:
    # nothing is missing, there is simply nothing to show.
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(LATER_GOLD, RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC))
    )
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    february = report(client, "2026-02", accounts=(PERSON,))
    link = february.attributes("coverage-explanation").get("href") or ""
    explained = read(client.get(link).text)

    assert (
        february.text_of("coverage-note"),
        february.text_of("money-left"),
        explained.text_of("explanation-coverage"),
    ) == (
        (
            "Ingen af de valgte konti har historik i februar 2026. "
            "Hvorfor der ingen tal er"
        ),
        "Ingen data endnu",
        (
            "Ingen af de valgte konti har historik i februar 2026, så der er "
            "ingen tal for måneden. Vælg en anden måned eller andre konti."
        ),
    )

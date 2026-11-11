# Dashboard #11 prototype archive

This directory is a historical, synthetic design reference for the household
dashboard exploration in [issue #11](https://github.com/ATherkel/budget/issues/11).
It is not a production dashboard, an authentication implementation, or a
release status page.

[Issue #100](https://github.com/ATherkel/budget/issues/100) owns the production
dashboard specification and links its child issues. The current normative
report semantics are in [report-contract.md](../../docs/architecture/report-contract.md).
GitHub Issues are the only tracker. The local ticket mirror, session logs,
checkpoint files, comment drafts, and implementation reports previously bundled
here duplicated that material and have been removed.

## Current scope

Release 0.3 is the authenticated monthly actuals workflow. It does not include
the prototype's budget comparison, trends, historical navigation, fixed/other
expense split, or earmarked reserves. Those are later product scopes assigned
by #100 and its child issues:

- [0.3 monthly actuals contract](https://github.com/ATherkel/budget/issues/101)
- [later budget inputs](https://github.com/ATherkel/budget/issues/102)
- [authenticated dashboard shell](https://github.com/ATherkel/budget/issues/103)
- [monthly actuals overview](https://github.com/ATherkel/budget/issues/104)
- [later category investigation](https://github.com/ATherkel/budget/issues/105)
- [later account and Kontrol details](https://github.com/ATherkel/budget/issues/106)
- [later budgets and time markers](https://github.com/ATherkel/budget/issues/107)
- [later trends](https://github.com/ATherkel/budget/issues/108)
- [later historical navigation](https://github.com/ATherkel/budget/issues/109)
- [later fixed expenses and planned disposable income](https://github.com/ATherkel/budget/issues/110)
- [0.3 acceptance](https://github.com/ATherkel/budget/issues/111)
- [later reserve and carry-forward design](https://github.com/ATherkel/budget/issues/112)

This archive records design exploration from September 2026. It does not
override current architecture, accepted ADRs, the current issue scope, or the
production implementation.

## Run the prototype

From the repository root:

```powershell
py -3.12 prototypes/dashboard-11/serve.py
```

Open <http://127.0.0.1:8011>. The server binds to loopback only. Use
`--port` to choose another port.

The fixture is synthetic and local:

```powershell
py -3.12 prototypes/dashboard-11/build_example.py
py -3.12 prototypes/dashboard-11/check_fixtures.py
node --check prototypes/dashboard-11/app.js
```

The demonstration login accepts any input. It has no password check, cookie,
storage, server session, security guarantee, or path to production account
access.

## Retained design evidence

The screen demonstrates Enkel and Avanceret modes, category drill-down,
synthetic current and historical Publications, missing-versus-zero states,
coverage and provisional states, transfers, adjustments, and an experimental
budget and trend layout.

[REPORT-SHAPE.md](REPORT-SHAPE.md) preserves the API-neutral report proposal
used during the exploration, including allocation-based category rows, refund
direction, adjustment handling, transfer evidence, nullable balances, and
coverage rules. Its current replacement is
[report-contract.md](../../docs/architecture/report-contract.md).

The historical decisions remain in the tracker:

- [prototype-to-planning timeline](https://github.com/ATherkel/budget/issues/11#issuecomment-5873041376)
- [September release-scope decision](https://github.com/ATherkel/budget/issues/2#issuecomment-5873042285)
- [fixed-expense finding and later scope](https://github.com/ATherkel/budget/issues/99#issuecomment-5873043116)

Later issue changes supersede those dated comments where release placement or
contract detail changed.

The latest prototype iteration has not completed a household usability trial.
Fixture checks and earlier browser checks are not household acceptance evidence;
production acceptance is tracked on #111.

## Boundaries

- `example.json` is generated from invented data. No bank export, private
  report, account number, or production store is included.
- The JavaScript renders supplied fixture values. It is not the production
  analytics, classification, publication, or authentication implementation.
- The demo server is standard-library-only and does not import the application
  package, read `imports/`, or write user data.
- The prototype's experimental budget and reserve arithmetic is design evidence,
  not accepted financial policy.
- The working application, its release notes, and current acceptance criteria
  live outside this archive.

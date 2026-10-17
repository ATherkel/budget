# #11 second round — implementation report

STATUS: **ready_for_review** (one consolidated correction cycle applied)
Task: `/root/dashboard_round_2` (worker report for Astra's review)
Workspace: `C:/Users/Therkel/.codex/worktrees/641b/budget`,
branch `codex/prototype-11-round-2`, HEAD `59f732f2db3a5a03b1b6dcd3bd43427842457c65`.
Contract: [ROUND-2-PLAN.md](ROUND-2-PLAN.md). Nothing was committed, staged,
pushed or written outside `prototypes/dashboard-11/`; no configuration, no
suppression and no project dependency changed.

## Changed paths

All under `prototypes/dashboard-11/`:

| Path | Change |
| --- | --- |
| `build_example.py` | **New.** Throwaway synthetic fixture builder: 2 accounts, 6 categories, 58 transactions, 3 publications. Exports carry `covers_from`/`covers_through`/`produced_on`/`imported_on`; reports carry `currency` (DKK) and the account taxonomy; reads only its own constants. |
| `example.json` | **Regenerated** (3 publications × 3 account selections × 5–6 months). 759 454 bytes, byte-identical on re-run. |
| `check_fixtures.py` | **Rewritten.** 2 236 checks against independently written constants, including an admitted-export table whose provisional verdict is recomputed and compared with the fixture, targeted export-rule cases, `evidenceThrough`, `currency` and account taxonomy. |
| `serve.py` | **Rewritten.** Serves only `index.html`, `style.css`, `app.js` and `example.json` from its own folder on `127.0.0.1`, with `--port` and a 204 answer for `/favicon.ico`. The automatic private-imports fallback is gone; private files on disk were left untouched. |
| `index.html` | Login screen, mode switch, publication picker, advanced tabs, logout. |
| `app.js` | Demo login/logout, `Enkel`/`Avanceret`, `Overblik`/`Detaljer`/`Kontrol`, publication views with banner and return-to-current, calendar-based trend ranges, budget experiment in `Avanceret`, `Se forklaring` control, no-data copy. |
| `style.css` | Login card, mode switch, tabs, publication banner, coverage line, reconciliation, route block, inline explanation control, and `[hidden]`/mobile rules. |
| `REPORT-SHAPE.md` | English, API-neutral proposal reconciled with Gold 0.2, `analytics-layer.md`, `publications.md`, `classification.md`, `operations.md`: currency, the `savingsRate` unit, the allocation-shaped category drill-down, the one-sided-transfer counterpart as fixture-only, the explicit transfer exclusion, and the gaps this round found. |
| `README.md` | English round-2 section above the previous Danish round, kept as history. |
| `HANDOFF.md` | New English status section at the top; earlier sections unchanged. |
| `SESSION.md` | English round-2 section plus a correction-cycle section; the Danish history is unchanged and no new participant observation is claimed. |
| `ROUND-2-IMPLEMENTATION.md` | This report. |

Untouched: `ROUND-2-PLAN.md` and `CHECKPOINT.md` (root-owned), `.codex/`, and
every file outside the prototype folder. No file added or removed in this
correction cycle (a temporary `__init__.py` was tried and removed again; see
Quality).

## Behaviour delivered

**Modes are presentation only.** `Enkel` (default) shows the month, three plain
figures (text, not buttons), one compact coverage line that names incomplete
accounts, the provisional label, one short non-numeric notice about
provisional/incomplete/uncategorised amounts with a **Se forklaring** control
into `Avanceret → Kontrol`, and the category list — categories are the only
drill-downs. No counts, amounts, transfer explanations, adjustments, charts or
account blocks appear in `Enkel`.

`Avanceret` adds `Overblik` (figures, trend chart, categories, budget
experiment — no diagnostic blocks), `Detaljer` (account activity with statement
and evidence dates, transfer list, adjustment list) and `Kontrol` (coverage per
account, provisional reasons and the rule, reconciliation, money without a
category with the `budget review` / `budget decide` route, transfers and
adjustments held outside the totals). Switching to `Enkel` closes an open
dialog, resets the tab and the budget experiment, and keeps publication, month,
account selection and figures.

**Publications.** One fixture carries the current publication, an `as-was` view
at 31 August 2026 and an `as-known-at` view at 31 August 2026. A non-current
view shows a named banner plus **Tilbage til nutiden** in both modes, the footer
names the view, and provisional labels follow the view's own knowledge time.
The views differ in data and interpretation: June expenses are
13.110,00 / 11.680,00 / 12.570,00 kr., and the `as-was` view still shows `Tøj`
where the current one shows `Tøj og sko`.

**Provisional rule.** A closed month keeps the label until every imported
account has an admitted export whose declared range contains the month's last
day *and* which the bank produced at least seven days after that day; an
account with `evidence_through` null is exempt. The verdict is recomputed in
the auditor from an independent export table. The result in this fixture:
current publication April, August and September provisional; past views April
and August; July, June and May closed and final. A closed provisional month
reads **Foreløbige tal**, the running month **Måneden indtil nu — foreløbige
tal**. April is provisional precisely because Fælleskonto's statements begin in
May: an export made late enough exists, but its range does not reach back.

**Trend ranges.** `Indeværende år` spans January to the newest month and
`Seneste 12 måneder` a real trailing twelve, both built from the calendar;
months without a report show `Ukendt`/`Ingen rapportoplysninger` as gaps, not
zeros. The custom range keeps its invalid-range guard. (This fixes a range that
previously always errored because it assumed the publication began in
January.)

**Budget experiment.** `Åbn opdigtet budget · begge konti` now selects both
example accounts, switches to the current publication and picks a month the
synthetic budget covers (July, August or September) before showing the budget
comparison — from any selection, including a past view.

**No evidence is not zero.** With no evidence, a month reports `Ukendt` for
every figure, `Antal ukendt` for the counts, `Ingen oplysninger` badges, and
declares neither "no adjustments" nor "no transfers"; the transfer panel names
no counts at all. A confirmed quiet month still reports a real `0,00 kr.` with
complete coverage. A category that ends negative (a net refund) still renders
as such.

**Demo login.** Any input proceeds; the screen states there is no password, no
backend, no storage and no security claim, and shows the fictional phrase.
`Log ud` returns to it.

## Verification

### Fixture and JavaScript

| Command | Exit | Salient result |
| --- | --- | --- |
| `py -3.12 prototypes/dashboard-11/build_example.py` | 0 | `Wrote example.json: 3 publications, 58 synthetic transactions.` |
| `py -3.12 prototypes/dashboard-11/check_fixtures.py` | 0 | `OK: 3 offentliggørelser og 2236 kontroller uden fejl.` |
| Rebuild determinism | 0 | `example.json` SHA-256 `060F4337441332D8812E4FD26134E4803E402881C3F53CC14BEC09BFB8A7F2C9` before and after a rebuild (`deterministic=True`). |
| Negative audit test, figure | 1 (expected) | Changing one fixture figure (June expenses 13110.00 → 13111.00) produced `FAIL: 2 af 2036 kontroller fejlede` naming the arithmetic and the hand-checked constant; a rebuild restored the original bytes. |
| Negative audit test, export rule | 0 with 3 targeted expectations | `audit_export_rule` rejects an export that begins after the period's last day, rejects one produced less than seven days after it, and accepts one that covers it and is seven days later. The same rule is what keeps April provisional. |
| `node --check prototypes/dashboard-11/app.js` | 0 | Syntax clean. |

### Python quality gate, locked versions

Run exactly as the repository documents, against the versions pinned in
`uv.lock`, with the environment placed outside the repository so no untracked
environment is left behind:

```powershell
$env:UV_PROJECT_ENVIRONMENT="$env:TEMP\budget-locked-venv"
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen ty check
uv run --frozen complexipy
```

| Command | Exit | Salient result |
| --- | --- | --- |
| `uv run --frozen ruff --version` / `ty --version` / `complexipy --version` | 0 | `ruff 0.16.8`, `ty 0.0.83 (9c214798c 2026-09-21)`, `complexipy 8.0.1` — the locked versions, not `uv tool` latest. |
| `uv run --frozen ruff check .` | 1 | 6 findings, all file-level: `INP001` ×3 and `CPY001` ×3. No lint finding in the code itself. |
| `uv run --frozen ruff format --check .` | 0 | `68 files already formatted` (the count is every file ruff walked, not only the three scripts). |
| `uv run --frozen ty check` | 0 | `All checks passed!` |
| `uv run --frozen complexipy` | 0 | `All functions are within the allowed complexity`; highest score 14 (`audit_budget`). |

`INP001`: the directory is named `dashboard-11`, which is not a valid Python
identifier. Adding the `__init__.py` the rule asks for is possible but then
raises `N999 Invalid module name: 'dashboard-11'` under the same locked ruff
(verified), so the package marker was removed again and the finding is reported
instead of trading one error for a worse one. The fixes are a directory rename
(outside this task's scope and referenced by the plan and the documents) or a
per-file ignore in `pyproject.toml` (a configuration change this task forbids).

`CPY001`: still reported by the locked ruff 0.16.8, so it is **not** a
newer-tool artefact. The repository holds no licence or copyright convention
(it has no other Python), and inventing a copyright holder is not the worker's
call; the rule is left unsuppressed and reported.

### Browser

The in-app browser was not available in this turn, so the checks ran through a
headless Chrome driven over the DevTools protocol (the sandbox needed an
escalated launch for Chrome's IPC; the driver and screenshots live in temp):

```powershell
node "$env:TEMP\budget-browser-qa.mjs" "$env:TEMP\budget-qa-final"
```

Result (exit 0), measured in the page:

| Check | Measurement |
| --- | --- |
| `Enkel` summary figures | `metricTags` `DIV, DIV, DIV`, `metricButtons` 0 — plain text, not buttons |
| `Enkel` notice | `Nogle tal er ufuldstændige. Tallene er foreløbige. Beløb uden kategori er ikke med i indtægter og udgifter. Se forklaring →`; `noticeHasDigits` false |
| `Enkel` coverage and label | `Ufuldstændige tal — Min konto er delvis med; Fælleskonto mangler`; badge `Måneden indtil nu — foreløbige tal` |
| `Enkel` diagnostics | `hasUnknownPanel` false, `hasTrend` false, `contentFootnotes` 0, 6 category buttons |
| `Se forklaring` | lands on mode `Avanceret`, tab `kontrol`, with the route block present |
| Advanced `Overblik` | no unknown panel, no summary note, trend + categories present, no account blocks, no transfers text |
| Trend `Indeværende år` | `januar 2026 – september 2026`, chart drawn, 9 table rows, 3 gap rows, 9 `Ukendt` cells |
| Trend `Seneste 12 måneder` | `oktober 2025 – september 2026`, 12 table rows, 6 gap rows, 18 `Ukendt` cells |
| Trend custom | `maj 2026 – juli 2026`, 3 rows; reversed range shows the guard, no chart |
| Budget from one account and April | both accounts checked, publication `pub-2026-09-15`, month `2026-09`, 8 budget rows, switch pressed, no empty state |
| Budget from a past view | both accounts checked, publication back on the current one, month `2026-09`, 8 budget rows, banner hidden |
| Provisional copy | April `Foreløbige tal`, July `Måneden er afsluttet`, September `Måneden indtil nu — foreløbige tal` |
| No-evidence month in `Kontrol` | badges `Ingen oplysninger`, `Antal ukendt`; sentence `Antal posteringer er ukendt for denne måned.`; all money `Ukendt`; no `0 posteringer`; no "no adjustments" claim; no `undefined` |
| No-evidence month in `Detaljer` | no counts, no list buttons, no `undefined` |
| Confirmed quiet month | coverage `Alle kontodata er med — Fælleskonto`, figures `0,00 kr.` ×3, badge `Foreløbige tal` (quiet but its export is dated 5 September) |
| Overflow sweep | 390×844: simple/overview/checks/details all `scrollWidth 375` ≤ 390; 320×740: `305` ≤ 320 — no horizontal overflow |
| Console | `consoleProblems` empty (the favicon 404 is answered 204) |

Screenshots (7 PNGs, desktop and phone, both modes and all three tabs) and the
raw JSON result, copied out of the temp folder into the task's artifact area so
they survive temp cleanup:
`C:\Users\Therkel\.codex\visualizations\2026\09\26\01a0def8-422e-7af1-8f78-c69f8f958467\dashboard-11-round2-fix\`
— `01-simple-1280.png`, `02-overview-1280.png`, `03-checks-nodata-1280.png`,
`04-quiet-1280.png`, `05-simple-390.png`, `06-overview-390.png`,
`07-checks-390.png`, `budget-qa-final.json`.

## Outstanding risks and gaps

1. **No usability evidence.** Neither participant has run the three tasks on
   this version, in either mode. Everything above is the agent's own check.
2. **The fixture is large** (759 454 bytes of JSON) because it materialises every
   account selection for three publications. Review the builder, not the JSON.
3. **Past-view balances are derived from that view's own known transactions**,
   so `Min konto`'s July/August balances differ by 540,00 kr. between the
   current publication and the past views. A real `as-was` view would carry the
   bank-stated balance of the export it actually had. Recorded as a fixture
   simplification.
4. **`no_data` still overloads two facts** — "the household has no evidence"
   and "this month is outside the account's managed period". April is the
   visible case: Fælleskonto is outside its managed period there and has no
   export reaching it, so the month reads provisional. The proposal records the
   gap; a production DTO needs a reason code.
5. **A one-sided transfer's counterpart is fixture data.** The accepted public
   contract has no such projection, so the production screen should use generic
   copy. The proposal now says so.
6. **The demo login is not security** and must not be read as a step toward
   `operations.md`'s passphrase.
7. **Residual quality findings** `INP001` and `CPY001` need an owner-level
   decision (directory rename, a documented ignore, or a copyright convention).
   `N999` shows why the obvious `__init__.py` fix is worse here.
8. **Routing is unverified.** The host exposed no model metadata to this
   worker, so the work is labelled with its route, not a verified model.

## Decisions for Astra

- Whether `REPORT-SHAPE.md` is ready to offer the maintainer as the analytics
  interface proposal, and which of its four recorded gaps belong to #11 or #12.
- How to treat `INP001`/`CPY001`: rename the prototype directory, add a
  documented per-file ignore, or record a repository copyright convention.
- Whether the README stays bilingual (round 2 English, earlier round Danish
  history) or is translated as a whole.

## Running it

Live now on this machine:

```powershell
py -3.12 prototypes/dashboard-11/serve.py --port 8011
```

<http://127.0.0.1:8011> — running as PID 40544; stop with Ctrl+C or
`Stop-Process -Id 40544`. The login screen accepts anything; the fictional
phrase is `fisk-i-haven`.

Next checkpoint if this is reopened: the maintainer's read of the two modes,
the `Kontrol` wording and `REPORT-SHAPE.md`, then at most one further
consolidated correction pass.

---
type: pr310-review-fixes
---
# PR #310 review fixes implementation

Baseline: `7fa6165e160c8ebee3a5005ceaa542963a64a7ac`

Branch: `codex/pr310-review-fixes`

The approved plan is `PLAN.md`. This work retained FastAPI, Jinja, HTMX and the
analytics boundary. Financial report figures remain in #104. No commit, stage,
push, merge, deployment or workflow change was made.

## Behavior delivered

1. **Credential rotation.** `CredentialSnapshot` is one immutable read of the
   stored salt and passphrase hash. Login verification, cookie verification
   and renewed-cookie issuance use that same snapshot. A request authorized
   against the old credential can finish, but receives only an old-key cookie;
   its next request is refused after rotation.
2. **Initial publication history.** Fresh pages carry a fully pinned canonical
   URL. Local `app.js` replaces the initial `/` history entry before HTMX
   interaction. `/` remains the explicit fresh-data action.
3. **Empty selections.** Empty-account responses now send the same pinned
   `HX-Push-Url`, with no account parameters. Reload and Back/Forward retain the
   prompt rather than silently restoring a previous account.
4. **Active and stale failures.** Each report request has a browser generation.
   Loading clears the old report. Network and HTTP failures for the active
   generation replace it with an accessible `role="alert"` state and a retry
   button. A superseded failure is ignored.
5. **Lockout duration.** The throttle stores the next bounded duration directly.
   It doubles from 30 seconds only until 900 seconds, with no exponent that can
   overflow, and successful login resets it.
6. **Synthetic dashboard demo.** `budget demo` creates a fresh development
   profile in a new isolated folder, publishes synthetic Gold, sets the known
   demo login, binds only to `127.0.0.1`, and runs the real serve path. Existing
   targets are refused without modification. README documents creation,
   login, expected screen, shutdown and cleanup.
7. **Responsive shell.** A shared Jinja base, local CSS and a local script
   provide deliberate typography, spacing, consistent controls, responsive
   desktop/phone layouts, visible focus, reduced-motion handling, and explicit
   loading, empty, unavailable, validation and request-failure states. No CSS
   framework or CDN is used.
   The shared footer says `Beskyttet adgang`; it does not claim that a profile
   bound to the home network runs only on one machine.

## Closing review outcome

Independent Astra review found one Required issue: the shared footer claimed
`Kun på denne maskine` even though `serve` supports a network bind. The footer
now uses the factual `Beskyttet adgang` label. Both the rendered-page test and
real-browser shell test reject the old wording, and the desktop and phone
screenshots were refreshed.

The root corrected `PLAN.md` to the repository-required frontmatter type and
reported that the targeted auth plus frontmatter run passed 81 tests. The root
also assessed the UTC/Copenhagen demo seed difference; analytics extends the
month range to the reference month, so it is not a demonstrated shell
regression and required no date behavior expansion. No further Required review
findings remain.

## Deferred red-green log

The brief prohibited commit history, so command output is retained under
`evidence/` instead of red/green commits.

| Slice | Red evidence | Green evidence | Note |
| --- | --- | --- | --- |
| Renewal cannot upgrade an old authorization | `01-renewal-red.txt` (`200 != 303`) | `02-rotation-green.txt` | Real passphrase-file replacement occurs immediately after the first credential read. |
| Login cannot upgrade an old authorization | Shared credential snapshot made this green during slice 1 | `02-rotation-green.txt` | Kept as a regression; no artificial second red. |
| Lock duration is capped without overflow | `03-throttle-red.txt` (`OverflowError` at cycle 43) | `04-throttle-green.txt` | Public `LoginThrottle`; 50 cycles reach and stay at 900 seconds. |
| Initial page exposes a fully pinned URL | `05-initial-pin-red.txt` | `06-initial-pin-green.txt` | Server contract. |
| Empty selection updates its pinned URL | `07-empty-push-red.txt` | `08-canonical-urls-green.txt` | Server contract; ordinary URL behavior remained green. |
| Back restores the initially opened publication | `09-initial-history-browser-red.txt` (`3 != 2`) | `10-initial-history-browser-green.txt` | Real Chrome opens P2, changes selection, publishes P3, Back restores P2. |
| Empty selection survives reload and history | Server slice was already fixed by the shared URL helper | `11-empty-history-browser-green.txt` | Real Chrome checks reload, Back and Forward. |
| Active request failure | `12-active-failure-browser-red.txt` | `13-active-failure-browser-green.txt` | Real Chrome aborts a report request, checks alert text and retry. |
| Superseded failure ordering | Generation handling landed with the active-failure slice | `14-superseded-failure-browser-green.txt` | Real concurrent browser requests; late old failure cannot replace newer success. |
| Synthetic demo | `15-demo-red.txt` (unknown CLI command) | `16-demo-green.txt`, `19-demo-real-cli-green.txt` | The latter starts `python -m budget demo`, logs in over live HTTP and requests an HTMX fragment. |
| Shell, responsive layout and keyboard | Visual verification | `18-browser-visual-keyboard-green.txt` | Playwright checks desktop/phone ordering, no horizontal overflow and keyboard-only login/selection. |
| Network footer is factual | `26-footer-red.txt` | `27-footer-green.txt`, `28-browser-refresh.txt` | The server contract rejects the old machine-only claim; Chrome checks the replacement and refreshed screenshots. |

The plan's separate login red was folded into the renewal slice because both
were fixed by the same immutable snapshot. The superseded-failure slice was
implemented with the generation state used by the active-failure slice and
then verified independently in the browser.

## Focused test coverage

- `tests/dashboard/test_access.py` covers real file rotation during renewal and
  login through HTTP.
- `tests/dashboard/test_throttle.py` covers 50 lockout cycles at the public
  interface.
- `tests/dashboard/test_overview_page.py` covers pinned canonical URLs for
  ordinary and empty selections.
- `tests/dashboard/test_overview_browser.py` uses the installed Chrome channel
  through pinned Playwright. It covers history, empty state navigation,
  active-request failure and retry, superseded failure ordering, keyboard use,
  desktop/phone layout, overflow, and the factual network footer.
- `tests/cli/test_demo.py` covers development-profile creation, existing-target
  refusal, the serve invocation and a live CLI/HTTP/HTMX smoke test.

## Demo

```powershell
$demo = Join-Path $env:TEMP ("budget-demo-" + [guid]::NewGuid().ToString("N"))
uv run budget demo --directory $demo --port 8765
```

Open `http://127.0.0.1:8765` and log in with `budget-demo`. The expected screen
has `Demo current` and `Demo savings` selected and the current month selected.
It intentionally shows no financial figures. Stop with `Ctrl+C`, then remove
only `$demo`.

## Visual evidence

- `evidence/dashboard-desktop.png` at 1280 x 900.
- `evidence/dashboard-phone.png` at 390 x 844.

Playwright asserted that desktop panels are side by side, phone panels stack,
and document width never exceeds the viewport at either size.

## Quality and verification

- `26-footer-red.txt` and `27-footer-green.txt`: the network-footer contract
  changed from a failing assertion to a passing assertion.
- `28-browser-refresh.txt`: `6 passed`; refreshed both screenshots and checked
  the factual footer, keyboard flow and responsive layouts.
- `29-full-pytest-final.txt`: `821 passed, 1 xfailed, 412 subtests passed` in
  122.72 seconds, exit `0`.
- `30-ruff-lint-final.txt`: Ruff lint passed.
- `31-ruff-format-final.txt`: `241 files already formatted`.
- `32-ty-final.txt`: ty passed.
- `33-complexipy-final.txt`: complexity passed with no findings.
- `34-diff-check-final.txt`: `git diff --check` passed; the diff summary is
  recorded with the working-tree handoff.

## Exact focused commands

The original red/green artifacts were captured before command headers were
added to evidence files. Their exact commands are:

```powershell
# 01-renewal-red.txt, 02-rotation-green.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/dashboard/test_access.py::test_renewal_never_upgrades_a_session_authorized_before_passphrase_rotation tests/dashboard/test_access.py::test_login_never_issues_a_new_key_cookie_after_credential_rotation -q

# 03-throttle-red.txt, 04-throttle-green.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/dashboard/test_throttle.py tests/dashboard/test_access.py -q

# 05-initial-pin-red.txt, 06-initial-pin-green.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/dashboard/test_overview_page.py::test_a_fresh_page_names_the_fully_pinned_history_entry -q

# 07-empty-push-red.txt, 08-canonical-urls-green.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/dashboard/test_overview_page.py::test_a_fresh_page_names_the_fully_pinned_history_entry tests/dashboard/test_overview_page.py::test_an_empty_selection_still_moves_the_address_to_its_pinned_page tests/dashboard/test_overview_page.py::test_a_report_fetched_in_place_moves_the_address_to_its_own_page -q

# 09- through 14-, 17- and 18-browser artifacts
$env:PR310_SCREENSHOT_DIR = '<REPO>/docs/agent-work/pr310-review-fixes/evidence'
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/dashboard/test_overview_browser.py -q

# 15-demo-red.txt, 16-demo-green.txt and 19-demo-real-cli-green.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/cli/test_demo.py -q

# 20- through 23-quality artifacts
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync ty check
uv run --no-sync complexipy --quiet

# 24-full-pytest.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base -q

# 25-docs-frontmatter-except-root-plan.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/test_docs_frontmatter.py -q -k 'not PLAN'

# 26-footer-red.txt and 27-footer-green.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/dashboard/test_overview_page.py::test_the_shared_shell_describes_network_access_factually -q

# 28-browser-refresh.txt
$env:PR310_SCREENSHOT_DIR = '<REPO>/docs/agent-work/pr310-review-fixes/evidence'
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base tests/dashboard/test_overview_browser.py -q

# 29-full-pytest-final.txt
uv run --no-sync pytest -p no:cacheprovider --basetemp <TEMP>/base -q

# 30- through 33-final quality artifacts
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync ty check
uv run --no-sync complexipy --quiet

# 34-diff-check-final.txt
git diff --check
```

`<TEMP>` was a fresh writable directory under the workspace because the host's
default pytest temporary directory is sandbox-protected. `UV_CACHE_DIR` was
set to that same fresh directory.

## Limitations

- The superseded-failure browser test uses two injected HTMX source elements
  targeting the same persistent report region. This deliberately allows both
  requests to overlap and exercises the application's generation guard. It is
  not evidence about HTMX's ordinary same-form cancellation path.
- No red or green commits exist because the user prohibited commits and staging
  for this work. Red failures and green logs are retained as local evidence.
- Browser tests require an installed Google Chrome channel. Playwright is
  pinned as a development dependency and no browser binary is downloaded by
  the tests.

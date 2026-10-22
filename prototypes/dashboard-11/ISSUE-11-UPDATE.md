# Queued #11 update — not yet posted

The initial WIP comment was posted:
https://github.com/ATherkel/budget/issues/11#issuecomment-5848770964

The required agent-gh wrapper subsequently reported a missing AGENT_TOKEN.
The review checkpoint is saved in `%TEMP%/budget-11-round-2-review.md`.
After the credential is refreshed, post that checkpoint first, then the body
below. Update the lint paragraph if the maintainer approves LINT-PROPOSAL.md
and the resulting pinned check passes.

---

## Second prototype round ready for a user trial — 27 September 2026

The dashboard prototype has been carried onto a local branch based on main at
`59f732f2db3a5a03b1b6dcd3bd43427842457c65`, incorporating the handoff from
`claude/modest-galileo-9daepj` at `df907f2381e2581b4a496b2535b060be90dedcbc`.
The original prototype branches remain intact. The new branch,
`codex/prototype-11-round-2`, is uncommitted and not yet published.

### What can be tried now

- Simple (`Enkel`) is the default: three static monthly figures and category
  spending, with transactions available by opening a category. A quiet
  nonnumeric notice links to the explanation when figures need context.
- Advanced (`Avanceret`) offers overview, account details and a separate
  Checks (`Kontrol`) tab. Missing classifications, diagnostic counts and
  reconciliation live in Checks. Mode changes preserve the selected accounts,
  month, publication and financial values.
- Current, as-was and as-known-at publications have distinct synthetic
  reports. Historical views keep a named banner in both modes and a direct
  return to the current publication.
- The examples include paired transfers, a manually decided one-sided
  transfer, an unmatched claim reported as unknown, a net refund, incomplete
  account data and a confirmed quiet month. The provisional examples follow
  the export date-range and seven-day rules.
- The login/logout screen is explicitly a demonstration. The server uses
  synthetic fixtures only on loopback. No production authentication, import
  engine or editing workflow was added.
- The previous budget experiment remains under Advanced and outside the
  accepted first-delivery scope. REPORT-SHAPE.md is an updated proposal,
  including publication identity, currency, percentage units and category
  allocation contributions. It still requires maintainer review.

### Verification and limits

The fixture audit passes 2,236 checks against independent expected values;
regeneration is deterministic and a deliberately incorrect amount is rejected.
JavaScript syntax and Python formatting, types and complexity pass. Desktop
and phone browser checks cover mode switching, category details, publication
selection, year/custom/trailing chart ranges, budget navigation, empty
selection and missing-versus-zero displays. The final browser run reported no
console errors or horizontal overflow at its tested widths. Astra reviewed
the actual patch and corrected the findings from the first implementation.

The quality gate is not fully green: pinned Ruff reports INP001 and CPY001 on
the three standalone prototype Python scripts. An exact three-file exception
is proposed locally in LINT-PROPOSAL.md and awaits the owner's explicit
approval; no rule has been disabled.

No new participant feedback has been observed. The prototype remains a
throwaway fixture-based UI, with simplified historical balance examples.

### Next usability pass

Run `py -3.12 prototypes/dashboard-11/serve.py`, then open
`http://127.0.0.1:8011/` on that machine. The demo login accepts any input.
Let the participant least familiar with the repository drive first, without
explaining the answers:

1. Find where the money went this month.
2. Open a surprising category and explain its amount.
3. Identify figures that should be treated as incomplete.

Record where they hesitate and what they expected. Then try Advanced and
Checks with the maintainer. Use those observations to choose the next small
iteration; do not infer usability or accept the DTO merely from agent checks.
#11 remains open.

🤖 Generated with Codex (GPT-6 Astra)

---
type: architecture
---
# Gold Publications and History

## Summary

- A **publication** is one immutable Gold build from one **recipe** of every
  input it used; consumers read exactly one at a time.
- The **current** one is a pointer whose moves are logged, so `undo` and past
  views work.
- **A report is a function of recorded inputs**: no clock, nothing unrecorded.
  A lost result replays only from its exact inputs and producer.
- Recipes are kept forever, results only while current, previous or labeled.
- Decisions: [ADR-014](../decisions/ADR-014-gold-publications-and-history.md),
  [ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md),
  [ADR-020](../decisions/ADR-020-stage-specific-build-provenance.md).

## Two Time Axes

Every report answers *which data* it covers and *which interpretation*
(configuration, decisions, code) it applies. Each answer is a moment.

| View | Data | Interpretation | How it is produced |
| --- | --- | --- | --- |
| Current | every import run so far | today's | the current publication |
| As-was at D | import runs started by D | the one in force at D, including its code | the publication current at D, from its retained result or the [replay prerequisites](#what-reproducible-promises) |
| As-known-at D | import runs started by D | today's | a new publication of kind `as_known_at` |

Data is cut at the import run's recorded `started_at`, when the platform
learned of it, not the bank's export date. A date D means **the end of that
day in Europe/Copenhagen**, presentation's zone for "today"; a timestamp with
an explicit offset is taken as given. Every recorded moment is UTC, and D is
converted before comparing. Today's data under an earlier interpretation is not
offered: configuration is only known where a publication was built.

## The Recipe

A recipe names each input exactly, never by "latest":

| Part | Content |
| --- | --- |
| Silver build | An immutable copy of the provenance consumed from Silver, with the fields [Silver build provenance](silver-layer.md#build-provenance) defines; Gold never reads Bronze. It keeps every consumed import run, voided and repeated ones included, with its payload and declared account. Recipes migrated from schema 6 keep their runs with an unknown account, never inferred later. |
| Configuration snapshot | The parsed, canonical account registry, taxonomy and rules, stored once per distinct content and referenced by fingerprint. |
| Late-booking window | The profile's `[gold] late_booking_days` at the build ([`operations.md`](operations.md#selecting-a-profile)). `late_bookings_settled` depends on it, so a change needs a new publication. |
| Decision context | The position and prefix hash of the decision log consumed; effective Gold decisions come from the complete entries through it. |
| Gold code version | The commit that built Gold, with its locked dependencies and Gold contract version. It fixes the transfer matching policy ([`classification.md`](classification.md#inputs)). |

A recipe holds inputs only, so two can be compared before building. The Python
and SQLite versions, and Silver's own decision-log position and prefix hash,
are recorded for diagnosis and audit but are not part of the recipe's identity:
the log can move while Silver's result stays the same, and Silver's result
fingerprint decides whether Gold republishes. A new recipe with any unknown run
account is refused before anything is written.

### Gold Acceptance

Before writing a publication, Gold checks the Silver provenance its recipe
stores, without rereading Silver or Bronze:

| Stored Silver state | Check that decides whether Gold may publish |
| --- | --- |
| Unbuilt | No completion marker: refuse with exit 4. |
| Unknown | A completed result lacks usable provenance: refuse with exit 4. |
| Incompatible | The fingerprint scheme or Silver identity contract is unsupported: refuse with exit 4. |
| Stale decision-log prefix | The recorded prefix is no longer a prefix: refuse with exit 4 and name `budget rebuild --from silver`. |
| Stale effective decisions | Current effective Silver decisions differ from those recorded in provenance: refuse with exit 4 and name `budget rebuild --from silver`. |
| Stale consumed currencies | A consumed account currency differs: refuse with exit 4 and name `budget rebuild --from silver`. |
| Fresh | Every required scheme and freshness check passes: continue the Gold build. |
| Undeclared consumed account | The account is absent from `accounts.toml`: refuse with exit 3, name the account, and require its declaration. |

Unknown, stale and incompatible provenance stays readable where its shape
allows, but never authorizes a publication. A changed Silver result with the
same import-run IDs changes the recipe. Recovery actions are in
[Provenance recovery](operations.md#provenance-recovery).

### Gold Result Fingerprint

The **result fingerprint** belongs to the publication: a SHA-256 over a
canonical serialization of every record it returns through `GoldRepository`
and `GoldLineageRepository`, in key order. The serialization is versioned as
the **fingerprint scheme**, recorded beside each fingerprint; fingerprints
compare only within one scheme. The printed diff compares measures, so it
still shows moved figures across schemes.

`classification_version` in lineage fingerprints the classification inputs:
the configuration snapshot and the effective classification decisions. The
transfer policy and classifier code change with the code version instead.

## What Reproducible Promises

1. **A stored Silver build and its Gold recipe yield the same Gold result.**
   A retained result is read directly. An unretained one needs the exact
   consumed Silver result and the recipe's Gold inputs and producer; replaying
   them gives the same fingerprint. Missing prerequisites make replay
   unavailable, not a mismatch.
2. **Timestamps never enter the result.** `built_at` is metadata outside the
   fingerprint. The build reads no clock, file times, environment variables or
   import order beyond Silver's recorded order (ADR-009). Anything that depends
   on today, such as the provisional label, is computed when a report is read.
3. **Each code change is attributable to its stage.** Silver and Gold record
   their own producer code, and every build prints its diff. A behavior-neutral
   Gold change in the same scheme gives a new publication with the same
   fingerprint.
4. **Production only builds from named code.** It refuses uncommitted code;
   development makes no promise ([`operations.md`](operations.md#profiles)). A
   producer commit is never backfilled from a later checkout.

Not promised:

- Replay through an unrecorded parser. `rebuild --from bronze` works, but may
  give a new result when the installed parser changes.
- Replay of a recipe whose code no longer runs. A result that must outlive its
  code is labeled, and kept across an unconvertible migration as in
  [Retention](#retention).
- Stable `transaction_id`s across a Silver identity version change, which needs
  a migration of every reference, the decision log included (ADR-009).

## Identity Across Publications

| Identifier | Stable across publications | Notes |
| --- | --- | --- |
| `account_id`, `category_id`, `group_id` | Always | Immutable household keys (contract invariant 1). |
| `transaction_id` | While the Silver identity version holds | Derived from Silver identity (ADR-009). |
| `allocation_id`, `transfer_group_id`, `review_item_id` | While the same inputs produce them | Derived from the identifiers above. |
| `account_sequence` | No | Ordering only. |
| `publication_id` | Names one publication | Increasing integer per store. |
| (`publication_id`, `transaction_id`) | Names one version of one fact | The only way two versions of a transaction differ. |

Facts do not carry `publication_id`; a consumer learns it from
`GoldRepository.publication()`. **No double counting**: every Gold table is
keyed by `publication_id` first, every repository read filters on exactly one,
and no interface reads across publications.

## Lifecycle

### Pipeline builds

An import, a configuration change, a decision or a new code version starts a
pipeline build:

1. Bronze has already committed the import run's payload.
2. Silver derives and commits one complete result with one provenance value.
3. Gold reads it and the household inputs and runs
   [Gold Acceptance](#gold-acceptance).
4. The recipe is assembled. If it equals the current one, nothing is built.
5. Gold is derived and checked. A configuration, freshness or compatibility
   error fails the build before publication (ADR-011, ADR-020).
6. In one write transaction the result is stored, the pointer moves and the
   pointer history records it. A failed build changes nothing, and readers
   never see a partial publication.
7. The CLI prints a **diff against the previous current publication**: per
   month and account, the changed measures (income, expenses, each category
   and group, unclassified money, coverage) and the review items opened and
   closed. It holds financial values, so it goes to the terminal only.

### Undo

`undo` moves the pointer back to the previous current publication and records
the move, so undo is itself undoable. It changes no input: fix the mistake, or
the next build brings it back.

### Pointer history

Every move of the pointer appends one row:

| Field | Meaning |
| --- | --- |
| `moved_at` | When the move committed, in UTC. |
| `from_publication_id` | The publication current before the move; null for a store's first build. |
| `to_publication_id` | The publication current after the move. |
| `cause` | `build`, `undo`, or `migration`. |

The publication current at a moment is the `to_publication_id` of the last
move at or before it; the previous one is the last move's
`from_publication_id`. The diff and the dashboard banner show the cause.

### Publication recovery

`restore` brings back Gold's recipes, results and pointer history as the
backup set holds them; later publications, labels and pointer moves are lost.
If the recipe changed since, catch-up builds a new current publication, and
undo returns to the set's current one, which `restore` names.

Each restore records a **recovery boundary** in `gold.db`: the set and when it
was taken, when the restore ran, the set's current publication, and the first
`publication_id` after the restore. Past-view lookups read it to report the
time between the set and the restore as unavailable.

That first id is the smallest multiple of 1,000,000 above the highest id the
restored store holds (1,000,000 for none), so an id written down before the
restore never names a publication built after it. A never-restored store
numbers 1, 2, 3, …. A second restore of the same or an older set jumps from
that set's highest id again, so it can reuse ids that builds between the two
restores took (pending: [#414](https://github.com/ATherkel/budget/issues/414)).

### Past views

Only the CLI builds views; the dashboard stays read-only. A view never becomes
current.

- `view --as-was D --label L` finds the publication current at the end of D.
  A retained result is labeled; otherwise it is replayed
  [from exact inputs](#what-reproducible-promises), never with today's code.
  A replay keeps the original `built_at` and `known_at`, records
  `replayed_at`, and must match the recorded fingerprint.
- `view --known-at D --label L` builds a new `as_known_at` publication from
  the runs started by D, with today's configuration, decisions and code. A
  decision whose target was not imported by D raises
  `decision-not-applicable`.

### Verify

Recipe replay by `verify` is pending
([#259](https://github.com/ATherkel/budget/issues/259)). It will replay
[from exact inputs](#what-reproducible-promises) and compare the fingerprint
without publishing; a mismatch once the prerequisites hold is a defect.

### Scratch stores

Views, replays and verification run in a **scratch store**, a temporary SQLite
file where the profile says ([`operations.md`](operations.md#stores)), created
by the migrate runner so only it creates schemas (ADR-013). A result to keep,
an as-known-at view or a replayed as-was view, is copied into the main store in
one transaction, and the scratch file deleted. A replay joins the main store
only when its code's `user_version` equals the store's; otherwise it refuses
`--label`, still checks the fingerprint, and the CLI shows the view from the
scratch store. Invariant 7 keeps its single exception.

## Retention

Every recipe is kept forever. A **result** is kept only for the current
publication, the previous one (so `undo` is instant), and every labeled one
until its label is removed. Others are deleted when they stop qualifying;
re-creating one needs the [replay prerequisites](#what-reproducible-promises).

A Gold migration converts the retained results it can. One it cannot survives
only in the pre-migration backup (ADR-013). A labeled one also becomes a
[legacy publication](operations.md#legacy-publications), and retention keeps
that backup (ADR-015). The migration then runs a pipeline build with `cause`
`migration`; until it commits, `current()` returns `None` and the dashboard
says nothing is published, and `undo` has nothing to return to until the next
build. Development and test take no backup, so they lose unconvertible
results.

## The Decision Log

Every manual decision, whether it classifies a transaction, settles a review
item or voids an import run, is an entry in one append-only log
([format](operations.md#decisionsjsonl-the-decision-log)):

| Field | Meaning |
| --- | --- |
| `entry` | Increasing position in the log. |
| `decision_id` | Durable identifier of the decision. |
| `recorded_at` | When the platform accepted the entry. It is set by the platform, never typed by a person. |
| `kind` | For example `classify`, `pair`, `one-sided-transfer`, `retract`, or Silver's kinds. |
| `targets`, outcome, `reason` | As defined for the kind. A `retract` entry has no targets and no outcome. |
| `supersedes` | The `decision_id`s this entry replaces. Empty for most entries. |

- An entry is never edited or deleted. A new entry supersedes one to change it;
  a `retract` supersedes one to withdraw it.
- The effective decisions at an entry are those recorded and not superseded up
  to it, excluding `retract`s, which are never effective.
- Decisions collide only within a group, never Silver with Gold:
  - `classify`, `pair` and `one-sided-transfer` collide on a transaction, so
    ADR-011's "at most one decision per transaction" holds by construction.
  - `void-import-run` and `accept-discrepancy` collide on an import run.
  - `withdrawn` and `same-transaction` exclude each other on a transaction;
    several `same-transaction`s stand, one per `record.payload_id`.
- An entry that collides with an effective decision must list it in
  `supersedes`. Each listed decision must be effective and, unless the entry
  is a `retract`, collide with it, so nothing is cancelled quietly. Otherwise
  [the boundary](operations.md#the-validation-boundary-for-decisions) rejects
  the entry.
- One entry can supersede several: a `pair` whose legs each had a `classify`
  supersedes both, so no publication shows both legs unclassified.
- Rules, taxonomy and account registry stay edited files, whose history is the
  configuration snapshots.

## Reading a Publication

```python
class GoldPublications(Protocol):
    def current(self) -> GoldPublication | None: ...  # None before the first build
    def available(self) -> Sequence[GoldPublication]: ...  # retained results
    # Raises PublicationUnavailableError.
    def open(self, publication_id: int) -> GoldRepository: ...
```

`GoldStore` in `budget.gold.store` implements it. A build takes its id from
`next_publication_id()` and stores the result with
`publish(result, recipe, configuration)`. `GoldRepository.publication()` names
the one publication all its reads come from.

The dashboard opens the current publication per page and carries that
`publication_id` in follow-up requests, so a page never mixes publications.
`current()` returns `None` when no current result is retained: before the first
build, and after an unconvertible migration until the next build. `open()`
raises `PublicationUnavailableError` for a publication that does not exist or
whose result was deleted, and the dashboard offers the current one.

### Reader Connection Lifetime

The dashboard's reader is a `GoldStore(profile, read_only=True)` owning one
`mode=ro` SQLite connection. Open, use and close it on the creating thread,
within one request or task:

```python
with GoldStore(profile, read_only=True) as publications:
    reports = HouseholdReports(publications)
    overview = reports.monthly_overview(context)

# `overview` and `context` are immutable DTOs; the store's connection is gone.
```

A page carries its `ReportContext`, not a store or repository; each request
opens a fresh store on its own thread. A repository from `open()` borrows its
store's connection and cannot outlive it.

Misuse raises a `GoldStoreLifecycleError` subclass, which analytics passes on
unchanged: `GoldStoreClosedError` after close, `GoldStoreThreadError` from
another thread (a wrong-thread close releases nothing). Closing is idempotent
on the creating thread, and SQLite's thread check stays on. `publish()` on a
read-only store raises `GoldStoreReadOnlyError` before any write.

## Synthetic Scenarios

All figures are synthetic, for February 2026 on `joint-current`, and use the
taxonomy from [`classification.md`](classification.md), with one extra
category: `streaming` in a new expense group `leisure`.

| Rule | When | Assigns |
| --- | --- | --- |
| `r-netto` | text contains `NETTO` | `groceries` |
| `r-home` | text contains `IKEA` | `household-goods` |
| `r-streaming` | text contains `NETFLIX` | `streaming` |

| Id | Transaction | First imported in |
| --- | --- | --- |
| A | 2026-02-02 −640.00 `NETTO 0412` | run-1 |
| B | 2026-02-12 +120.00 `NETTO 0412` | run-1 |
| C | 2026-02-07 −2,400.00 `IKEA 551` | run-1 |
| E | 2026-02-18 −129.00 `NETFLIX.COM` | run-1 |
| F | 2026-02-27 −300.00 `NETTO 0412`, a late booking | run-2 |

Import run-1 starts on 2026-03-03, from an export covering through
2026-03-02. Import run-2 starts on 2026-03-10, from an export covering
2026-02-01 to 2026-03-09.

### Lifecycle

| # | When | Change | Result | February: groceries / household-goods / gifts / streaming | Expenses | Unclassified out |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 03-03 | Import run-1 | P1 current | 520.00 / 2,400.00 / 0.00 / 129.00 | 3,049.00 | 0.00 |
| 2 | 03-10 | Import run-2: late booking F | P2 current | 820.00 / 2,400.00 / 0.00 / 129.00 | 3,349.00 | 0.00 |
| 3 | 04-10 | **Category correction.** Decision-log entry 1: `classify` C → `gifts` | P3 current | 820.00 / 0.00 / 2,400.00 / 129.00 | 3,349.00 | 0.00 |
| 4 | 04-12 | **Rule change.** Add `r-net`: text contains `NET` → `groceries` | P4 current | 820.00 / 0.00 / 2,400.00 / 0.00 | 3,220.00 | −129.00 (1) |
| 5 | 04-12 | `undo` | P3 current again | as step 3 | 3,349.00 | 0.00 |
| 6 | 04-12 | Delete `r-net` from the rules file | Nothing published: the recipe equals P3's | as step 3 | 3,349.00 | 0.00 |
| 7 | 05-02 | **Dimension change.** Rename `streaming` to "Subscriptions" and move it from `leisure` to `housing`; logged in `category-changes.md` | P5 current | as step 3 | 3,349.00 | 0.00 |
| 8 | 05-03 | **Gold recipe verification (pending)** | Nothing published when the exact-input replay matches | as step 3 | 3,349.00 | 0.00 |
| 9 | 06-01 | New code version, with no change in behavior | P6 current, same result fingerprint as P5 | as step 3 | 3,349.00 | 0.00 |

- **Step 3.** 2,400.00 moves between categories, so Expenses hold. The decision
  beats `r-home` (ADR-011); lineage still names `r-home` as matching.
- **Step 4.** `r-net` and `r-streaming` have equal priority and disagree on E,
  so E becomes `unknown` with a `rule-conflict` review item (ADR-011); A, B and
  F match `r-net` and `r-netto`, which agree. The diff, *February streaming
  −129.00, Expenses −129.00, unclassified out −129.00, one `rule-conflict`
  opened*, is the cue to undo.
- **Step 6.** The snapshot is of parsed content, so restoring a rule's meaning
  restores the fingerprint. A `contains` or `starts_with` pattern counts by its
  case-folded text; a regular expression counts as written.
- **Step 7.** No fact or allocation changes, but the `GoldCategory` row does,
  so the fingerprint changes. Group rollups restate every month: `leisure`
  −129.00, `housing` +129.00 in February.
- **Step 9.** Only the code version differs, in the same scheme, and the
  fingerprint is unchanged: the change was behavior-neutral.

Pointer history after step 9: P1, P2, P3, P4, P3, P5, P6. Results kept: P6
(current) and P5 (previous).

### Views, on 2026-06-15

V1 depends on the pending replay in [Verify](#verify): an unretained P1 is
available only with its exact replay inputs.

| # | Request | Publication read | February: groceries / household-goods / gifts / streaming (name, group) | Expenses |
| --- | --- | --- | --- | --- |
| V1 | `view --as-was 2026-03-05 --label "March review"` | P1, using the pending exact-input replay | 520.00 / 2,400.00 / 0.00 / 129.00 ("Streaming", `leisure`) | 3,049.00 |
| V2 | `view --known-at 2026-03-05 --label "Known 5 March"` | P7, kind `as_known_at`: run-1 only, today's interpretation | 520.00 / 0.00 / 2,400.00 / 129.00 ("Subscriptions", `housing`) | 3,049.00 |
| V3 | the dashboard, default | P6 | 820.00 / 0.00 / 2,400.00 / 129.00 ("Subscriptions", `housing`) | 3,349.00 |

- **V1** shows what the household saw on 5 March: IKEA as household goods,
  under the old category name and group. Step 9 changed no schema, so the
  replay joins the main store and the label keeps it.
- **V2 against V3** isolates late bookings: 300.00 of groceries reached
  February after 5 March.
- **V1 against V2** isolates reinterpretation: the IKEA correction and the
  rename, on the same data.
- A past view's provisional label is as of its knowledge time: the build time
  for as-was (3 March for V1), D for as-known-at (end of 5 March for V2).
  February is provisional in both: no export produced 7 days after February
  had been imported by then.
- The store now holds P6, P5, P1 and P7. Summing February expenses over all of
  them would read 3,349.00 + 3,349.00 + 3,049.00 + 3,049.00 = 12,796.00, which
  is why no interface reads across publications.

## Invariants

1. A store has at most one current publication. After its first successful
   build it has exactly one, except between a Gold migration that could not
   convert the current result and the build that follows it.
2. A publication's result is complete or absent, and never changes once
   stored.
3. Every Gold record belongs to exactly one publication, and every consumer
   read is confined to one.
4. A Gold build uses the exact-input reproducibility rule in
   [What Reproducible Promises](#what-reproducible-promises).
5. The pointer history and the decision log are append-only.
6. An `as_known_at` publication is never current.
7. Every recipe is retained. The results of the current publication, the
   previous one, and every labeled one are retained in the store. The one
   exception is a Gold migration that cannot convert a result: that result
   then survives in the pre-migration backup instead, and, when labeled, in
   its legacy extract (ADR-015).

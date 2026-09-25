# Gold Publications and History

Status: accepted ([ADR-014](../decisions/ADR-014-gold-publications-and-history.md)),
with legacy publications added by
[ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md).
Command names and file formats are in [`operations.md`](operations.md).

## Purpose

A Gold build reads much more than Silver. It reads the account registry, the
category taxonomy, the classification rules, the manual decisions, the
transfer matching policy, and the code that implements them. Any of these can
change, and every change restates history. This document defines what one
build of Gold is, which build a report reads, what is kept of past builds,
and what "reproducible" promises.

The principle behind it is that **a report is a function of recorded inputs**.
The build never reads the clock or anything else that was not recorded, so a
past report can always be explained, and it can be shown again exactly
whenever its code still runs.

## Terms

- **Publication**: one complete, immutable build of Gold. It holds every
  dimension row, every fact, the lineage, and the review items, all built
  from one recipe. A consumer reads exactly one publication at a time.
- **Recipe**: the record of every input a publication was built from. See
  [The Recipe](#the-recipe). The publication, not the recipe, carries the
  fingerprint of the result.
- **Current publication**: the one reports show by default. It is a pointer,
  and every move of the pointer is appended to the *pointer history*.
- **Decision log**: the append-only record of manual decisions. See
  [The Decision Log](#the-decision-log).
- **As-was view**: the publication that was current at a moment D, shown
  exactly as it was.
- **As-known-at view**: a new publication built from only the import runs
  started by D, interpreted with today's configuration, decisions, and code.

## Two Time Axes

Every report answers two questions: *which data* does it cover, and *which
interpretation* (configuration, manual decisions, code) does it apply? Each
answer is a point in time.

| View | Data | Interpretation | How it is produced |
| --- | --- | --- | --- |
| Current | every import run so far | today's | the current publication |
| As-was at D | import runs started by D | the one in force at D, including its code | the publication current at D, from its retained result or by replaying its recipe |
| As-known-at D | import runs started by D | today's | a new publication of kind `as_known_at` |

The data axis is cut at the import run's recorded `started_at`: the moment the
platform learned of the data. The bank's export date is not used, because it
says when the bank made the file, not when the household knew of it.

A moment D given as a date means **the end of that day in Europe/Copenhagen**,
the zone presentation already uses for "today". "Started by D" therefore
includes an import at 21:30 on D, and an as-was view at D shows the
publication current at the end of D. D may instead be a timestamp with an
explicit offset, which is taken as given. `started_at`, like every recorded
moment in this document, is stored in UTC (`bronze-layer.md`), and D is
converted to UTC before it is compared.

A fourth combination is possible: all of today's data under the interpretation
in force at D. The first release does not offer it. Configuration files are
read only when a build runs, so an interpretation is known only at the points
where a publication was built.

## The Recipe

A recipe names each input exactly and never by "latest":

| Part | Content |
| --- | --- |
| Data | The set of import runs, each with its `import_run_id` and payload hash. Silver derives admission and quarantine from these; admission is not an input. |
| Configuration snapshot | The parsed, canonical content of the account registry, category taxonomy, classification rules, and transfer matching policy. It is stored once per distinct content and referenced by its fingerprint. |
| Decision log position | The last decision-log entry included. The effective decisions are derived from the log up to that entry. |
| Code version | The commit of the application code, with its locked dependencies, and the Gold contract version and Silver identity version it implements. |

A recipe holds inputs only, so two recipes can be compared before anything is
built. The recipe also records the Python and SQLite versions that ran the
build.
They are diagnostic only and not part of the recipe's identity.

The result belongs to the publication. Its **result fingerprint** is a
SHA-256 hash over a canonical serialization of every record the publication
returns through `GoldRepository` and `GoldLineageRepository`, in key order.
The serialization is versioned as the **fingerprint scheme**, which is
recorded beside each fingerprint, and fingerprints are compared only within
one scheme. A code version that changes the scheme, for example by adding a
contract field, makes its fingerprints incomparable with earlier ones. The
printed diff compares measures, not fingerprints, so it still shows whether
any figure moved.

`classification_version` in lineage is the fingerprint of the classification
inputs: the configuration snapshot and the effective classification
decisions.

## What Reproducible Promises

1. **The same recipe yields the same result.** Rebuilding a recipe with the
   code version it names gives a result with the same fingerprint: the same
   records, identifiers, and amounts.
2. **Timestamps never enter the result.** `built_at` is publication metadata
   outside the fingerprint. The build never reads the clock, file modification
   times, environment variables, or import order beyond the order Silver
   derives from recorded fields (ADR-009). Anything that depends on today's
   date, such as the provisional label, is computed when the report is read.
3. **A code change is attributable.** Different code may give a different
   result. The recipe names the code, so the difference is explained, and the
   diff printed on every build shows it. A behavior-neutral code change that
   keeps the fingerprint scheme yields a new publication with an unchanged
   result fingerprint.
4. **Production only builds from named code.** A production build refuses to
   run when it cannot name its code version exactly, for example from
   uncommitted changes. A development store makes no reproducibility promise:
   a development build may run from uncommitted code, and nothing records
   which code that was. Each profile keeps its own stores
   ([`operations.md`](operations.md#profiles)).

Not promised:

- Replaying a recipe whose code can no longer run. A publication that must
  outlive its code keeps its result by being labeled, and across a Gold
  migration that cannot convert it, in the pre-migration backup
  ([Retention](#retention)).
- Stable `transaction_id`s across a Silver identity version change. That
  change needs a migration of every reference (ADR-009), including the
  decision log.

## Identity Across Publications

| Identifier | Stable across publications | Notes |
| --- | --- | --- |
| `account_id`, `category_id`, `group_id` | Always | Immutable household keys (contract invariant 1). |
| `transaction_id` | While the Silver identity version holds | Derived from Silver identity (ADR-009). |
| `allocation_id`, `transfer_group_id`, `review_item_id` | While the same inputs produce them | Derived from the identifiers above. |
| `account_sequence` | No | Ordering only. |
| `publication_id` | Names one publication | Increasing integer per store. |
| (`publication_id`, `transaction_id`) | Names one version of one fact | The only way two versions of a transaction differ. |

Facts do not carry `publication_id`. A consumer learns which publication it is
reading from `GoldRepository.publication()`.

**No double counting.** Every Gold table is keyed by `publication_id` first.
Every repository read filters on exactly one, and no interface reads across
publications. A summed query over a store that holds several retained results
would otherwise count each transaction once per result.

## Lifecycle

### Pipeline builds

An import, a configuration change, a new manual decision, or a new code version
starts a pipeline build:

1. Bronze has already committed the import run's payload on import.
2. The build assembles the recipe from the current inputs. If the recipe
   equals the current publication's recipe, nothing is built or published.
3. Silver and Gold are derived and checked. A configuration error fails the
   build (ADR-011).
4. On success, in one write transaction, the new publication's result is
   stored, the pointer moves to it, and the pointer history records the move.
   A failed build leaves everything as it was, and readers never see a partial
   publication.
5. The CLI prints a **diff against the previous current publication**: per
   month and account, the measures that changed (income, expenses, each
   category and group, unclassified money, and coverage), and the review items
   opened and closed. The diff contains financial values, so it goes to the
   terminal and never to routine logs.

### Undo

`undo` moves the pointer back to the previous current publication and appends
the move to the pointer history. Undo is itself undoable: after undo, the
publication just left is the previous one. Undo changes no input. The mistake
must still be fixed; otherwise the next build brings it back.

### Pointer history

Every move of the pointer appends one row:

| Field | Meaning |
| --- | --- |
| `moved_at` | When the move committed, in UTC. |
| `from_publication_id` | The publication current before the move; null for a store's first build. |
| `to_publication_id` | The publication current after the move. |
| `cause` | `build`, `undo`, or `migration`. |

The publication current at a moment is the `to_publication_id` of the last
move at or before it. The previous current publication is the
`from_publication_id` of the last move. The printed diff and the dashboard
banner show the cause.

### Past views

A view is always built by the CLI and never by the dashboard, which stays
read-only.

- `view --as-was D --label L` finds the publication that was current at the
  end of D in the pointer history. If its result is retained, it is labeled.
  Otherwise its recipe is replayed under the same `publication_id`, in a
  scratch store, and the replay must match the recorded fingerprint. Replay
  needs the code version the recipe names; the CLI refuses to replay with any
  other code and names the version to use. A replay keeps the publication's
  original `built_at` and `known_at`, and records when it happened in
  `replayed_at`, so the banner and the provisional label stay dated to the
  original build.
- `view --known-at D --label L` builds a new publication of kind
  `as_known_at` from the import runs started by D, with today's
  configuration, decisions, and code. A decision whose target was not yet
  imported at D raises `decision-not-applicable`, as it would have then.

A view can never become current.

### Verify

`verify` replays the current publication's recipe from Bronze in a scratch
store and compares the result fingerprint with the recorded one. It publishes
nothing and changes nothing. It refuses to run when the running code is not
the code version the recipe names.

- **Match:** reproducibility is shown, and `verify` says so.
- **Mismatch:** a platform defect, not a data problem, so it never becomes a
  review item. `verify` fails with a non-zero exit status, prints both
  fingerprints and the first differing records by key, and leaves the current
  publication in place. The defect is fixed in code, and the fixed code's
  next build becomes current as usual.

### Scratch stores

Views, replays, and `verify` derive Silver and Gold away from the current
state, in a **scratch store**: a temporary SQLite file in a location the
profile configures ([`operations.md`](operations.md#stores)). The migrate
runner creates it from the same migration files, so ADR-013's rule that only the migrate command creates a
schema still holds, and opening a store still never creates tables. An
in-memory database is not used, because only the migrate runner may create
tables.

When the work finishes, a result that is to be kept, meaning an as-known-at
view or a replayed as-was view, is copied into the main store in one write
transaction, and the scratch file is deleted. A replayed result joins the
main store only when its code's schema version (`user_version`) equals the
main store's. When the versions differ, the running dashboard could not open
the result, so the replay refuses `--label`. It still checks the fingerprint,
and the CLI shows the view from the scratch store with that code version. The
scratch store is then deleted, the recipe remains, and invariant 7 keeps its
single exception.

## Retention

Every recipe is kept forever. A few kilobytes each, recipes are what make
history explainable.

A **result** (the publication's tables) is kept only for:

- the current publication;
- the previous current publication, so `undo` is instant;
- every labeled publication, until its label is removed.

Any other result is deleted when it stops qualifying. It can be re-created by
replaying its recipe with the code it names.

A Gold schema migration converts the retained results where it can. A result
it cannot convert survives only in the backup that production takes before
migrating (ADR-013), which the code version that built it can open. Its recipe
also remains, and can be replayed with that code version into a separate store.
A labeled result is also extracted to its own file and recorded as a legacy
publication, and retention keeps its backup
([ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md),
[`operations.md`](operations.md#legacy-publications)).

After such a migration, the migrate command runs a pipeline build with the new
code. The new publication becomes current, with `cause` `migration` in the
pointer history. Until that build commits, the store has no current
publication: `current()` returns `None`, and the dashboard says so. Until the next build after it, `undo` has no
previous result to return to. Development and test stores take no backup
before migrating, so they lose any result a migration cannot convert.

## The Decision Log

Every manual decision, whether it classifies a transaction, settles a review
item, or voids an import run, is an entry in one append-only log:

| Field | Meaning |
| --- | --- |
| `entry` | Increasing position in the log. |
| `decision_id` | Durable identifier of the decision. |
| `recorded_at` | When the platform accepted the entry. It is set by the platform, never typed by a person. |
| `kind` | For example `classify`, `pair`, `one-sided-transfer`, `retract`, or the Silver kinds from issue #5. |
| `targets`, outcome, `reason` | As defined for the kind. A `retract` entry has no targets and no outcome. |
| `supersedes` | The `decision_id`s this entry replaces. Empty for most entries. |

- An entry is never edited or deleted. To change a decision, record a new one
  that supersedes it. To retract one without replacing it, record a `retract`
  entry that supersedes it.
- The kind is `retract`, not *withdraw*, so it cannot be confused with Silver's
  *withdrawn*, which records that the bank removed a transaction.
- The effective decisions at an entry are those recorded up to it and not
  superseded up to it, excluding `retract` entries, which are never
  effective.
- An entry that targets a transaction already targeted by an effective
  decision must list that decision in `supersedes`, and every decision it
  lists must be effective. Otherwise the entry is rejected when it is
  recorded, so ADR-011's "at most one decision per transaction" holds by
  construction. The same validation serves the CLI now and a browser editor
  later ([`operations.md`](operations.md#the-validation-boundary-for-decisions)).
- One entry can supersede several decisions. A `pair` of two legs that are
  each classified by their own decision supersedes both in one entry, and
  therefore in one build, never passing through a publication where both legs
  are unclassified.
- Rules, the taxonomy, the account registry, and the matching policy remain
  edited files. Their history is the configuration snapshots in recipes.

## Reading a Publication

```python
class GoldPublications(Protocol):
    def current(self) -> GoldPublication | None: ...  # None before the first build
    def available(self) -> Sequence[GoldPublication]: ...  # retained results
    def open(self, publication_id: int) -> GoldRepository: ...  # PublicationUnavailable
```

`GoldRepository` gains `publication() -> GoldPublication`. Every read through
one `GoldRepository` comes from its one publication. The dashboard opens the
current publication for each page and carries that `publication_id` in the
page's follow-up requests, so a page never mixes two publications, even if a
build finishes while it is open.

`current()` returns `None` when there is no current publication with a
retained result: before a store's first successful build, and between a Gold
migration that could not convert the current result and the build that
follows it. The dashboard then says that nothing is published. `open()` raises
`PublicationUnavailable` when the publication does not exist or its result is
not retained. Example: a page is pinned to P5, two imports run, and P5's
result is deleted. The page's next request gets `PublicationUnavailable`, and
the dashboard offers the current publication instead.

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
| 8 | 05-03 | **Full rebuild.** `verify` rebuilds Silver and Gold from Bronze into a scratch store | Nothing published: the fingerprint equals P5's | as step 3 | 3,349.00 | 0.00 |
| 9 | 06-01 | New code version, with no change in behavior | P6 current, same result fingerprint as P5 | as step 3 | 3,349.00 | 0.00 |

Notes:

- **Step 3.** The correction moves 2,400.00 between categories, so Expenses
  do not change. The decision beats `r-home` (ADR-011), and lineage still
  names `r-home` as matching.
- **Step 4.** `r-net` and `r-streaming` have equal priority and disagree on E,
  so E becomes `unknown` with a `rule-conflict` review item (ADR-011). A, B,
  and F match both `r-net` and `r-netto`, which agree, so they are unchanged.
  The build's diff shows it: *February streaming −129.00, Expenses −129.00,
  unclassified out −129.00, one `rule-conflict` opened*. That diff is the cue
  to undo.
- **Step 6.** The configuration snapshot is taken of parsed content, so a
  rules file restored to its old meaning gives the same fingerprint.
- **Step 7.** No fact or allocation changes. The `GoldCategory` row changes,
  so the result fingerprint changes too. Group rollups restate for every
  month: `leisure` −129.00, `housing` +129.00 in February.
- **Step 8.** The same recipe and code give the same result. This is the
  routine proof of reproducibility.
- **Step 9.** P6's recipe differs from P5's only in its code version. Both
  use the same fingerprint scheme, and the result fingerprint is unchanged.
  That shows the code change was behavior-neutral.

Pointer history after step 9: P1, P2, P3, P4, P3, P5, P6. Results kept: P6
(current) and P5 (previous).

### Views, on 2026-06-15

| # | Request | Publication read | February: groceries / household-goods / gifts / streaming (name, group) | Expenses |
| --- | --- | --- | --- | --- |
| V1 | `view --as-was 2026-03-05 --label "March review"` | P1, replayed from its recipe with P1's code; fingerprint verified | 520.00 / 2,400.00 / 0.00 / 129.00 ("Streaming", `leisure`) | 3,049.00 |
| V2 | `view --known-at 2026-03-05 --label "Known 5 March"` | P7, kind `as_known_at`: run-1 only, today's interpretation | 520.00 / 0.00 / 2,400.00 / 129.00 ("Subscriptions", `housing`) | 3,049.00 |
| V3 | the dashboard, default | P6 | 820.00 / 0.00 / 2,400.00 / 129.00 ("Subscriptions", `housing`) | 3,349.00 |

- **V1** shows exactly what the household saw on 5 March: IKEA as
  household goods, and the old category name and group. `k1` and `k2` share a
  schema version (step 9 changed no schema), so the replayed result joins the
  main store and the label keeps it.
- **V2 against V3** isolates the late bookings: 300.00 of groceries reached
  February after 5 March. Everything else is the same interpretation.
- **V1 against V2** isolates reinterpretation: the IKEA correction and the
  category rename, on the same data.
- Past views get the provisional label as of their knowledge time: the
  original build time for an as-was view, and D for an as-known-at view.
  V1's knowledge time is 3 March, P1's build, and V2's is the end of 5 March.
  February is provisional in both, because by neither moment had an export
  produced at least 7 days after the end of February been imported.
- After V1 and V2 the store holds four results: P6, P5, P1, and P7. A query
  summing February expenses over all of them without a publication filter
  would read 3,349.00 + 3,349.00 + 3,049.00 + 3,049.00 = 12,796.00. That is
  why no interface reads across publications.

## Invariants

1. A store has at most one current publication. After its first successful
   build it has exactly one, except between a Gold migration that could not
   convert the current result and the build that follows it.
2. A publication's result is complete or absent, and never changes once
   stored.
3. Every Gold record belongs to exactly one publication, and every consumer
   read is confined to one.
4. A build reads only what its recipe names. Rebuilding a recipe with the
   code version it names yields the same result fingerprint.
5. The pointer history and the decision log are append-only.
6. An `as_known_at` publication is never current.
7. Every recipe is retained. The results of the current publication, the
   previous one, and every labeled one are retained in the store. The one
   exception is a Gold migration that cannot convert a result: that result
   then survives in the pre-migration backup instead, and, when labeled, in
   its legacy extract (ADR-015).

## Left to Other Tickets

- **Issue #11:** how the dashboard shows the publication picker and the banner
  for a non-current publication.
- **Issue #12:** acceptance cases for version selection, deterministic
  replay, and changed rules and manual inputs, taken from the scenarios above.

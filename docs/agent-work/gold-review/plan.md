---
type: gold-review
---
# Issue 258: published Gold review

User approved the `budget review` CLI as the test seam, with synthetic stores,
on 2026-10-24. Workflow: ship-issue, red-green deferred. Base:
`113ba5028ca9d28fbbb47cf2804690f52dc2666b`, branch `claude/258-gold-review`.

## Contract

Extend the existing review route with published classification questions. Keep
Silver output and filters compatible. Gold items and their targets must come
from one current publication selected once; concurrent publishing must not mix
results. Read without the writer lock or migration, and never rebuild to review.
An absent Gold file or no current publication leaves Silver review available;
other invalid-store errors retain the existing refusal conventions.

Persist classification review items atomically with their publication using an
additive numbered Gold migration. Preserve ordered target/rule identifiers
exactly as classified; missing decision targets stay absent per the accepted
Gold contract, and the decision ID identifies the non-applicable decision. Bind all
reads and retention cleanup to publication_id. Do not invent old review items
for existing publications that never stored them. Keep the privileged review
read interface separate from analytics. Use a SQLite read snapshot for the
entire selection and materialization to survive concurrent pointer changes and
retention. Do not persist unrelated lineage without need.

Output follows accepted operations/classification policy: stable review and
decision/rule identifiers, transaction handles (first eight characters), and
only already-permitted target details. No full transaction IDs or arbitrary
reason text in routine logs. Handle collisions are for #178 to reject, never
silently resolved here. Account filtering selects items involving a matching
published target and retains all targets needed to understand that item;
missing targets remain visible without an account filter. Kind filtering must
support published Gold kinds. No decide command, dashboard, pipeline assembly,
production access, or workflow changes. W2's complete decision/rebuild loop is
owned by #178; this issue proves its discovery half.

## Ordered slices

1. CLI lists a persisted Gold rule conflict with stable references and targets,
   alongside Silver output. Add minimal persistence and read support.
2. CLI lists unmatched/ambiguous transfer and non-applicable decisions,
   including a decision with no surviving target; enforce kind/account filtering.
3. CLI preserves Silver behavior with no publication and pins the publication
   while another publication is built/published, including retention effects.
4. CLI output and routine logs preserve the accepted privacy boundary and the
   command remains read-only under a writer lock.

Split slices further only when a focused test requires it. One red then its
green at a time, never a bulk batch of speculative tests. Evidence must include
actual red assertion failure, green result, and code-quality checks per slice.

## Execution and acceptance

One native astra_flash_builder owns src/budget review/summary/CLI/Gold persistence
paths, additive Gold migrations, related synthetic tests, and focused docs.
Astra owns this plan, review, Git commits, GitHub progress, draft PR and CI.
Worker cannot commit: capture exact sequential red/green patches and evidence
for Astra to commit in order, retaining the tested intermediate states.
Do not edit .github/workflows, credentials, tool gates, or unrelated work.

Run ruff lint/format check, ty and complexipy for each stage; full pytest at
completion. Astra reviews specification and quality/security together, then
integrates. ship-issue's independent closing review follows the draft PR;
findings go to the user for triage. Routing configuration is static-ready;
runtime provider verification remains outstanding.

## Result and validation

Astra accepted the corrected patch after specification and quality review.
The initial proposal to retain missing decision targets was rejected because
it conflicted with the accepted classification contract; classification code
and its tests are unchanged. New behavior tests use the agreed CLI seam.

The final sequence contains two red/green pairs: published Gold review listing
(`0e7eb37` / `6f828a3`) and omission of an empty targets field for a wholly
missing decision target (`8a3969f` / `78379cd`). Filtering, absent Gold,
publication retention races, and privacy already passed against the core
implementation and were retained as regression coverage, not claimed as reds.
The builder captured intermediate states without Git writes; Astra integrated
the checked states as commits after acceptance. Local artifacts preserve the
individual assertion failures and per-state quality checks.

Full suite: 759 passed, 1 xfailed, 398 subtests passed. Ruff lint and format,
ty, and complexipy passed for all captured states and the final workspace.
Independent closing review and CI remain required before shipping.

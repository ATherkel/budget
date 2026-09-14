# Kimball learning in the household warehouse

Research date: 2026-09-14. Resolves the investigation in
[Connect Kimball learning to the warehouse design](https://github.com/ATherkel/budget/issues/3).
This is research evidence and proposed exercises, not an approved dimensional design.
No private financial imports were inspected or included.
Evidence is limited to public official material; this is not a page-by-page reading
of the user's editions of the Toolkit trilogy.

## Finding and project context

Keep the accepted Bronze/Silver/Gold boundaries and use Kimball's modeling process
to design the business-facing warehouse within them. Medallion describes successive
stages of data refinement; Kimball supplies methods for deciding what a measurement
means and how users analyze it. Their compatibility is a project inference from the
primary descriptions, not a claim that the three layer names originate in Kimball.
[Databricks medallion architecture](https://docs.databricks.com/gcp/en/lakehouse/medallion),
[Kimball four-step design process](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/four-4-step-design-process/).

The local design reviewed at documentation commit `3a67141820af1943380cdd0d5b8fdb831552096d`
assigns immutable source retention to Bronze, validation and normalization to Silver,
and household meaning to Gold. Its proposed Gold transaction contract describes one
booked transaction on one account. It does not yet specify a dimensional storage
model or a balance fact. These are observations of the local documentation, which
was not copied into this research branch.

**Recommendation:** retain atomic business facts in Gold, with a consumer interface
that can hide the physical star schema. Treat the proposed transaction interface as
an input to the model decision, not proof that one flat transaction dataset satisfies
every reporting need. No database, cloud platform, or distributed processing engine
is selected by this research.

## Evidence that should guide the decisions

### Business processes and grain come first

Kimball's sequence is business process, grain, dimensions, then facts; business
requirements and source realities constrain all four. A process is a measurable
operational activity, and monthly account snapshots are an explicit example. Grain
defines what one fact row represents before the keys and measures are chosen;
different grains belong in different fact tables.
[Four-step design](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/four-4-step-design-process/),
[Business processes](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/business-process/),
[Grain](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/grain/).

**Household implication:** distinguish recording account movements from observing
account balances. Before accepting category as a transaction dimension, decide whether
a purchase can be split into category allocations. One booked movement and one
allocation of that movement are different grains. This research leaves that choice
to the user and the Gold-model ticket. Source identity and duplicate handling also
remain source/domain questions; Kimball's grain declaration does not supply missing
bank identifiers.

### Choose facts by the question they answer

Transaction facts describe measurement events at particular times. Periodic snapshots
describe standard reporting intervals and typically include rows even without activity.
Accumulating snapshots describe processes with a beginning, predictable milestones,
and an end, updating the row as that process progresses.
[Transaction facts](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/transaction-fact-table/),
[Periodic snapshots](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/periodic-snapshot-fact-table/),
[Accumulating snapshots](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/accumulating-snapshot-fact-table/).

**Household recommendation:** investigate transaction facts for booked movements and
separate balance observations or periodic balance snapshots for account reporting.
Select daily versus monthly snapshots only after defining coverage, cutoff, and
reconciliation requirements. Do not infer a known zero balance from no transactions.
There is no established need for an accumulating snapshot in this release; studying
the pattern need not create a bill-processing feature.

Balances are commonly semi-additive: they can be summed across some dimensions but
not through time. Ratios should usually be calculated from aggregated additive
components, rather than summed as ratios.
[Additive, semi-additive, and non-additive facts](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/additive-semi-additive-non-additive-fact/).

**Synthetic exercise:** account A closes January at DKK 1,000 and February at
DKK 1,200. Summing these gives DKK 2,200, not February's balance. If account B closes
February at DKK 300, the two included accounts total DKK 1,500 at that same cutoff.
For a complete period with known opening balance, test closing balance against opening
balance plus signed movements. Whether the evidence establishes a complete period is
a separate household decision. Transfers stay relevant to account balances even when
excluded from household income and expense measures.

### Conformance makes expansion coherent

Conformed dimensions share consistent attributes and value domains across facts,
allowing separately aggregated results to align. Kimball's multipass approach aggregates
each fact separately before combining on common dimension attributes, avoiding
uncontrolled fact-to-fact joins.
[Conformed dimensions](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/conformed-dimension/),
[Multipass SQL](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/multipass-sql/).

**Recommendation:** sketch a small bus matrix: candidate processes as rows and shared
calendar, account, currency, and category concepts as columns. Mark dimensions only
where their meaning actually applies. Use later budget comparison as a paper exercise
in conformance, without adding budgets to this release. A future monthly category
budget joined directly to every transaction can multiply the budget amount; compare
aggregated actuals and budget at a compatible reporting grain instead.

### Historical interpretation needs an explicit policy

Type 1 overwrites dimension attributes; Type 2 adds a new dimension version with a
new surrogate key and effective/expiration information so facts can retain the relevant
version. These provide different reporting semantics.
[Type 1](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/type-1/),
[Type 2](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/type-2/).

**Household implication:** correcting a merchant typo, moving a category in a hierarchy,
and deliberately reclassifying old purchases are different intentions. Decide which
attributes require current interpretation and which need historically effective values.
Type 2 dimension history alone does not preserve every transaction classification
assignment or reproduce what a report displayed before a rule change. The history
ticket must separately settle rule/manual-input versions, transformation versions,
publication selection, and whether prior report outputs must be reproducible.

### ETL quality includes evidence and recovery

Kimball's ETL framework covers extraction, cleaning/conforming, delivery, and management.
It includes profiling, quality violations, error tracking, audit metadata, dimension
keys, fact construction, late arrivals, lineage, logic/metadata version control,
backup, and restart. It emphasizes making cleaning assumptions visible and considering
the architecture appropriate to the requirements.
[Subsystems of ETL Revisited](https://www.kimballgroup.com/2007/10/subsystems-of-etl-revisited/).

**Recommendation:** use that framework as a review checklist, not a requirement for
34 independently deployed services. In this project, exercise source profiling with
synthetic CSV fixtures; preserve rejected-row reasons and provenance; trace a dashboard
measure back to contributing facts; and rehearse a failed import followed by a safe
restart. Reproducibility requires retained manual inputs and logic as well as retained
bank exports. Make incomplete coverage and unresolved classification available to
report consumers through the chosen contract.

## How to learn through delivery

Kimball's Lifecycle emphasizes business value, dimensional delivery, manageable
increments, and business acceptance. This supports learning while completing useful
reporting slices rather than building every possible warehouse technique in advance.
[Kimball DW/BI Lifecycle](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dw-bi-lifecycle-method/).

The following sequence is a **proposed learning aid**, not an implementation backlog
or a prescribed chapter order. The user should align reading with their book editions.

| Learning checkpoint | Concrete exercise | Evidence to carry into a decision |
| --- | --- | --- |
| Requirements and lifecycle | State household questions and define trustworthy answers. | Agreed measures, coverage, acceptance examples. |
| Dimensional modeling | Declare candidate grains; sketch a bus matrix and facts/dimensions. | Explain transaction versus allocation grain and balance additivity. |
| ETL design | Trace synthetic exports through validation, identity, and classification. | Explain rejects, duplicates, lineage, and restart behavior. |
| History | Apply a typo correction and a deliberate historical reclassification. | State which old reports should change and why. |
| Incremental delivery | Review one useful report end to end, then add a second synthetic source. | Same report semantics despite different source formats. |

## Decisions deliberately left open

- Detailed account membership and exclusion policies within the agreed whole-household
  scope; refund/adjustment meaning, transfer evidence, and coverage.
- Transaction versus allocation grain; balance representation, cutoff, and cadence.
- Exact facts, dimensions, keys, history policies, and physical/consumer contracts.
- Reproducible report semantics and the active published version selection rule.
- Storage, deployment, recovery commands, and which reading exercises become code.

The research resolves the compatibility and learning question: the accepted layers can
host a practical Kimball exercise. It does not resolve these human modeling decisions.

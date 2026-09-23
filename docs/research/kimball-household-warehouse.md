# How Kimball fits this budget project

Research for [#3](https://github.com/ATherkel/budget/issues/3), originally written 2026-09-14; simplified and updated against `main` on 2026-09-19. Sources are public official material, not the full paid books. No private imports were used in this review.

**Kimball helps us organize reporting data. Bronze/Silver/Gold describes how we prepare that data. They fit together.** This compatibility is our design judgment based on the two approaches. [Medallion layers](https://docs.databricks.com/gcp/en/lakehouse/medallion), [Kimball's design process](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/four-4-step-design-process/).

| Layer | Job in this project |
| --- | --- |
| Bronze | Keep the original bank payload and import metadata |
| Silver | Validate records and identify which records represent the same transaction |
| Gold | Organize household facts for reporting, including balance checks and coverage |

## Start with what one row means

Kimball calls this the **grain**. Decide it before choosing columns. A **fact** records an event or measurement; a **dimension** describes it, such as its account, date, or category. Different grains belong in separate fact tables. [Grain](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/grain/).

The original research left the household model open. [ADR-007](https://github.com/ATherkel/budget/blob/main/docs/decisions/ADR-007-dimensional-gold-model.md) and [ADR-008](https://github.com/ATherkel/budget/blob/main/docs/decisions/ADR-008-category-allocation-grain.md) have since accepted:

| Gold record | One row means | Example |
| --- | --- | --- |
| Transaction | One booked movement on one account | A DKK 300 supermarket payment |
| Category allocation | One category assignment for a transaction | All DKK 300 assigned to groceries |
| Monthly balance snapshot | One account in one reporting month | The account's February closing balance and coverage status |

The first release gives each classified transaction one allocation for its whole amount. Splitting a payment across categories is deferred. The separate allocation table prepares for that future feature.

## Three mistakes this model helps prevent

**Adding balances across months.** If January ends at DKK 1,000 and February at DKK 1,200, February's balance is DKK 1,200. Adding them gives a meaningless DKK 2,200. Balances can be added across included accounts at the same cutoff and in the same currency. Kimball calls this *semi-additive*. [Additivity](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/additive-semi-additive-non-additive-fact/).

**Treating no transactions as a known zero.** A quiet month may retain the previous balance; missing evidence may mean the balance is unknown. Monthly records must carry coverage so reports can tell these cases apart. ADR-007 assigns that work to Gold.

**Multiplying totals when joining tables.** A monthly grocery budget joined to ten grocery purchases appears ten times. First total purchases by month and category, then compare that total with the monthly budget. Shared definitions of account, date, and category make this possible. [Multipass SQL](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/multipass-sql/).

## History means two different things

**Type 1** updates a description in place. **Type 2** keeps dated versions. The accepted first release uses Type 1: current category descriptions and grouping apply when reports are rebuilt. [Type 1](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/type-1/), [Type 2](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/type-2/).

Neither category-name history nor bank exports alone can reproduce an old report. Its classification decisions and the data version it used matter too. [#8](https://github.com/ATherkel/budget/issues/8) must define how complete Gold publications are retained and selected. [#10](https://github.com/ATherkel/budget/issues/10) covers recovery inputs and workflows.

## Learn through three small exercises

1. Trace one synthetic payment from its source record through Silver to a Gold transaction and category allocation.
2. Compare a quiet month with a month missing an export. Explain why their coverage differs.
3. Reclassify a purchase and compare a rebuilt report with a retained earlier publication. State which result each report should show.

The layer boundaries and three Gold grains are already decided. Publication/history and operating workflows remain follow-up work. This research adds no database choice or implementation requirement beyond those accepted decisions.

🤖 Generated with Codex (GPT-6)

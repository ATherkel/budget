## Dashboard specification and release split — 28 September 2026

The prototype discussion is now organized into the modular specification #100
and its delivery tickets. The maintainer confirmed read-only monthly budget
comparison for the first release, using household-scoped TOML inputs with plans
preserved by Publication. Account-specific budgets are guaranteed future scope;
the contract must support that extension without implementing it now.

The maintainer explicitly moved fixed/other expense reporting and planned
rådighedsbeløb to **after** the first usable release (#99 design, #110
implementation). Earmarking and selected-category carry-forward are also later
(#112). Neither follow-up blocks first-release dashboard acceptance (#111).

The report/context contract #101 and budget contract #102 feed #12; production
implementation remains gated by accepted contracts and ordinary TDD. The #11
timeline records the full decisions. This updates the earlier blanket budget
exclusion without changing the other exclusions or prematurely closing the map.

🤖 Generated with Codex (GPT-6 Astra)

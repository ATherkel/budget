## Prototype feedback: elapsed-month marker — 27 September 2026

The maintainer requested a marker on spending progress bars to show how far
the current month has progressed, using 14 September as an example. He
explicitly accepts the uncertainty caused by uneven spending and delayed
transactions, especially around vacations.

Implemented locally in Mod budget: a thin marker and a shared date/fraction
legend. The 14 September position is 14/30 (about 47%); the synthetic fixture's
fixed 15 September date shows 50%. The marker represents calendar time, not a
forecast or an expected-spending target. It does not move with the latest
transaction/import date.

The ordinary amount bars compare category sizes, so they do not get a marker
on an incompatible scale. Carry-forward reserves such as Ferie span multiple
months and are also excluded. Closed months and zero-budget rows have no
marker. Whether Mod budget should also appear in Simple remains a question
for the maintainer; current placement is Advanced / Mod budget.

JavaScript syntax and eight explicit calendar cases passed. The marker was
also inspected in the running in-app browser. No new usability verdict or
production budget scope is implied; #11 remains open. Work remains local on
codex/prototype-11-round-2.

🤖 Generated with Codex (GPT-6 Astra)

# Category Change Log

Gold's category dimension is Type 1: renaming a category, or moving it to
another group, restates every report ever produced
([ADR-007](../decisions/ADR-007-dimensional-gold-model.md)). That is a
deliberate trade, and this file is what keeps it safe. A household decision
made on last March's numbers can still be understood, because this log says
what the categories meant in March even though today's reports no longer show
it.

Two rules make the log sufficient:

- A `category_id` or `group_id` is **immutable and never reused**. Retiring a
  category deactivates it; the key is never repointed at a different meaning
  (`gold-contract.md`, invariant 1). Without that rule no log and no archive
  can recover the past, because the same key would mean two things.
- Every rename, regrouping, retirement, and direction change is appended here
  on the day it is made, with the reason. An entry is never edited or removed.

Reproducing a report exactly as it was read is a different matter, and needs
the publication it was built from; that is
[issue #8](https://github.com/ATherkel/budget/issues/8).

## Log

The household taxonomy does not exist yet — it arrives with
[issue #7](https://github.com/ATherkel/budget/issues/7) — so there is nothing
to record. The first entry is the taxonomy's own creation.

| Date | Key | Change | Before | After | Why |
| --- | --- | --- | --- | --- | --- |

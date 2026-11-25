# PR line caps

The project does not cap the number of changed lines in a pull request. A
reviewer or agent that finds a PR too big splits it by concern instead.

## Why this is out of scope

A line cap measures size, not reviewability. A mechanical rename can run to
thousands of lines and review in minutes, while a 50-line change that mixes two
concerns takes longer. A cap also pushes authors to cut a change at the limit
and not at a natural seam, which leaves PRs that only make sense together.

"One concern per PR" is the rule instead, stated in
[Presentation Agent Brief](../docs/agents/ui-agent.md#structure-rules).

## Prior requests

- #584: "Guardrail docs and rejected caps"

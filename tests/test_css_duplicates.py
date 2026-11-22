# Copyright 2026 Therkel
"""The duplicate CSS check names the existing rule to reuse."""

from tests.css_duplicates import find_duplicates

CARD_AND_PANEL = """\
.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}

.panel {
  color: var(--ink);
  margin: 0;
  padding: 1rem;
  border: 1px solid var(--line);
}
"""


def test_a_rule_sharing_three_declarations_names_the_rule_to_reuse() -> None:
    assert find_duplicates(CARD_AND_PANEL) == [
        "`.panel` shares 3 declarations with `.card` (line 1); reuse `.card`"
    ]


def test_rules_sharing_two_declarations_pass() -> None:
    css = """\
.card {
  padding: 1rem;
  color: var(--ink);
  border: 1px solid var(--line);
}

.panel {
  padding: 1rem;
  color: var(--ink);
  border: 2px solid var(--line);
}
"""

    assert find_duplicates(css) == []


def test_an_allowlisted_duplicate_passes() -> None:
    assert find_duplicates(CARD_AND_PANEL, allowlist=[(".panel", ".card")]) == []

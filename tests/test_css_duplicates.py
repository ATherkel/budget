# Copyright 2026 Therkel
"""The duplicate CSS check names the existing rule to reuse."""

from tests.css_duplicates import find_duplicates


def test_a_rule_sharing_three_declarations_names_the_rule_to_reuse() -> None:
    css = """\
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

    assert find_duplicates(css) == [
        "`.panel` shares 3 declarations with `.card` (line 1); reuse `.card`"
    ]

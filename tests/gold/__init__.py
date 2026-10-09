# Copyright 2026 Therkel
"""Gold contract tests."""

import pytest

# The shared contract tests are not in a `test_*` module. Pytest still runs them
# through each implementation's test class, but only this makes a failing assert
# show what differed instead of a bare AssertionError.
pytest.register_assert_rewrite("tests.gold.contract")

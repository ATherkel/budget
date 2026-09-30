# Copyright 2026 Therkel
"""The source-parser registry: which format IDs are accepted input.

The rules of a declared format belong to that format's own suite
(`tests/bronze/parsers/test_danske_csv_v1.py`). This file observes only
selection, and specifically how an ID that no parser declares is refused.
"""

import unittest

import pytest

from budget.bronze.parsers import registry


class SourceParserRegistryTests(unittest.TestCase):
    def test_an_undeclared_format_is_refused_by_name(self) -> None:
        with pytest.raises(ValueError, match="Unsupported source format") as refusal:
            registry.source_parser("nordea-csv-v1")

        assert "nordea-csv-v1" in str(refusal.value)


if __name__ == "__main__":
    unittest.main()

# Copyright 2026 Therkel
"""The source-parser registry: which format IDs are accepted input.

The rules of a declared format belong to that format's own suite
(`tests/bronze/parsers/test_danske_csv_v1.py`). This file observes only
selection: the declared list, the parser each ID selects, and how an undeclared
ID is refused.
"""

import unittest

import pytest

from budget.bronze.parsers import registry


class SourceParserRegistryTests(unittest.TestCase):
    def test_the_registry_declares_only_formats_that_exist(self) -> None:
        # A format ID is a promise that a parser is implemented for it, so the
        # declared list is the whole set of accepted inputs.
        assert registry.source_formats() == ("danske-csv-v1",)

    def test_a_declared_format_selects_the_parser_that_names_it(self) -> None:
        for source_format in registry.source_formats():
            parser = registry.source_parser(source_format)

            assert parser.source_format == source_format

    def test_an_undeclared_format_is_refused_by_name(self) -> None:
        with pytest.raises(ValueError, match="Unsupported source format") as refusal:
            registry.source_parser("nordea-csv-v1")

        assert "nordea-csv-v1" in str(refusal.value)


if __name__ == "__main__":
    unittest.main()

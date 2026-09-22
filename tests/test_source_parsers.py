"""The source-parser seam: one declared format ID selects one parser.

These tests observe the extension contract the store itself depends on, and
they use only the synthetic payloads the Bronze tests already use.
"""

from datetime import date
import unittest

from budget.bronze.parsers import registry


ONE_RECORD_PAYLOAD = (
    b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
    b'"Saldo","Status","Afstemt"\r\n'
    b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
    b'"-45,00","955,00","Udf\xf8rt","Nej"'
)


class SourceParserRegistryTests(unittest.TestCase):
    def test_the_registry_declares_only_formats_that_exist(self):
        # A format ID is a promise that a parser is implemented for it, so the
        # declared list is the whole set of accepted inputs.
        self.assertEqual(registry.source_formats(), ("danske-csv-v1",))

    def test_an_undeclared_format_is_refused_by_name(self):
        with self.assertRaises(ValueError) as refusal:
            registry.source_parser("nordea-csv-v1")
        self.assertIn("nordea-csv-v1", str(refusal.exception))

    def test_a_declared_parser_presents_fields_exactly_as_decoded(self):
        parser = registry.source_parser("danske-csv-v1")
        result = parser.parse(ONE_RECORD_PAYLOAD)

        self.assertIsNone(result.failure_reason)
        self.assertEqual(
            [dict(record) for record in result.records],
            [
                {
                    "Dato": "12-09-2026",
                    "Kategori": " Mad ",
                    "Underkategori": " Dagligvarer ",
                    "Tekst": " Café",
                    "Beløb": "-45,00",
                    "Saldo": "955,00",
                    "Status": "Udført",
                    "Afstemt": "Nej",
                }
            ],
        )
        self.assertEqual(result.last_transaction_date, date(2026, 9, 12))

    def test_a_failure_verdict_offers_no_records_and_no_transaction_date(self):
        parser = registry.source_parser("danske-csv-v1")
        result = parser.parse(ONE_RECORD_PAYLOAD[:-1] + b"\x81")

        self.assertEqual(result.records, ())
        self.assertIsNone(result.last_transaction_date)
        self.assertTrue(result.failure_reason)
        self.assertNotIn("Dato", result.failure_reason)


if __name__ == "__main__":
    unittest.main()

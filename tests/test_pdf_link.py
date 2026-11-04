"""Tests for PDF documentation link detection."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import find_pdf_url


class TestFindPdfUrl(unittest.TestCase):
    def test_plain_pdf_url(self):
        url = "https://estadisticas.bcrp.gob.pe/estadisticas/series/documentos/bcrpdataapi.pdf"
        self.assertEqual(find_pdf_url(url), url)

    def test_url_inside_text(self):
        text = "Ver documentación: https://example.com/docs/metodologia.pdf para más detalle."
        self.assertEqual(find_pdf_url(text), "https://example.com/docs/metodologia.pdf")

    def test_uppercase_extension(self):
        self.assertEqual(
            find_pdf_url("https://example.com/X/Y.PDF"), "https://example.com/X/Y.PDF"
        )

    def test_pdf_with_query_string(self):
        self.assertEqual(
            find_pdf_url("https://example.com/file.pdf?download=1"),
            "https://example.com/file.pdf?download=1",
        )

    def test_no_pdf_returns_none(self):
        self.assertIsNone(find_pdf_url("https://example.com/page.html"))
        self.assertIsNone(find_pdf_url("sin enlaces"))
        self.assertIsNone(find_pdf_url(""))
        self.assertIsNone(find_pdf_url(None))

    def test_first_pdf_wins(self):
        text = "https://a.com/one.pdf y https://b.com/two.pdf"
        self.assertEqual(find_pdf_url(text), "https://a.com/one.pdf")


if __name__ == "__main__":
    unittest.main(verbosity=2)

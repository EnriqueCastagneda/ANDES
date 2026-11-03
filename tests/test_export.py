"""
Test suite for BCRP Flet App - Phase 3: CSV export
"""
import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import re

from app import OUTPUT_DIR, METADATA_PATH, KNOWN_CODE_COL


class TestCSVExport(unittest.TestCase):
    """Tests for CSV export functionality."""

    def setUp(self):
        """Create a temporary output directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_output_dir = OUTPUT_DIR

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_csv_export_creates_file(self):
        """Test that CSV export creates a file."""
        df = pd.DataFrame({"fecha": ["Ene.2020", "Feb.2020"], "PN00001MM": [231956.42, 234889.06]})
        filepath = os.path.join(self.temp_dir, "test.csv")
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        self.assertTrue(os.path.exists(filepath))
        self.assertGreater(os.path.getsize(filepath), 0)

    def test_csv_export_utf8_bom(self):
        """Test that CSV export uses UTF-8 with BOM."""
        df = pd.DataFrame({"fecha": ["Ene.2020"], "PN00001MM": [231956.42]})
        filepath = os.path.join(self.temp_dir, "test.csv")
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        with open(filepath, "rb") as f:
            content = f.read()
        # UTF-8 BOM is EF BB BF
        self.assertEqual(content[:3], b"\xef\xbb\xbf", "CSV should start with UTF-8 BOM")

    def test_csv_export_filename_format(self):
        """Test that exported filename follows the expected format."""
        code = "PN00001MM"
        start = "2020-1"
        end = "2020-3"
        safe_code = re.sub(r"[^\w\-_.]", "_", code.upper())
        filename = f"bcrp_serie_{safe_code}_{start}_to_{end}.csv"
        self.assertEqual(filename, "bcrp_serie_PN00001MM_2020-1_to_2020-3.csv")

    def test_csv_export_filename_sanitizes_code(self):
        """Test that filename sanitizes special characters in code."""
        code = "PN/00001:MM"
        safe_code = re.sub(r"[^\w\-_.]", "_", code.upper())
        filename = f"bcrp_serie_{safe_code}_2020-1_to_2020-3.csv"
        self.assertNotIn("/", filename)
        self.assertNotIn(":", filename)

    def test_csv_export_has_correct_columns(self):
        """Test that exported CSV has the correct columns."""
        df = pd.DataFrame({"fecha": ["Ene.2020"], "PN00001MM": [231956.42]})
        filepath = os.path.join(self.temp_dir, "test.csv")
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        df_read = pd.read_csv(filepath, encoding="utf-8-sig")
        self.assertIn("fecha", df_read.columns)
        self.assertIn("PN00001MM", df_read.columns)

    def test_csv_export_no_index_column(self):
        """Test that exported CSV does not include an index column."""
        df = pd.DataFrame({"fecha": ["Ene.2020"], "PN00001MM": [231956.42]})
        filepath = os.path.join(self.temp_dir, "test.csv")
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        df_read = pd.read_csv(filepath, encoding="utf-8-sig")
        self.assertNotIn("Unnamed: 0", df_read.columns)


class TestMultiFormatExport(unittest.TestCase):
    """Tests for the format selector (CSV/JSON/XLS/XML/TXT/HTML)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.df = pd.DataFrame({"fecha": ["Ene.2024", "Feb.2024"], "PN00001MM": [1.5, 2.5]})

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _export(self, fmt):
        from app import export_series
        return export_series(self.df, "PN00001MM", "2024-01-01", "2024-03-01", fmt, out_dir=self.temp_dir)

    def test_csv(self):
        path = self._export("csv")
        self.assertTrue(path.endswith(".csv"))
        df = pd.read_csv(path, encoding="utf-8-sig")
        self.assertEqual(list(df.columns), ["fecha", "PN00001MM"])

    def test_json(self):
        import json
        path = self._export("json")
        self.assertTrue(path.endswith(".json"))
        with open(path, encoding="utf-8") as f:
            records = json.load(f)
        self.assertEqual(records[0]["fecha"], "Ene.2024")
        self.assertEqual(len(records), 2)

    def test_txt_is_tab_separated(self):
        path = self._export("txt")
        self.assertTrue(path.endswith(".txt"))
        with open(path, encoding="utf-8-sig") as f:
            first = f.readline().rstrip("\n")
        self.assertIn("\t", first)

    def test_xml(self):
        import xml.etree.ElementTree as ET
        path = self._export("xml")
        self.assertTrue(path.endswith(".xml"))
        root = ET.parse(path).getroot()
        self.assertEqual(root.tag, "serie")
        self.assertEqual(len(root.findall("periodo")), 2)

    def test_html(self):
        path = self._export("html")
        self.assertTrue(path.endswith(".html"))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("<!DOCTYPE html>", text)
        self.assertIn("PN00001MM", text)
        self.assertIn("<table", text)

    def test_xls_is_native_only(self):
        from app import export_series
        with self.assertRaises(ValueError):
            export_series(self.df, "PN00001MM", "2024-01-01", "2024-03-01", "xls", out_dir=self.temp_dir)

    def test_unknown_format_raises(self):
        from app import export_series
        with self.assertRaises(ValueError):
            export_series(self.df, "PN00001MM", "2024-01-01", "2024-03-01", "pdf", out_dir=self.temp_dir)


if __name__ == "__main__":
    unittest.main(verbosity=2)
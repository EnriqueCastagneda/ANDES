"""
Test suite for BCRP Downloader - Phase 2: API connection and data extraction
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pandas as pd

from app import METADATA_URL, KNOWN_CODE_COL, KNOWN_NAME_COL, _http_get_json

API_BASE = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"


def _fetch(url, timeout=30):
    """Fetch JSON with retries, skipping tests on persistent CDN blocks."""
    try:
        return _http_get_json(url, max_retries=4, timeout=timeout)
    except RuntimeError as e:
        raise unittest.SkipTest(f"BCRP API unreachable after retries: {e}")


class TestAPIConnection(unittest.TestCase):
    """Tests for BCRP API connection and data extraction."""

    def test_metadata_endpoint_reachable(self):
        """Test that the metadata endpoint is reachable."""
        resp = requests.get(METADATA_URL, timeout=60)
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.content), 1000000)

    def test_series_api_returns_json(self):
        """Test that the series API returns valid JSON."""
        url = f"{API_BASE}/PN00001MM/json/2020-1/2020-3/esp"
        data = _fetch(url)
        self.assertIn("config", data)
        self.assertIn("periods", data)

    def test_series_api_has_periods(self):
        """Test that the API returns periods for a valid range."""
        url = f"{API_BASE}/PN00001MM/json/2020-1/2020-3/esp"
        data = _fetch(url)
        periods = data.get("periods", [])
        self.assertGreater(len(periods), 0)

    def test_period_structure(self):
        """Test that each period has name and values."""
        url = f"{API_BASE}/PN00001MM/json/2020-1/2020-3/esp"
        data = _fetch(url)
        for period in data.get("periods", []):
            self.assertIn("name", period)
            self.assertIn("values", period)
            self.assertIsInstance(period["values"], list)
            self.assertGreater(len(period["values"]), 0)

    def test_period_values_are_numeric(self):
        """Test that period values are numeric strings."""
        url = f"{API_BASE}/PN00001MM/json/2020-1/2020-3/esp"
        data = _fetch(url)
        for period in data.get("periods", []):
            val = period["values"][0]
            try:
                float(val)
            except (TypeError, ValueError):
                self.fail(f"Value {val} is not numeric")

    def test_invalid_code_returns_empty(self):
        """Test that an invalid code returns empty periods."""
        url = f"{API_BASE}/INVALIDCODE/json/2020-1/2020-3/esp"
        data = _fetch(url)
        periods = data.get("periods", [])
        self.assertEqual(len(periods), 0)


class TestDataExtraction(unittest.TestCase):
    """Tests for data extraction and transformation."""

    def test_json_to_dataframe(self):
        """Test that JSON response can be transformed to a DataFrame."""
        url = f"{API_BASE}/PN00001MM/json/2020-1/2020-3/esp"
        data = _fetch(url)
        periods = data.get("periods", [])
        rows = [{"fecha": p.get("name"), "PN00001MM": p.get("values", [None])[0]} for p in periods]
        df = pd.DataFrame(rows)
        self.assertEqual(len(df), len(periods))
        self.assertIn("fecha", df.columns)
        self.assertIn("PN00001MM", df.columns)

    def test_dataframe_has_no_nulls_in_dates(self):
        """Test that the DataFrame has no null dates."""
        url = f"{API_BASE}/PN00001MM/json/2020-1/2020-3/esp"
        data = _fetch(url)
        periods = data.get("periods", [])
        rows = [{"fecha": p.get("name"), "PN00001MM": p.get("values", [None])[0]} for p in periods]
        df = pd.DataFrame(rows)
        self.assertFalse(df["fecha"].isnull().any())

    def test_dataframe_values_are_numeric(self):
        """Test that DataFrame values are numeric."""
        url = f"{API_BASE}/PN00001MM/json/2020-1/2020-3/esp"
        data = _fetch(url)
        periods = data.get("periods", [])
        rows = [{"fecha": p.get("name"), "PN00001MM": p.get("values", [None])[0]} for p in periods]
        df = pd.DataFrame(rows)
        numeric = pd.to_numeric(df["PN00001MM"], errors="coerce")
        self.assertFalse(numeric.isnull().any())


if __name__ == "__main__":
    unittest.main(verbosity=2)
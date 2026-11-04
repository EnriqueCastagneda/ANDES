"""
Test suite for BCRP Downloader - Phase 1: Metadata loading
"""
import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    download_metadata,
    load_metadata,
    METADATA_URL,
    METADATA_PATH,
    DATA_DIR,
    KNOWN_CODE_COL,
    KNOWN_NAME_COL,
)


class TestMetadataLoading(unittest.TestCase):
    """Tests for metadata download and loading."""

    def setUp(self):
        """Backup existing metadata file."""
        self.backup = None
        if os.path.exists(METADATA_PATH):
            self.backup = METADATA_PATH + ".backup"
            shutil.copy2(METADATA_PATH, self.backup)

    def tearDown(self):
        """Restore metadata file."""
        if self.backup and os.path.exists(self.backup):
            shutil.move(self.backup, METADATA_PATH)
        elif os.path.exists(METADATA_PATH):
            os.remove(METADATA_PATH)

    def test_metadata_url_is_valid(self):
        """Test that the metadata URL is a valid HTTPS URL."""
        self.assertTrue(METADATA_URL.startswith("https://"))
        self.assertIn("bcrp.gob.pe", METADATA_URL)

    def test_metadata_file_downloads_successfully(self):
        """Test that metadata can be downloaded from the official URL."""
        path = download_metadata()
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 1000000)  # > 1MB

    def test_metadata_loads_as_dataframe(self):
        """Test that metadata loads as a valid DataFrame."""
        df = load_metadata()
        self.assertIsNotNone(df)
        self.assertGreater(len(df), 10000)  # Should have 17,000+ series
        self.assertGreaterEqual(len(df.columns), 10)  # Should have 10+ columns

    def test_metadata_has_required_columns(self):
        """Test that metadata has the required columns."""
        df = load_metadata()
        self.assertIn(KNOWN_CODE_COL, df.columns)
        self.assertIn(KNOWN_NAME_COL, df.columns)

    def test_metadata_codes_are_unique(self):
        """Test that series codes are unique."""
        df = load_metadata()
        codes = df[KNOWN_CODE_COL]
        self.assertEqual(len(codes), len(codes.unique()), "Series codes must be unique")

    def test_metadata_codes_are_normalized_lowercase(self):
        """Test that codes are normalized to lowercase."""
        df = load_metadata()
        codes = df[KNOWN_CODE_COL]
        for code in codes:
            self.assertEqual(code, code.lower(), f"Code {code} should be lowercase")


if __name__ == "__main__":
    unittest.main(verbosity=2)
"""
Test suite for BCRP Flet App - Phase 4: HTTP retry and block detection
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import _is_blocked_response, _http_get_json


class TestIsBlockedResponse(unittest.TestCase):
    """Tests for CDN block page detection."""

    def test_detects_html_content_type(self):
        """Test that HTML content-type with an HTML body is detected as blocked."""
        resp = MagicMock()
        resp.headers = {"Content-Type": "text/html; charset=UTF-8"}
        resp.text = '<html><body>blocked by CDN</body></html>'
        self.assertTrue(_is_blocked_response(resp))

    def test_allows_json_body_with_html_content_type(self):
        """BCRP serves valid JSON with a misleading text/html content type."""
        resp = MagicMock()
        resp.headers = {"Content-Type": "text/html; charset=UTF-8"}
        resp.text = '{"config": {"series": []}, "periods": [{"name": "Ene.2024", "values": ["1"]}]}'
        resp.json.return_value = {"config": {"series": []}, "periods": [{"name": "Ene.2024", "values": ["1"]}]}
        self.assertFalse(_is_blocked_response(resp))

    def test_allows_json_content_type(self):
        """Test that JSON content-type is allowed."""
        resp = MagicMock()
        resp.headers = {"Content-Type": "application/json"}
        resp.text = '{"periods": []}'
        self.assertFalse(_is_blocked_response(resp))

    def test_detects_doctype_html(self):
        """Test that HTML body with doctype is detected as blocked."""
        resp = MagicMock()
        resp.headers = {"Content-Type": "text/plain"}
        resp.text = '<!DOCTYPE html><html><head></head><body></body></html>'
        self.assertTrue(_is_blocked_response(resp))

    def test_detects_html_tag(self):
        """Test that HTML body with <html> tag is detected as blocked."""
        resp = MagicMock()
        resp.headers = {"Content-Type": "text/plain"}
        resp.text = '<html><body>blocked</body></html>'
        self.assertTrue(_is_blocked_response(resp))

    def test_allows_json_body(self):
        """Test that JSON body is allowed."""
        resp = MagicMock()
        resp.headers = {"Content-Type": "text/plain"}
        resp.text = '{"config": {}, "periods": []}'
        self.assertFalse(_is_blocked_response(resp))


class TestHttpGetJson(unittest.TestCase):
    """Tests for HTTP GET with retries."""

    @patch("app.requests.get")
    def test_succeeds_on_first_attempt(self, mock_get):
        """Test that a successful request returns data immediately."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.text = '{"periods": [{"name": "Ene.2020", "values": ["100"]}]}'
        mock_resp.json.return_value = {"periods": [{"name": "Ene.2020", "values": ["100"]}]}
        mock_get.return_value = mock_resp

        result = _http_get_json("https://example.com/api", max_retries=3, timeout=30)
        self.assertEqual(result["periods"][0]["name"], "Ene.2020")
        self.assertEqual(mock_get.call_count, 1)

    @patch("app.requests.get")
    def test_retries_on_blocked_response(self, mock_get):
        """Test that blocked responses trigger retries."""
        blocked_resp = MagicMock()
        blocked_resp.status_code = 200
        blocked_resp.headers = {"Content-Type": "text/html"}
        blocked_resp.text = '<html><body>blocked</body></html>'

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.headers = {"Content-Type": "application/json"}
        success_resp.text = '{"periods": []}'
        success_resp.json.return_value = {"periods": []}

        mock_get.side_effect = [blocked_resp, blocked_resp, success_resp]

        result = _http_get_json("https://example.com/api", max_retries=3, timeout=30)
        self.assertEqual(result["periods"], [])
        self.assertEqual(mock_get.call_count, 3)

    @patch("app.requests.get")
    def test_raises_after_max_retries(self, mock_get):
        """Test that an exception is raised after max retries."""
        blocked_resp = MagicMock()
        blocked_resp.status_code = 200
        blocked_resp.headers = {"Content-Type": "text/html"}
        blocked_resp.text = '<html><body>blocked</body></html>'
        mock_get.return_value = blocked_resp

        with self.assertRaises(RuntimeError):
            _http_get_json("https://example.com/api", max_retries=2, timeout=30)
        self.assertEqual(mock_get.call_count, 2)

    @patch("app.requests.get")
    def test_retries_on_http_error(self, mock_get):
        """Test that HTTP errors trigger retries."""
        error_resp = MagicMock()
        error_resp.status_code = 503
        mock_get.return_value = error_resp

        with self.assertRaises(RuntimeError):
            _http_get_json("https://example.com/api", max_retries=2, timeout=30)
        self.assertEqual(mock_get.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
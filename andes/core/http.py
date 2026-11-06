"""HTTP helpers with retries and CDN block detection."""

from __future__ import annotations

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _is_blocked_response(resp):
    """Detect CDN/rate-limit blocks that return HTML instead of data.

    BCRP serves valid JSON with a misleading ``Content-Type: text/html``,
    so a body that parses as JSON is never treated as a block page.
    """
    body = resp.text.lstrip()
    if body.startswith("{") or body.startswith("["):
        try:
            resp.json()
            return False
        except ValueError:
            pass
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        return True
    head = body[:200]
    return head.startswith("<!DOCTYPE html>") or head.startswith("<html")


def _http_get_json(url, max_retries=3, timeout=30):
    """GET a URL with retries, skipping CDN block pages."""
    last_error = None
    for _attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code != 200:
                last_error = RuntimeError(f"HTTP {resp.status_code} for {url}")
                continue
            if _is_blocked_response(resp):
                last_error = RuntimeError(f"CDN block page returned for {url}")
                continue
            return resp.json()
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_error}")


def _http_get_bytes(url, max_retries=3, timeout=30):
    """GET raw bytes (e.g. a native XLS) with retries, skipping CDN blocks."""
    last_error = None
    for _attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code != 200:
                last_error = RuntimeError(f"HTTP {resp.status_code} for {url}")
                continue
            head = resp.content.lstrip()[:200]
            ctype = (resp.headers.get("Content-Type") or "").lower()
            is_html = head.startswith(b"<!DOCTYPE") or head.startswith(b"<html")
            if is_html and "html" in ctype:
                last_error = RuntimeError(f"CDN block page returned for {url}")
                continue
            return resp.content
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_error}")



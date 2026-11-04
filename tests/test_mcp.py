"""Tests for the MCP tool functions."""

from __future__ import annotations

import pandas as pd
import pytest

import bcrp_downloader.mcp.server as srv


def test_search_series_returns_dicts(sample_df, monkeypatch):
    monkeypatch.setattr(srv, "load_metadata", lambda: sample_df)
    results = srv.search_series("tipo de cambio")
    assert len(results) == 2
    assert results[0]["code"].startswith("PN")
    assert {"code", "name", "category", "frequency"} <= set(results[0])


def test_search_series_frequency_filter(sample_df, monkeypatch):
    monkeypatch.setattr(srv, "load_metadata", lambda: sample_df)
    results = srv.search_series("tipo de cambio", frequency="Mensual")
    assert all(r["frequency"] == "Mensual" for r in results)


def test_get_metadata_includes_pdf(sample_df, monkeypatch):
    monkeypatch.setattr(srv, "load_metadata", lambda: sample_df)
    meta = srv.get_metadata("PN00001MM")
    assert meta["code"] == "PN00001MM"
    assert meta["pdf_url"].endswith(".pdf")


def test_get_metadata_unknown(sample_df, monkeypatch):
    monkeypatch.setattr(srv, "load_metadata", lambda: sample_df)
    with pytest.raises(ValueError):
        srv.get_metadata("NOPE")


def test_download_series_returns_path(tmp_path, monkeypatch):
    frame = pd.DataFrame({"fecha": ["Ene.2024"], "PN00001MM": [1.5]})
    captured = {}

    def fake_export(df, code, start, end, fmt, out_dir=None):
        path = tmp_path / "out.csv"
        path.write_text("ok")
        captured["fmt"] = fmt
        return str(path)

    monkeypatch.setattr(srv, "download_series_data", lambda *a, **k: frame)
    monkeypatch.setattr(srv, "export_series", fake_export)
    result = srv.download_series("PN00001MM", "2024-1", "2024-2", "csv")
    assert result["rows"] == 1
    assert result["format"] == "csv"
    assert captured["fmt"] == "csv"


def test_server_instance_or_skip():
    if srv.server is None:
        pytest.skip("optional 'mcp' dependency not installed")
    assert srv.server is not None

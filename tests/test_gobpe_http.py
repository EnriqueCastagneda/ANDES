"""Descargas del adaptador Gob.pe sin red real."""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest
import requests
from openpyxl import Workbook

from andes.core.adapters import gobpe as gobpe_adapter


class _Response:
    """Respuesta falsa con la interfaz que usa ``_download``."""

    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:  # noqa: D401 - stub
        return None


def _stub_catalog(monkeypatch: pytest.MonkeyPatch, code: str, platform: str, url: str) -> None:
    memo = json.dumps({"kind": "gobpe", "url": url, "platform": platform}, ensure_ascii=False)
    monkeypatch.setattr(
        gobpe_adapter.catalog,
        "get",
        lambda requested: {"code": requested, "name": code, "memo": memo},
    )


def test_fetch_csv(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    adapter = gobpe_adapter.GobpeAdapter()
    monkeypatch.setattr(gobpe_adapter, "CACHE_DIR", str(tmp_path))
    calls: list[str] = []

    def fake_get(url: str, **kwargs) -> _Response:
        calls.append(url)
        return _Response(b"a,b\n1,2\n3,4\n")

    monkeypatch.setattr(gobpe_adapter.requests, "get", fake_get)
    _stub_catalog(monkeypatch, "GOBPE-X", "csv", "https://x.gob.pe/datos.csv")

    frame = adapter.fetch(["GOBPE-X"])

    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["a", "b"]
    assert len(frame) == 2
    assert len(calls) == 1


def test_fetch_excel(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    path = tmp_path / "tabla.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["a", "b"])
    sheet.append([1, 2])
    sheet.append([3, 4])
    workbook.save(path)

    adapter = gobpe_adapter.GobpeAdapter()
    monkeypatch.setattr(
        gobpe_adapter.GobpeAdapter,
        "_download",
        lambda self, url: (str(path), "xlsx"),
    )
    _stub_catalog(monkeypatch, "GOBPE-X", "excel", "https://x.gob.pe/datos.xlsx")

    frame = adapter.fetch(["GOBPE-X"])

    assert list(frame.columns) == ["a", "b"]
    assert len(frame) == 2


def test_fetch_json_api(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    adapter = gobpe_adapter.GobpeAdapter()
    monkeypatch.setattr(gobpe_adapter, "CACHE_DIR", str(tmp_path))
    payload = json.dumps({"records": [{"a": 1}, {"a": 2}]}).encode("utf-8")

    def fake_get(url: str, **kwargs) -> _Response:
        return _Response(payload)

    monkeypatch.setattr(gobpe_adapter.requests, "get", fake_get)
    _stub_catalog(
        monkeypatch,
        "GOBPE-X",
        "api",
        "https://x.gob.pe/api/3/action/package_search",
    )

    frame = adapter.fetch(["GOBPE-X"])

    assert len(frame) == 2
    assert list(frame.columns) == ["a"]


def test_fetch_non_tabular_web_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = gobpe_adapter.GobpeAdapter()
    calls: list[str] = []
    monkeypatch.setattr(
        gobpe_adapter.requests,
        "get",
        lambda url, **kwargs: calls.append(url),
    )
    _stub_catalog(monkeypatch, "GOBPE-X", "web", "https://x.gob.pe/datos/")

    frame = adapter.fetch(["GOBPE-X"])

    assert frame.empty
    assert calls == []


def test_download_uses_cache(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    adapter = gobpe_adapter.GobpeAdapter()
    monkeypatch.setattr(gobpe_adapter, "CACHE_DIR", str(tmp_path))
    calls: list[str] = []

    def fake_get(url: str, **kwargs) -> _Response:
        calls.append(url)
        return _Response(b"a,b\n1,2\n")

    monkeypatch.setattr(gobpe_adapter.requests, "get", fake_get)
    url = "https://x.gob.pe/datos.csv"

    first = adapter._download(url)
    second = adapter._download(url)

    assert first == second
    assert len(calls) == 1
    assert os.path.exists(first[0])


def test_fetch_http_error_returns_empty(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    adapter = gobpe_adapter.GobpeAdapter()
    monkeypatch.setattr(gobpe_adapter, "CACHE_DIR", str(tmp_path))

    def boom(url: str, **kwargs):
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(gobpe_adapter.requests, "get", boom)
    _stub_catalog(monkeypatch, "GOBPE-X", "csv", "https://x.gob.pe/datos.csv")

    assert adapter.fetch(["GOBPE-X"]).empty

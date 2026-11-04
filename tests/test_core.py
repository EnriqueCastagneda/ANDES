"""Unit and integration tests for the core backend."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import pytest

from bcrp_downloader.core import api, http
from bcrp_downloader.core.metadata import filter_metadata
from bcrp_downloader.gui.theme import resolve_theme


class TestFilters:
    def test_no_filters(self, sample_df):
        assert len(filter_metadata(sample_df, {})) == 3

    def test_code_substring(self, sample_df):
        assert len(filter_metadata(sample_df, {"codigo": "pn00001"})) == 1

    def test_name_case_insensitive(self, sample_df):
        assert len(filter_metadata(sample_df, {"nombre": "TIPO DE CAMBIO"})) == 2

    @pytest.mark.parametrize(
        ("key", "value", "expected"),
        [
            ("categoria", "Tipo de cambio real", 1),
            ("fuente", "INEI", 1),
            ("frecuencia", "Mensual", 2),
            ("grupo_publicacion", "Tipo de cambio", 2),
            ("area", "Estadísticas", 1),
            ("grupo_serie", "moneda", 2),
        ],
    )
    def test_exact_filters(self, sample_df, key, value, expected):
        assert len(filter_metadata(sample_df, {key: value})) == expected

    def test_date_range(self, sample_df):
        result = filter_metadata(
            sample_df, {"creacion_desde": "2022-01-01", "creacion_hasta": "2022-12-31"}
        )
        assert len(result) == 2

    def test_combined(self, sample_df):
        result = filter_metadata(
            sample_df, {"categoria": "Tipo de cambio nominal", "frecuencia": "Mensual"}
        )
        assert len(result) == 1

    def test_todas_ignored(self, sample_df):
        assert len(filter_metadata(sample_df, {"categoria": "Todas"})) == 3


class TestPdf:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("https://a.com/x.pdf", "https://a.com/x.pdf"),
            ("Ver: https://a.com/x.PDF fin", "https://a.com/x.PDF"),
            ("https://a.com/x.pdf?d=1", "https://a.com/x.pdf?d=1"),
            ("sin enlaces", None),
            ("", None),
        ],
    )
    def test_find_pdf_url(self, text, expected):
        assert api.find_pdf_url(text) == expected


class TestBlockDetection:
    def test_json_with_html_content_type_is_allowed(self):
        class R:
            headers = {"Content-Type": "text/html"}
            text = '{"periods": []}'

            def json(self):
                return {"periods": []}

        assert http._is_blocked_response(R()) is False

    def test_html_page_is_blocked(self):
        class R:
            headers = {"Content-Type": "text/html"}
            text = "<!DOCTYPE html><html></html>"

            def json(self):
                raise ValueError

        assert http._is_blocked_response(R()) is True


class TestHttpRetries:
    def test_succeeds_after_block(self, monkeypatch):
        calls = {"n": 0}

        class Resp:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            text = '{"periods": [{"name": "Ene.2024", "values": ["1"]}]}'

            def json(self):
                return {"periods": [{"name": "Ene.2024", "values": ["1"]}]}

        class Blocked(Resp):
            headers = {"Content-Type": "text/html"}
            text = "<!DOCTYPE html><html></html>"

        responses = [Blocked(), Resp()]

        def fake_get(*args, **kwargs):
            calls["n"] += 1
            return responses[min(calls["n"] - 1, 1)]

        monkeypatch.setattr(http.requests, "get", fake_get)
        data = http._http_get_json("https://example.com", max_retries=2)
        assert data["periods"][0]["name"] == "Ene.2024"
        assert calls["n"] == 2

    def test_raises_after_max_retries(self, monkeypatch):
        class Resp:
            status_code = 503
            headers = {}
            text = ""

        monkeypatch.setattr(http.requests, "get", lambda *a, **k: Resp())
        with pytest.raises(RuntimeError):
            http._http_get_json("https://example.com", max_retries=2)


class TestExports:
    @pytest.fixture()
    def frame(self):
        return pd.DataFrame({"fecha": ["Ene.2024", "Feb.2024"], "PN00001MM": [1.5, 2.5]})

    def test_csv(self, frame, tmp_path):
        path = api.export_series(frame, "PN00001MM", "2024-1", "2024-2", "csv", str(tmp_path))
        df = pd.read_csv(path, encoding="utf-8-sig")
        assert list(df.columns) == ["fecha", "PN00001MM"]

    def test_json(self, frame, tmp_path):
        path = api.export_series(frame, "PN00001MM", "2024-1", "2024-2", "json", str(tmp_path))
        assert json.load(open(path, encoding="utf-8"))[0]["fecha"] == "Ene.2024"

    def test_txt(self, frame, tmp_path):
        path = api.export_series(frame, "PN00001MM", "2024-1", "2024-2", "txt", str(tmp_path))
        assert "\t" in open(path, encoding="utf-8-sig").readline()

    def test_xml(self, frame, tmp_path):
        path = api.export_series(frame, "PN00001MM", "2024-1", "2024-2", "xml", str(tmp_path))
        root = ET.parse(path).getroot()
        assert root.tag == "serie"
        assert len(root.findall("periodo")) == 2

    def test_html(self, frame, tmp_path):
        path = api.export_series(frame, "PN00001MM", "2024-1", "2024-2", "html", str(tmp_path))
        text = open(path, encoding="utf-8").read()
        assert "<!DOCTYPE html>" in text and "PN00001MM" in text

    def test_invalid_format(self, frame, tmp_path):
        with pytest.raises(ValueError):
            api.export_series(frame, "X", "1", "2", "pdf", str(tmp_path))


class TestTheme:
    def test_day_is_light(self):
        assert resolve_theme(datetime(2026, 1, 1, 9, 0)) == __import__("flet").ThemeMode.LIGHT

    def test_night_is_dark(self):
        assert resolve_theme(datetime(2026, 1, 1, 22, 0)) == __import__("flet").ThemeMode.DARK

    def test_boundaries(self):
        import flet as ft

        assert resolve_theme(datetime(2026, 1, 1, 6, 0)) == ft.ThemeMode.LIGHT
        assert resolve_theme(datetime(2026, 1, 1, 18, 0)) == ft.ThemeMode.DARK

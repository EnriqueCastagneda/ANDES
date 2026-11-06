"""Cuadros estadísticos del MEF y exportación en todos los formatos."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pandas as pd
import pytest
import xlwt

from andes.core import mef_stats
from andes.core.api import export_series


def _sample_xls(path):
    book = xlwt.Workbook()
    sheet = book.add_sheet("Hoja1")
    sheet.write(0, 1, "Cuadro 99")
    sheet.write(1, 1, "SERIE DE PRUEBA")
    sheet.write(3, 2, 2020)
    sheet.write(3, 3, 2021)
    sheet.write(5, 1, "Ingresos")
    sheet.write(6, 1, "Tributarios")
    sheet.write(6, 2, 10.5)
    sheet.write(6, 3, 11.5)
    sheet.write(7, 1, "No tributarios")
    sheet.write(7, 2, 2.0)
    book.save(str(path))


def test_extract_annual_series(tmp_path):
    path = tmp_path / "cuadro99.xls"
    _sample_xls(path)
    series = mef_stats.extract(str(path), "https://x/cuadro99.xls", "Cuadro 99")
    assert len(series) == 2
    tributarios = next(s for s in series if s["label"] == "Tributarios")
    assert tributarios["frequency"] == "Anual"
    assert tributarios["points"] == [("2020-01-01", 10.5), ("2021-01-01", 11.5)]


@pytest.mark.parametrize("fmt", ["csv", "json", "xls", "xml", "txt", "html"])
def test_export_all_formats(tmp_path, fmt):
    frame = pd.DataFrame(
        {"fecha": ["2020-01-01", "2021-01-01"], "MEF-EST-TEST": [10.5, 11.5]}
    )
    path = export_series(
        frame, "MEF-EST-TEST", "2020-01-01", "2021-12-31", fmt, out_dir=str(tmp_path)
    )
    assert path.endswith(f".{fmt}")
    if fmt == "json":
        assert json.loads(open(path, encoding="utf-8").read()) == [
            {"fecha": "2020-01-01", "MEF-EST-TEST": 10.5},
            {"fecha": "2021-01-01", "MEF-EST-TEST": 11.5},
        ]
    elif fmt == "xml":
        assert ET.parse(path).getroot().tag == "serie"
    elif fmt == "xls":
        assert len(pd.read_excel(path)) == 2
    elif fmt == "html":
        assert "<table" in open(path, encoding="utf-8").read()
    else:
        assert len(open(path, encoding="utf-8-sig").read().splitlines()) == 3

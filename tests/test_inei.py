"""Población distrital INEI: indexado, búsqueda y descarga."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import openpyxl
import pandas as pd

from andes.core.adapters.inei import IneiAdapter, _bounds, _numeric, _ubigeo
from andes.core.api import export_series


def test_bounds_accepts_years_and_months():
    assert _bounds("2018", "2026") == ("2018-01-01", "2026-12-01")
    assert _bounds("2020-01-01", "2024-12-31") == ("2020-01-01", "2024-12-31")


def test_numeric_and_ubigeo_normalization():
    assert _numeric("1,234.5") == 1234.5
    assert _numeric("abc") is None
    assert _ubigeo("021801") == "021801"
    assert _ubigeo(21801.0) == "021801"


def test_adapter_indexes_and_searches():
    from andes.core import catalog

    adapter = IneiAdapter()
    adapter._ensure_indexed()
    assert catalog.count_prefix("INEI-POP", "inei") > 0
    frame = adapter.search("chimbote")
    assert len(frame) == 2
    assert frame.iloc[0]["Código de serie"].upper() == "INEI-POP-021801"


def test_adapter_fetches_full_history():
    adapter = IneiAdapter()
    data = adapter.fetch(["INEI-POP-021801"], "2018-01-01", "2026-01-01")
    assert len(data) == 9
    assert list(data["fecha"]) == [
        f"{year}-01-01" for year in range(2018, 2027)
    ]
    assert data.iloc[0]["INEI-POP-021801"] == 215834.0
    assert data.iloc[-1]["INEI-POP-021801"] == 213966.0


def test_adapter_respects_year_range():
    adapter = IneiAdapter()
    data = adapter.fetch(["INEI-POP-021801"], "2020", "2022")
    assert list(data["fecha"]) == ["2020-01-01", "2021-01-01", "2022-01-01"]


def test_adapter_info():
    adapter = IneiAdapter()
    info = adapter.info("INEI-POP-021801")
    assert info["institution"] == "inei"
    assert info["source"] == "INEI"

def _sample_xlsx(path):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["CUADRO Nº 01"])
    sheet.append(["PERÚ: POBLACIÓN TOTAL PROYECTADA"])
    sheet.append([])
    sheet.append(["UBIGEO", "Departamento, provincia y distrito", "Población", None, None])
    sheet.append([None, None, 2018, 2019, 2020])
    sheet.append([])
    sheet.append(["010000", "AMAZONAS", 400000, 410000, 420000])
    sheet.append(["010101", "CHACHAPOYAS", 30000, 31000, 32000])
    sheet.append(["010102", "ASUNCION", 9000, 9100, 9200])
    book.save(path)


def test_load_parses_synthetic_workbook(tmp_path, monkeypatch):
    path = tmp_path / "pop.xlsx"
    _sample_xlsx(path)
    adapter = IneiAdapter()
    monkeypatch.setattr(adapter, "_fetch_file", lambda: str(path))
    frame = adapter._load()
    assert set(frame["ubigeo"]) == {"010101", "010102"}
    assert set(frame["department"]) == {"AMAZONAS"}
    row = frame[frame["ubigeo"] == "010101"].iloc[0]
    assert row["points"] == [
        ("2018-01-01", 30000.0),
        ("2019-01-01", 31000.0),
        ("2020-01-01", 32000.0),
    ]


def test_fetch_reads_synthetic_workbook(tmp_path, monkeypatch):
    path = tmp_path / "pop.xlsx"
    _sample_xlsx(path)
    adapter = IneiAdapter()
    monkeypatch.setattr(adapter, "_fetch_file", lambda: str(path))
    data = adapter.fetch(["INEI-POP-010101"], "2019", "2020")
    assert list(data["fecha"]) == ["2019-01-01", "2020-01-01"]
    assert list(data["INEI-POP-010101"]) == [31000.0, 32000.0]


def test_inei_exports_all_formats(tmp_path, monkeypatch):
    frame = pd.DataFrame(
        {"fecha": ["2018-01-01", "2019-01-01"], "INEI-POP-010101": [30000.0, 31000.0]}
    )
    for fmt in ("csv", "json", "xls", "xml", "txt", "html"):
        path = export_series(
            frame, "INEI-POP-010101", "2018-01-01", "2019-12-31", fmt,
            out_dir=str(tmp_path),
        )
        assert path.endswith(f".{fmt}")
        if fmt == "json":
            assert len(json.loads(open(path, encoding="utf-8").read())) == 2
        elif fmt == "xml":
            assert ET.parse(path).getroot().tag == "serie"
        elif fmt == "xls":
            assert len(pd.read_excel(path)) == 2
        elif fmt == "html":
            assert "<table" in open(path, encoding="utf-8").read()
        else:
            assert len(open(path, encoding="utf-8-sig").read().splitlines()) == 3


def test_xml_export_sanitizes_numeric_columns():
    import xml.etree.ElementTree as ET

    from andes.core.api import _dataframe_to_xml

    frame = pd.concat(
        [
            pd.Series(["2020-01-01"], name="fecha"),
            pd.Series([1.5], name="2015"),
            pd.Series([2.0], name="2015"),
            pd.Series([3], name="a b"),
        ],
        axis=1,
    )
    root = ET.fromstring(_dataframe_to_xml(frame))
    tags = [child.tag for child in root[0]]
    assert tags[1] == "col_2015"
    assert len(tags) == len(set(tags))

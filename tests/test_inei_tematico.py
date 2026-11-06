"""Índice temático INEI: descubrimiento dinámico y descarga de archivos."""
from __future__ import annotations

import json

import openpyxl

from bcrp_downloader.core.adapters import get_adapter
from bcrp_downloader.core.adapters.inei_tematico import IneiTematicoAdapter

INDEX_HTML = """
<html><body>
<a href="/estadisticas/indice-tematico/economia/">Economía</a>
<a href="/estadisticas/indice-tematico/sociales/">Sociales</a>
</body></html>
"""

ECONOMIA_HTML = """
<html><body>
<span class="indice-tematico"> ECONOMÍA </span>
<ul>
  <li class="sub-indice-tematico titulo"><a href="/estadisticas/indice-tematico/cuentas/">Cuentas Nacionales</a>
    <ul>
      <li><a href="/media/MenuRecursivo/indices_tematicos/pbi.xlsx" title="Producto Bruto Interno 2020-2025">Producto Bruto Interno 2020-2025</a></li>
      <li><a href="/media/MenuRecursivo/indices_tematicos/pbi.csv">PBI en CSV</a></li>
    </ul>
  </li>
</ul>
</body></html>
"""

SOCIALES_HTML = """
<html><body>
<span class="indice-tematico"> SOCIALES </span>
<ul><li><a href="/media/MenuRecursivo/indices_tematicos/pobreza.xlsx">Población en situación de pobreza</a></li></ul>
</body></html>
"""


def _fake_get(mapping):
    def inner(url, headers=None, timeout=None):
        return _Response(mapping[url])
    return inner


class _Response:
    def __init__(self, text):
        self.text = text
        self.content = text.encode()

    def raise_for_status(self):
        return None


def test_index_is_discovered_dynamically(monkeypatch, tmp_path):
    adapter = IneiTematicoAdapter()
    monkeypatch.setattr(adapter, "_fetch", lambda url: {
        "https://www.inei.gob.pe/estadisticas-indice-tematico/": INDEX_HTML,
        "https://www.inei.gob.pe/estadisticas/indice-tematico/economia/": ECONOMIA_HTML,
        "https://www.inei.gob.pe/estadisticas/indice-tematico/sociales/": SOCIALES_HTML,
    }[url])
    data = adapter._scan()
    names = [c["name"] for c in data["categories"]]
    assert names == ["ECONOMÍA", "SOCIALES"]
    assert len(data["files"]) == 3
    assert {f["category"] for f in data["files"]} == {"ECONOMÍA", "SOCIALES"}
    assert all(f["url"].startswith("https://www.inei.gob.pe/media/") for f in data["files"])


def test_header_detection_reads_years(tmp_path):
    path = tmp_path / "t.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["TASA DE DESEMPLEO"])
    sheet.append(["(Porcentaje)"])
    sheet.append(["Ciudad", 2022, 2023])
    sheet.append(["Total", 6.4, 6.9])
    sheet.append(["Lima", 7.7, 6.7])
    book.save(path)
    frame = IneiTematicoAdapter._table(str(path), "xlsx")
    assert list(frame.columns) == ["Ciudad", "2022", "2023"]
    assert frame.iloc[0]["Ciudad"] == "Total"
    assert frame.iloc[1]["2022"] == 7.7


def test_fetch_reads_indexed_file(monkeypatch, tmp_path):
    path = tmp_path / "pbi.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["PBI", 2022, 2023])
    sheet.append(["Total", 100.0, 105.0])
    book.save(path)

    adapter = IneiTematicoAdapter()
    monkeypatch.setattr(
        "bcrp_downloader.core.adapters.inei_tematico.catalog.get",
        lambda code: {
            "code": code,
            "name": "Producto Bruto Interno",
            "memo": json.dumps(
                {"kind": "inei_tematico", "url": "https://x/pbi.xlsx", "format": "xlsx"}
            ),
        },
    )
    monkeypatch.setattr(adapter, "_download", lambda url: str(path))
    frame = adapter.fetch(["INEI-TEM-TEST"], "archivo", "unico")
    assert list(frame.columns) == ["PBI", "2022", "2023"]
    assert frame.iloc[0]["2022"] == 100.0


def test_registry_has_tematico():
    assert get_adapter("inei_tematico").institution == "inei_tematico"
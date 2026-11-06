"""Contrato de portales, adaptadores nativos y fixtures de jerarquía."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from bcrp_downloader.core import adapters, catalog, portals

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

CSV = (
    "Código de serie;Categoría de serie;Grupo de serie;Nombre de serie;"
    "Descripción de la serie;Metodología de la serie;Unidad de medida;Escala;"
    "Geografía (País, Región de Perú);Fuente;Frecuencia;Fecha de creación;"
    "Grupo de publicación;Área que publica;Fecha de actualización;"
    "Fecha de inicio;Fecha de fin;Memo\n"
    + ";".join(
        [
            "PD04638PD", "Tipo de cambio", "TC", "Tipo de cambio - Venta",
            "", "", "", "", "", "BCRP", "Diaria", "2021-01-10",
            "Tipo de cambio", "Mercados", "2026-10-23", "1997-01-02",
            "2026-10-22", "",
        ]
    )
    + "\n"
)


def test_mef_spec_declares_hierarchy():
    spec = portals.spec_for("mef")
    assert [dimension.label for dimension in spec.dimensions] == [
        "Año",
        "Nivel de gobierno",
        "Rubro",
        "Fuente de financiamiento",
        "Programa",
    ]
    options = {dimension.label: dimension.options for dimension in spec.dimensions}
    assert "1999" in options["Año"] and "2026" in options["Año"]
    assert "Gobiernos Locales" in options["Nivel de gobierno"]


def test_fixtures_match_declared_specs():
    for spec in portals.specs():
        data = json.loads((FIXTURES / spec.id / "hierarchy.json").read_text())
        assert data == json.loads(json.dumps(asdict(spec)))


def test_adapters_registered():
    assert {"bcrp", "mef", "inei", "inei_tematico", "gobpe"} <= set(adapters.registered())


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


RECORD = {
    "ANO_PRC": "2022",
    "MES_PRC": "4",
    "RECURSO_NOMBRE": "CANON MINERO",
    "RUBRO_NOMBRE": "CANON Y SOBRECANON, REGALIAS",
    "TIPO_ENTIDAD_NOMBRE": "GOBIERNO LOCAL",
    "GRUPO_TRANSFERENCIA_NOMBRE": "RECURSOS AUTORIZADOS",
    "FUENTE_NOMBRE": "DONACIONES Y TRANSFERENCIAS",
    "MONTO_AUTORIZADO": "100.50",
}


def test_mef_adapter_ingests_and_fetches(tmp_path, monkeypatch):
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(CSV, encoding="latin-1")
    monkeypatch.setattr(catalog, "METADATA_PATH", str(csv_path))
    monkeypatch.setattr(catalog, "CATALOG_PATH", str(tmp_path / "catalog.sqlite3"))

    from bcrp_downloader.core.adapters import mef

    mef.MefAdapter._resource = None
    mef.MefAdapter._resources = None
    monkeypatch.setattr(
        mef.requests,
        "post",
        lambda *a, **k: _Response(
            {
                "resources": [
                    {
                        "resource_name": "2022-Transferencias.csv",
                        "resource_url": f"/dataset/x/resource/{mef.BOOTSTRAP_RESOURCE}",
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(
        mef.requests,
        "get",
        lambda *a, **k: _Response(
            {
                "records": [dict(RECORD, MES_PRC="1"), RECORD],
                "result": {"include_total": 2},
            }
        ),
    )

    adapter = adapters.get_adapter("mef")
    frame = adapter.search("canon")
    assert len(frame) == 1
    code = frame.iloc[0]["Código de serie"].upper()
    assert code.startswith("MEF-")
    assert "CANON MINERO" in frame.iloc[0]["Nombre de serie"].upper()
    assert frame.iloc[0]["Fecha de inicio"] == "2022-01"
    assert frame.iloc[0]["Fecha de fin"] == "2022-04"

    monkeypatch.setattr(
        adapter,
        "_monthly_totals",
        lambda resource_id, recurso, year="": {
            "2022-01-01": 50.25,
            "2022-04-01": 100.50,
        },
    )
    data = adapter.fetch([code], "2022", "2022")
    assert list(data.columns) == ["fecha", code]
    assert list(data["fecha"]) == ["2022-01-01", "2022-04-01"]
    assert data.iloc[0][code] == pytest.approx(50.25)

    partial = adapter.fetch([code], "2022-02", "2022-04")
    assert list(partial["fecha"]) == ["2022-04-01"]


def test_bcrp_adapter_uses_local_catalog(tmp_path, monkeypatch):
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(CSV, encoding="latin-1")
    monkeypatch.setattr(catalog, "METADATA_PATH", str(csv_path))
    monkeypatch.setattr(catalog, "CATALOG_PATH", str(tmp_path / "catalog.sqlite3"))

    adapter = adapters.get_adapter("bcrp")
    frame = adapter.search("tipo de cambio", filters={"frecuencia": "Diaria"})
    assert list(frame["Código de serie"]) == ["pd04638pd"]


def test_unknown_portal_rejected():
    with pytest.raises(ValueError):
        adapters.get_adapter("nope")
    with pytest.raises(ValueError):
        portals.spec_for("nope")


def test_mef_period_bounds_accept_full_dates():
    from bcrp_downloader.core.adapters.mef import _bounds

    assert _bounds("2010-01-01", "2026-10-01") == ("2010-01", "2026-10")
    assert _bounds("2022", "2024") == ("2022-01", "2024-12")

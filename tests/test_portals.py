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
    assert spec.pending


def test_fixtures_match_declared_specs():
    for spec in portals.specs():
        data = json.loads((FIXTURES / spec.id / "hierarchy.json").read_text())
        assert data == json.loads(json.dumps(asdict(spec)))


def test_adapters_registered():
    assert {"bcrp", "mef"} <= set(adapters.registered())


def test_mef_adapter_is_pending():
    adapter = adapters.get_adapter("mef")
    assert adapter.search("gasto").empty
    with pytest.raises(NotImplementedError):
        adapter.fetch(["MEF1"], "2024", "2026")


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

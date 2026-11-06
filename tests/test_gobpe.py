"""Portales de Gob.pe: clasificación, registro y lectura de datos."""
from __future__ import annotations

import json

import pandas as pd

from bcrp_downloader.core import gobpe
from bcrp_downloader.core.adapters.gobpe import GobpeAdapter
from bcrp_downloader.core.gobpe import infer_institution


def test_classify_platforms():
    assert gobpe.classify("https://x.gob.pe/a.csv") == "csv"
    assert gobpe.classify("https://x.gob.pe/a.XLSX") == "excel"
    assert gobpe.classify("https://x.gob.pe/api/3/action/package_search") == "api"
    assert gobpe.classify("https://public.tableau.com/app/x") == "tableau"
    assert gobpe.classify("https://app.powerbi.com/view?r=1") == "powerbi"
    assert gobpe.classify("https://x.gob.pe/a.pdf") == "pdf"
    assert gobpe.classify("https://x.gob.pe/datos/") == "web"
    assert gobpe.classify("/inei") == "gobpe"
    assert gobpe.classify("") == "sin-enlace"


def test_build_registry_dedupes_and_skips_empty():
    records = [
        {"name": "Portal A", "institution": "Entidad A", "kind": "service",
         "url": "https://a.gob.pe/"},
        {"name": "Portal A repetido", "institution": "Entidad A", "kind": "service",
         "url": "https://a.gob.pe/"},
        {"name": "Sin enlace", "institution": "Entidad B", "kind": "service",
         "url": ""},
        {"name": "CSV", "institution": "Entidad C", "kind": "service",
         "url": "https://c.gob.pe/d.csv"},
        {"name": "Norma PDF", "institution": "Entidad D", "kind": "",
         "url": "https://d.gob.pe/n.pdf"},
    ]
    portals = gobpe.build_registry(records)
    urls = [portal["url"] for portal in portals]
    assert len(portals) == 2
    assert "https://a.gob.pe/" in urls
    assert "https://c.gob.pe/d.csv" in urls
    assert {portal["platform"] for portal in portals} == {"web", "csv"}
    assert all(portal["id"].startswith("GOBPE-") for portal in portals)


def test_registry_roundtrip(tmp_path):
    records = [{"name": "Portal", "institution": "Entidad",
                "url": "https://a.gob.pe/"}]
    portals = gobpe.build_registry(records)
    path = tmp_path / "portals.json"
    gobpe.save_registry(portals, str(path))
    loaded = gobpe.load_registry(str(path))
    assert loaded == portals


def test_adapter_without_registry_does_not_index(monkeypatch):
    adapter = GobpeAdapter()
    monkeypatch.setattr(gobpe, "load_registry", lambda path=None: [])
    assert adapter._ensure_indexed() == 0


def test_parse_json_records(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"records": [{"a": 1}, {"a": 2}]}), encoding="utf-8")
    frame = GobpeAdapter._parse(str(path), "json")
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) == 2
    assert list(frame.columns) == ["a"]


def test_non_tabular_portal_returns_empty(monkeypatch, tmp_path):
    adapter = GobpeAdapter()
    monkeypatch.setattr(
        "bcrp_downloader.core.adapters.gobpe.catalog.get",
        lambda code: {
            "code": code,
            "name": "Tablero",
            "memo": json.dumps(
                {"kind": "gobpe", "url": "https://x/tableau", "platform": "tableau"}
            ),
        },
    )
    assert adapter.fetch(["GOBPE-TEST"]).empty

def test_group_rules_collapse_repeated_prefixes():
    assert infer_institution("MUNISATIPO", "") == (
        "municipalidades", "Municipalidades"
    )
    assert infer_institution("MUNISANISIDRO-LIMA", "") == (
        "municipalidades", "Municipalidades"
    )
    assert infer_institution("REGIONPIURA", "") == ("regiones", "Regiones")
    assert infer_institution("REGIONLAMBAYEQUE-GERESA", "") == (
        "regiones", "Regiones"
    )
    assert infer_institution("UGELHUARMACA", "") == ("ugel", "UGEL")
    assert infer_institution(
        "Unidad de Gestión Educativa Local Tahuamanu", ""
    ) == ("ugel", "UGEL")

def test_institutions_keep_full_name_for_tooltip():
    portals = gobpe.build_registry(
        [
            {
                "name": "Portal",
                "institution": "INPE - Instituto Nacional Penitenciario",
                "kind": "service",
                "url": "https://siep.inpe.gob.pe/",
            }
        ]
    )
    inst = gobpe.institutions(portals)
    assert inst == [
        {
            "id": "inpe",
            "label": "INPE",
            "name": "INPE - Instituto Nacional Penitenciario",
        }
    ]


def test_group_institution_uses_descriptive_name():
    portals = [
        {"institution_id": "municipalidades", "institution_label": "Municipalidades",
         "institution_full": "MUNISATIPO", "id": "GOBPE-1"},
    ]
    inst = gobpe.institutions(portals)
    assert inst[0]["name"] == gobpe.GROUP_NAMES["municipalidades"]
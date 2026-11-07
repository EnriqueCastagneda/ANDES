"""Origen de cada serie: URL y etiqueta del recurso."""
from __future__ import annotations

import json
import sqlite3

import pytest

from andes.core import catalog, metadata


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "catalog.sqlite3")
    conn = sqlite3.connect(path)
    conn.executescript(catalog._SCHEMA)
    conn.commit()
    conn.close()
    catalog.upsert(
        [
            {"institution": "bcrp", "code": "PN00001MM", "name": "Canon"},
            {"institution": "mef", "code": "MEF-1", "name": "Transferencia",
             "memo": json.dumps({"recurso": "CANON"})},
            {"institution": "inei", "code": "INEI-POP-010101", "name": "Distrito"},
            {"institution": "inei_tematico", "code": "INEI-TEM-1", "name": "Cuadro",
             "memo": json.dumps({"url": "https://x/cuadro.xls"})},
            {"institution": "gobpe:inpe", "code": "GOBPE-1", "name": "Portal",
             "memo": json.dumps({"url": "https://siep.inpe.gob.pe/"})},
        ],
        db_path=path,
    )
    return path


def test_bcrp_origin_is_api(db):
    url, label = metadata.origin_for("PN00001MM", db_path=db)
    assert label == "API BCRP"
    assert url.startswith(
        "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
    )
    assert "PN00001MM" in url


def test_mef_origin_is_api(db):
    url, label = metadata.origin_for("MEF-1", db_path=db)
    assert label == "API MEF"
    assert url == "https://datosabiertos.mef.gob.pe"


def test_inei_origin_uses_source(db):
    _, label = metadata.origin_for("INEI-POP-010101", db_path=db)
    assert label == "INEI"
    url, label = metadata.origin_for("INEI-TEM-1", db_path=db)
    assert label == "INEI Temático"
    assert url == "https://x/cuadro.xls"


def test_gobpe_origin_uses_portal_url(db):
    url, label = metadata.origin_for("GOBPE-1", db_path=db)
    assert label == "Portal Gob.pe"
    assert url == "https://siep.inpe.gob.pe/"


def test_unknown_origin_falls_back(db):
    url, label = metadata.origin_for("NO-EXISTE", db_path=db)
    assert url == "https://www.gob.pe"
    assert label == "Gob.pe"
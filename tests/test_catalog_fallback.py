"""Catálogo sin FTS5 (Android y SQLite reducidos)."""
from __future__ import annotations

import sqlite3

import pytest

from andes.core import catalog


@pytest.fixture()
def db_without_fts(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "_FTS5_AVAILABLE", False)
    path = str(tmp_path / "catalog.sqlite3")
    conn = sqlite3.connect(path)
    conn.executescript(catalog._schema())
    conn.commit()
    conn.close()
    catalog.upsert(
        [
            {"institution": "bcrp", "code": "PN00001MM",
             "name": "Canon minero", "category": "Canon", "unit": "Millones"},
            {"institution": "bcrp", "code": "PN00003MM",
             "name": "Tipo de cambio", "category": "Cambiario",
             "unit": "S/ por US$"},
            {"institution": "bcrp", "code": "PN00004MM",
             "name": "Población total", "category": "Social",
             "unit": "Personas"},
        ],
        db_path=path,
    )
    return path


def _codes(db, query="", **kwargs):
    return [row["code"] for row in catalog.search(query, db_path=db, **kwargs)]


def test_schema_without_fts_has_no_virtual_table(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "_FTS5_AVAILABLE", False)
    path = str(tmp_path / "plain.sqlite3")
    conn = sqlite3.connect(path)
    conn.executescript(catalog._schema())
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    conn.close()
    assert "series" in names
    assert "series_fts" not in names


def test_fallback_search_matches_prefix_and_accent(db_without_fts):
    assert set(_codes(db_without_fts, "canon")) == {"PN00001MM"}
    # «poblacion» debe encontrar «Población» sin FTS5.
    assert _codes(db_without_fts, "poblacion") == ["PN00004MM"]


def test_fallback_search_requires_all_terms(db_without_fts):
    assert _codes(db_without_fts, "tipo cambio") == ["PN00003MM"]
    assert _codes(db_without_fts, "tipo canon") == []


def test_fallback_search_keeps_filters(db_without_fts):
    assert _codes(db_without_fts, "canon", category="Canon") == ["PN00001MM"]
    assert _codes(db_without_fts, "canon", category="Social") == []


def test_fallback_count_and_get(db_without_fts):
    assert catalog.count(db_path=db_without_fts) == 3
    assert catalog.get("PN00003MM", db_path=db_without_fts)["name"] == (
        "Tipo de cambio"
    )


@pytest.mark.skipif(not catalog.has_fts5(), reason="SQLite sin FTS5")
def test_schema_with_fts_keeps_batch_search(tmp_path):
    path = str(tmp_path / "fts.sqlite3")
    conn = sqlite3.connect(path)
    conn.executescript(catalog._schema(True))
    conn.commit()
    conn.close()
    catalog.upsert(
        [{"institution": "bcrp", "code": "PN1", "name": "Canon minero"}],
        db_path=path,
    )
    assert _codes(path, "canon") == ["PN1"]

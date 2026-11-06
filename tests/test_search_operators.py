"""Operadores de búsqueda avanzada sobre el catálogo FTS5."""
from __future__ import annotations

import sqlite3

import pytest

from andes.core import catalog
from andes.core.catalog import _fts_query


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "catalog.sqlite3")
    conn = sqlite3.connect(path)
    conn.executescript(catalog._SCHEMA)
    conn.commit()
    conn.close()
    rows = [
        {"institution": "bcrp", "code": "PN00001MM",
         "name": "Canon minero", "category": "Canon", "unit": "Millones"},
        {"institution": "bcrp", "code": "PN00002MM",
         "name": "Canon forestal", "category": "Canon", "unit": "Millones"},
        {"institution": "bcrp", "code": "PN00003MM",
         "name": "Tipo de cambio", "category": "Cambiario", "unit": "S/ por US$"},
        {"institution": "bcrp", "code": "PN00004MM",
         "name": "Población total", "category": "Social", "unit": "Personas"},
    ]
    catalog.upsert(rows, db_path=path)
    return path


def _codes(db, query):
    return [row["code"] for row in catalog.search(query, db_path=db)]


def test_plain_search_is_prefix(db):
    assert set(_codes(db, "canon")) == {"PN00001MM", "PN00002MM"}


def test_and_operator(db):
    assert _codes(db, "canon AND minero") == ["PN00001MM"]


def test_or_operator(db):
    assert set(_codes(db, "canon OR cambio")) == {
        "PN00001MM", "PN00002MM", "PN00003MM",
    }


def test_not_operator(db):
    assert _codes(db, "canon NOT forestal") == ["PN00001MM"]
    assert _codes(db, "canon -forestal") == ["PN00001MM"]


def test_quoted_phrase(db):
    assert _codes(db, '"tipo de cambio"') == ["PN00003MM"]
    assert _codes(db, '"canon minero"') == ["PN00001MM"]


def test_parentheses(db):
    assert _codes(db, "(canon OR social) AND total") == ["PN00004MM"]


def test_field_prefix(db):
    assert _codes(db, "codigo:PN00003MM") == ["PN00003MM"]
    assert _codes(db, "nombre:poblacion") == ["PN00004MM"]
    assert _codes(db, "categoria:canon") == ["PN00001MM", "PN00002MM"]


def test_wildcard_and_accents(db):
    assert set(_codes(db, "canon*")) == {"PN00001MM", "PN00002MM"}
    assert _codes(db, "poblacion") == ["PN00004MM"]


def test_invalid_expression_falls_back(db):
    assert set(_codes(db, "(canon OR")) == {"PN00001MM", "PN00002MM"}
    assert _codes(db, "canon AND") == ["PN00001MM", "PN00002MM"]


def test_translation_shape():
    assert _fts_query("canon AND minero") == '"canon"* AND "minero"*'
    assert _fts_query("canon NOT forestal") == '"canon"* NOT "forestal"*'
    assert _fts_query('"tipo de cambio"') == '"tipo de cambio"'
    assert _fts_query("nombre:población") == 'name:"población"*'
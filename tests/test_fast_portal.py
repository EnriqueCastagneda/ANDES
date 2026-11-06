"""Pruebas del catálogo FTS5 y del cliente por lotes (sin red)."""

from __future__ import annotations

from andes.core import catalog, fetcher

CSV = (
    "Código de serie;Categoría de serie;Grupo de serie;Nombre de serie;"
    "Descripción de la serie;Metodología de la serie;Unidad de medida;Escala;"
    "Geografía (País, Región de Perú);Fuente;Frecuencia;Fecha de creación;"
    "Grupo de publicación;Área que publica;Fecha de actualización;"
    "Fecha de inicio;Fecha de fin;Memo\n"
    "PD04638PD;Tipo de cambio;TC;Tipo de cambio - Venta;;;;;;;Diaria;;;"
    ";;;1997-01-02;2026-10-22;\n"
    "PN01250PM;Precios;Inflación;Inflación USA;;;;;;;Mensual;;;"
    ";;;Ene-1992;Dic-2025;\n"
)


def test_catalog_search_prefix_and_accents(tmp_path):
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(CSV, encoding="latin-1")
    db_path = tmp_path / "catalog.sqlite3"
    catalog.build_catalog(str(csv_path), str(db_path))

    hits = catalog.search("inflacion", db_path=str(db_path))
    assert hits and hits[0]["code"] == "PN01250PM"

    hits = catalog.search("tipo de camb", frequency="Diaria", db_path=str(db_path))
    assert [h["code"] for h in hits] == ["PD04638PD"]


def test_period_syntax():
    assert fetcher.period("Diaria", 2026, 11, 5) == "2026-11-5"
    assert fetcher.period("Mensual", 2026, 11) == "2026-11"
    assert fetcher.period("Trimestral", 2026, quarter=4) == "2026-4"
    assert fetcher.period("Anual", 2026) == "2026"


def test_parse_period_two_digit_years():
    assert fetcher.parse_period("01.Ene.97", "Diaria") == "1997-01-01"
    assert fetcher.parse_period("31.Dic.26", "Diaria") == "2026-12-31"
    assert fetcher.parse_period("T1.20", "Trimestral") == "2020-01-01"
    assert fetcher.parse_period("Ene.2024", "Mensual") == "2024-01-01"
    assert fetcher.parse_period("2025", "Anual") == "2025-01-01"

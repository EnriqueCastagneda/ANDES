"""Reconstrucción del catálogo: filas ajenas válidas y sin códigos vacíos."""

from __future__ import annotations

import sqlite3

from andes.core import catalog

CSV = (
    "Código de serie;Categoría de serie;Grupo de serie;Nombre de serie;"
    "Descripción de la serie;Metodología de la serie;Unidad de medida;Escala;"
    "Geografía (País, Región de Perú);Fuente;Frecuencia;Fecha de creación;"
    "Grupo de publicación;Área que publica;Fecha de actualización;"
    "Fecha de inicio;Fecha de fin;Memo\n"
    "PN00001MM;Monetario;Agregados;Serie oficial;;;;;;;Mensual;;;"
    ";;;2020-01;2026-01;\n"
)


def test_build_catalog_keeps_only_valid_foreign_rows(tmp_path, monkeypatch):
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(CSV, encoding="latin-1")
    db_path = tmp_path / "catalog.sqlite3"

    conn = sqlite3.connect(db_path)
    conn.executescript(catalog._schema())
    conn.executemany(
        "INSERT INTO series (institution, code, name) VALUES (?, ?, ?)",
        [
            ("mef", "MEF-KEEP", "Serie MEF"),
            ("mef", "PN00001MM", "Código BCRP mal atribuido"),
            ("", "", "CHACHAPOYAS"),
        ],
    )
    conn.commit()
    conn.close()

    catalog.build_catalog(str(csv_path), str(db_path))

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT institution, code, name FROM series ORDER BY code"
    ).fetchall()
    conn.close()

    assert rows == [
        ("mef", "MEF-KEEP", "Serie MEF"),
        ("bcrp", "PN00001MM", "Serie oficial"),
    ]

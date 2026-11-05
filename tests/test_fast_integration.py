"""Pruebas de los adaptadores rápidos (catálogo FTS5 y lotes) sin red."""

from __future__ import annotations

import pandas as pd
from typer.testing import CliRunner

import bcrp_downloader.cli.main as cli
from bcrp_downloader.core import catalog, metadata

runner = CliRunner()

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


def _catalog(tmp_path, monkeypatch):
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(CSV, encoding="latin-1")
    monkeypatch.setattr(catalog, "METADATA_PATH", str(csv_path))
    monkeypatch.setattr(catalog, "CATALOG_PATH", str(tmp_path / "catalog.sqlite3"))


def test_search_catalog_returns_official_columns(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch)
    frame = metadata.search_catalog("inflacion")
    assert list(frame.columns) == list(catalog.COLUMNS.values())
    assert frame.iloc[0][metadata.KNOWN_CODE_COL] == "pn01250pm"


def test_frequency_for_detects_mismatch(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch)
    assert metadata.frequency_for(["PD04638PD"]) == "Diaria"
    try:
        metadata.frequency_for(["PD04638PD", "PN01250PM"])
    except ValueError as exc:
        assert "frecuencia" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("debía rechazar frecuencias distintas")


def test_cli_download_many_writes_file(tmp_path, monkeypatch):
    frame = pd.DataFrame({"fecha": ["2024-01-01"], "PN00001MM": [1.5]})
    monkeypatch.setattr(cli, "download_many", lambda *a, **k: frame)
    out = tmp_path / "lote.csv"
    result = runner.invoke(
        cli.app,
        ["download-many", "PN00001MM", "PN00002MM", "-s", "2024-1", "-e", "2024-2",
         "-o", str(out)],
    )
    assert result.exit_code == 0, result.stdout
    assert out.exists()

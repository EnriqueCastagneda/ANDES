"""Paridad entre los filtros SQL del catálogo y el filtro pandas original.

Cada clave de ``filter_metadata`` debe devolver el mismo conjunto de códigos que
``search_catalog``. Sirve como red de seguridad al añadir instituciones.
"""

from __future__ import annotations

import pandas as pd
import pytest

from bcrp_downloader.core import catalog, metadata

HEADER = (
    "Institución;Código de serie;Categoría de serie;Grupo de serie;Nombre de serie;"
    "Descripción de la serie;Metodología de la serie;Unidad de medida;Escala;"
    "Geografía (País, Región de Perú);Fuente;Frecuencia;Fecha de creación;"
    "Grupo de publicación;Área que publica;Fecha de actualización;"
    "Fecha de inicio;Fecha de fin;Memo"
)

ROWS = [
    "bcrp;PD04638PD;Tipo de cambio;TC;Tipo de cambio - Venta;;;;;;BCRP;Diaria;"
    "2021-01-10;Tipo de cambio;Mercados;2026-10-23;1997-01-02;2026-10-22;",
    "bcrp;PN01250PM;Precios;Inflación;Inflación USA;;;;;;INEI;Mensual;"
    "2022-03-24;Precios;Estadísticas;2026-06-24;Ene-1992;Dic-2025;",
    "bcrp;PN00001MM;Cuentas monetarias;Cuentas monetarias;Activos externos netos;"
    ";;;;;BCRP;Mensual;2020-05-01;Monetario;Estadísticas;2025-11-30;Ene-1992;Dic-2025;",
    "mef;PD04746FA;Presupuesto;Gasto;Gasto corriente;;;;;;MEF;Anual;2019-01-01;"
    "Presupuesto;Fiscal;2024-12-31;1970;2026;",
]

CSV = "\n".join([HEADER, *ROWS]) + "\n"


def _build(tmp_path, monkeypatch) -> pd.DataFrame:
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(CSV, encoding="latin-1")
    monkeypatch.setattr(catalog, "METADATA_PATH", str(csv_path))
    monkeypatch.setattr(catalog, "CATALOG_PATH", str(tmp_path / "catalog.sqlite3"))
    catalog.ensure_catalog()

    frame = pd.read_csv(
        csv_path, sep=";", encoding="latin-1", dtype=str, keep_default_na=False
    )
    frame = frame.drop(columns=["Institución"], errors="ignore")
    frame[metadata.KNOWN_CODE_COL] = frame[metadata.KNOWN_CODE_COL].str.lower()
    frame[metadata.KNOWN_NAME_COL] = frame[metadata.KNOWN_NAME_COL].str.lower()
    return frame


CASES = [
    {"institucion": "bcrp"},
    {"institucion": "mef"},
    {"frecuencia": "Mensual"},
    {"frecuencia": "Anual"},
    {"categoria": "Precios"},
    {"area": "Estadísticas"},
    {"fuente": "BCRP"},
    {"grupo_serie": "TC"},
    {"grupo_publicacion": "Presupuesto"},
    {"creacion_desde": "2021-06-01"},
    {"creacion_hasta": "2021-12-31"},
    {"actual_desde": "2026-01-01"},
    {"actual_hasta": "2025-12-31"},
    {"inicio": "1992"},
    {"fin": "2025"},
    {"institucion": "bcrp", "frecuencia": "Mensual", "area": "Estadísticas"},
]


@pytest.mark.parametrize("filters", CASES, ids=[str(c) for c in CASES])
def test_filter_parity(tmp_path, monkeypatch, filters):
    frame = _build(tmp_path, monkeypatch)

    if "institucion" in filters:
        # El CSV legado no tiene esa columna: se valida contra el catálogo.
        rest = {k: v for k, v in filters.items() if k != "institucion"}
        expected = {
            row["code"].lower()
            for row in catalog.search(
                "", limit=None, institution=filters["institucion"]
            )
        }
        if rest:
            expected &= set(
                metadata.search_catalog("", filters=rest, limit=None)[
                    metadata.KNOWN_CODE_COL
                ]
            )
    else:
        expected = set(
            metadata.filter_metadata(frame, filters)[metadata.KNOWN_CODE_COL]
        )

    got = set(
        metadata.search_catalog("", filters=filters, limit=None)[
            metadata.KNOWN_CODE_COL
        ]
    )
    assert got == expected


def test_text_search(tmp_path, monkeypatch):
    _build(tmp_path, monkeypatch)
    assert list(
        metadata.search_catalog("inflacion", limit=None)[metadata.KNOWN_CODE_COL]
    ) == ["pn01250pm"]
    assert list(
        metadata.search_catalog("presupuesto", limit=None)[metadata.KNOWN_CODE_COL]
    ) == ["pd04746fa"]


def test_mef_listed_even_without_rows(tmp_path, monkeypatch):
    _build(tmp_path, monkeypatch)
    assert ("mef", "MEF") in metadata.catalog_institutions()
    assert ("bcrp", "BCRP") in metadata.catalog_institutions()
    assert metadata.search_catalog("", filters={"institucion": "mef"}).shape[0] == 1


def test_mef_filter_options_have_seeds(tmp_path, monkeypatch):
    _build(tmp_path, monkeypatch)
    assert "2026" in metadata.institution_filter_options("mef", "start")
    assert "Gobiernos Locales" in metadata.institution_filter_options("mef", "group_name")
    assert "Recursos Ordinarios" in metadata.institution_filter_options("mef", "source")
    assert "Bienes y Servicios" in metadata.institution_filter_options("mef", "category")
    assert "Programas Presupuestales" in metadata.institution_filter_options(
        "mef", "pub_group"
    )
    # BCRP no hereda las semillas de MEF.
    assert "Recursos Ordinarios" not in metadata.institution_filter_options(
        "bcrp", "source"
    )

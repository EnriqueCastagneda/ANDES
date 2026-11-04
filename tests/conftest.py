"""Shared pytest fixtures."""

from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture()
def sample_df() -> pd.DataFrame:
    """Small metadata catalogue covering the fields used by the app."""
    return pd.DataFrame(
        {
            "Código de serie": ["pn00001mm", "pd04637pd", "pn01250pm"],
            "Nombre de serie": [
                "tipo de cambio nominal",
                "índice de precios",
                "tipo de cambio real",
            ],
            "Categoría de serie": [
                "Tipo de cambio nominal",
                "Inflación",
                "Tipo de cambio real",
            ],
            "Grupo de serie": ["moneda", "precios", "moneda"],
            "Fuente": ["BCRP", "INEI", "BCRP"],
            "Frecuencia": ["Mensual", "Diaria", "Mensual"],
            "Grupo de publicación": ["Tipo de cambio", "Precios", "Tipo de cambio"],
            "Área que publica": ["Mercados", "Estadísticas", "Mercados"],
            "Fecha de creación": ["2022-03-24", "2021-01-10", "2022-06-01"],
            "Fecha de actualización": ["2026-10-23", "2026-09-01", "2026-10-23"],
            "Fecha de inicio": ["Ene-1992", "Ene-2000", "Ene-1995"],
            "Fecha de fin": ["Dic-2025", "Dic-2025", "Dic-2024"],
            "Unidad de medida": ["S/", "Índice", "S/"],
            "Descripción de la serie": [
                "Ver https://estadisticas.bcrp.gob.pe/docs/bcrpdataapi.pdf",
                "Índice de precios al consumidor",
                "Tipo de cambio real bilateral",
            ],
        }
    )

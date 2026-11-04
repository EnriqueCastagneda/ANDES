"""
Test suite for BCRP Downloader - advanced metadata filtering.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from app import filter_metadata


def _sample_df():
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
        }
    )


class TestFilterMetadata(unittest.TestCase):
    def setUp(self):
        self.df = _sample_df()

    def test_no_filters_returns_all(self):
        self.assertEqual(len(filter_metadata(self.df, {})), 3)

    def test_codigo_substring(self):
        r = filter_metadata(self.df, {"codigo": "pn00001"})
        self.assertEqual(len(r), 1)
        self.assertEqual(r.iloc[0]["Código de serie"], "pn00001mm")

    def test_nombre_substring_case_insensitive(self):
        r = filter_metadata(self.df, {"nombre": "TIPO DE CAMBIO"})
        self.assertEqual(len(r), 2)

    def test_grupo_substring(self):
        r = filter_metadata(self.df, {"grupo": "moneda"})
        self.assertEqual(len(r), 2)

    def test_categoria_exact(self):
        r = filter_metadata(self.df, {"categoria": "Tipo de cambio real"})
        self.assertEqual(len(r), 1)
        self.assertEqual(r.iloc[0]["Código de serie"], "pn01250pm")

    def test_fuente_exact(self):
        r = filter_metadata(self.df, {"fuente": "INEI"})
        self.assertEqual(len(r), 1)

    def test_frecuencia_exact(self):
        r = filter_metadata(self.df, {"frecuencia": "Mensual"})
        self.assertEqual(len(r), 2)

    def test_grupo_publicacion_exact(self):
        r = filter_metadata(self.df, {"grupo_publicacion": "Tipo de cambio"})
        self.assertEqual(len(r), 2)

    def test_area_exact(self):
        r = filter_metadata(self.df, {"area": "Estadísticas"})
        self.assertEqual(len(r), 1)

    def test_fecha_inicio_substring(self):
        r = filter_metadata(self.df, {"inicio": "1992"})
        self.assertEqual(len(r), 1)

    def test_fecha_fin_substring(self):
        r = filter_metadata(self.df, {"fin": "Dic-2025"})
        self.assertEqual(len(r), 2)

    def test_creacion_date_range(self):
        r = filter_metadata(
            self.df, {"creacion_desde": "2022-01-01", "creacion_hasta": "2022-12-31"}
        )
        self.assertEqual(len(r), 2)

    def test_actualizacion_date_range(self):
        r = filter_metadata(self.df, {"actual_desde": "2026-10-01"})
        self.assertEqual(len(r), 2)

    def test_combined_filters(self):
        r = filter_metadata(
            self.df, {"categoria": "Tipo de cambio nominal", "frecuencia": "Mensual"}
        )
        self.assertEqual(len(r), 1)

    def test_todas_is_ignored(self):
        r = filter_metadata(self.df, {"categoria": "Todas", "fuente": "Todos"})
        self.assertEqual(len(r), 3)

    def test_empty_result(self):
        r = filter_metadata(self.df, {"codigo": "zzz"})
        self.assertTrue(r.empty)


if __name__ == "__main__":
    unittest.main(verbosity=2)

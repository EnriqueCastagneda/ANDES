import pandas as pd
import pytest

import app


@pytest.fixture
def df():
    rows = [
        ["PN01", "Tipo de cambio", "Mercado", "Cambiario", "BCRP", "Mensual", "G1", "Estudios",
         "01/01/2010", "15/03/2024"],
        ["PD02", "Tasa interbancaria", "Tasas", "Monetario", "SBS", "Diaria", "G2", "Operaciones",
         "05/02/2015", "10/05/2024"],
    ]
    cols = [app.COL_CODE, app.COL_NAME, app.COL_CATEGORY, app.COL_GROUP, app.COL_SOURCE,
            app.COL_FREQ, app.COL_PUBGROUP, app.COL_AREA, app.COL_CREATED, app.COL_UPDATED]
    d = pd.DataFrame(rows, columns=cols)
    d["_code_norm"] = d[app.COL_CODE].map(app._norm)
    d["_name_norm"] = d[app.COL_NAME].map(app._norm)
    return d


def codes(d):
    return list(d[app.COL_CODE])


def test_text(df):
    assert codes(app.filter_metadata(df, text=" pn01 ")) == ["PN01"]
    assert codes(app.filter_metadata(df, text="INTERBANCARIA")) == ["PD02"]


@pytest.mark.parametrize("kw,expected", [
    ({"grupo": "Monetario"}, ["PD02"]),
    ({"categoria": "Mercado"}, ["PN01"]),
    ({"fuente": "SBS"}, ["PD02"]),
    ({"frecuencia": "Mensual"}, ["PN01"]),
    ({"grupo_publicacion": "G2"}, ["PD02"]),
    ({"area": "Estudios"}, ["PN01"]),
    ({"creacion_desde": "2012-01-01"}, ["PD02"]),
    ({"actualizacion_hasta": "2024-04-01"}, ["PN01"]),
])
def test_single_filters(df, kw, expected):
    assert codes(app.filter_metadata(df, **kw)) == expected


def test_combination(df):
    assert codes(app.filter_metadata(df, text="tasa", frecuencia="Diaria", fuente="SBS")) == ["PD02"]
    assert app.filter_metadata(df, text="tasa", frecuencia="Mensual").empty


def test_all_values_ignored(df):
    out = app.filter_metadata(df, frecuencia="Todos", area="Todas", fuente="Todas",
                              categoria="Todas", grupo="Todos", grupo_publicacion="Todos")
    assert len(out) == 2


def test_api_dates():
    assert str(app.parse_api_date("2020-3")) == "2020-03-01"
    assert str(app.parse_api_date("2020-03-15")) == "2020-03-15"

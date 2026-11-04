import pytest

import app


def test_api_connection_and_structure():
    url = app.build_api_url("PN01207PM", "json", "2020-1", "2020-3")
    try:
        data = app._http_get_json(url, retries=3, delay=0.5)
    except Exception as exc:
        pytest.skip(f"API BCRP no disponible: {exc}")
    assert "config" in data and "periods" in data
    for period in data["periods"]:
        assert "name" in period and "values" in period

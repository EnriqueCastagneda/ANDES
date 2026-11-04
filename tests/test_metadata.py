import pytest

import app


@pytest.fixture(scope="module")
def meta(tmp_path_factory):
    path = tmp_path_factory.mktemp("data") / "metadata_bcrp.csv"
    try:
        app.download_metadata(path)
    except Exception as exc:
        pytest.skip(f"BCRP no disponible: {exc}")
    return app.load_metadata(path)


def test_download_only_if_missing(tmp_path, monkeypatch):
    path = tmp_path / "metadata_bcrp.csv"
    path.write_text("x", encoding="latin-1")
    monkeypatch.setattr(app, "_http_get", lambda *a, **k: pytest.fail("no debe descargar"))
    assert app.download_metadata(path) == path


def test_required_columns(meta):
    for col in app.REQUIRED_COLUMNS:
        assert col in meta.columns


def test_codes_unique_and_normalized(meta):
    assert meta[app.COL_CODE].is_unique
    assert (meta["_code_norm"] == meta["_code_norm"].str.strip().str.lower()).all()

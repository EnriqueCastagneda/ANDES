import json
import xml.etree.ElementTree as ET

import pandas as pd
import pytest

import app

DF = pd.DataFrame({"Periodo": ["Ene.2020", "Feb.2020"], "Serie": [1.5, 2.5]})


def test_csv(tmp_path):
    p = app.export_dataframe(DF, "csv", tmp_path / "a.csv")
    assert p.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "Ene.2020" in p.read_text(encoding="utf-8-sig")


def test_json(tmp_path):
    p = app.export_dataframe(DF, "json", tmp_path / "a.json")
    assert json.loads(p.read_text(encoding="utf-8"))[1]["Serie"] == 2.5


def test_txt(tmp_path):
    p = app.export_dataframe(DF, "txt", tmp_path / "a.txt")
    assert p.read_text(encoding="utf-8").splitlines()[0] == "Periodo\tSerie"


def test_xml(tmp_path):
    p = app.export_dataframe(DF, "xml", tmp_path / "a.xml")
    assert len(ET.parse(p).getroot()) == 2


def test_html(tmp_path):
    p = app.export_dataframe(DF, "html", tmp_path / "a.html")
    assert p.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_unknown_format(tmp_path):
    with pytest.raises(ValueError):
        app.export_dataframe(DF, "pdf", tmp_path / "a.pdf")


def test_xls_local_not_supported(tmp_path):
    with pytest.raises(ValueError):
        app.export_dataframe(DF, "xls", tmp_path / "a.xls")

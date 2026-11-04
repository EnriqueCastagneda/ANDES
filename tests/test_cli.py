"""Tests for the Typer command line interface."""

from __future__ import annotations

import pandas as pd
from typer.testing import CliRunner

import bcrp_downloader.cli.main as cli

runner = CliRunner()


def test_search_lists_series(sample_df, monkeypatch):
    monkeypatch.setattr(cli, "load_metadata", lambda: sample_df)
    result = runner.invoke(cli.app, ["search", "tipo de cambio"])
    assert result.exit_code == 0
    assert "PN00001MM" in result.stdout
    assert "PN01250PM" in result.stdout


def test_search_with_frequency(sample_df, monkeypatch):
    monkeypatch.setattr(cli, "load_metadata", lambda: sample_df)
    result = runner.invoke(
        cli.app, ["search", "tipo de cambio", "--frequency", "Mensual"]
    )
    assert result.exit_code == 0
    assert "PN00001MM" in result.stdout


def test_search_no_results(sample_df, monkeypatch):
    monkeypatch.setattr(cli, "load_metadata", lambda: sample_df)
    result = runner.invoke(cli.app, ["search", "zzz-no-existe"])
    assert result.exit_code == 1
    assert "Sin resultados" in result.stdout


def test_download_writes_file(tmp_path, sample_df, monkeypatch):
    frame = pd.DataFrame({"fecha": ["Ene.2024"], "PN00001MM": [1.5]})
    monkeypatch.setattr(cli, "download_series_data", lambda *a, **k: frame)
    out = tmp_path / "serie.csv"
    result = runner.invoke(
        cli.app,
        [
            "download",
            "PN00001MM",
            "--start",
            "2024-1",
            "--end",
            "2024-2",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert out.exists()


def test_download_invalid_format(sample_df, monkeypatch):
    monkeypatch.setattr(cli, "download_series_data", lambda *a, **k: pd.DataFrame())
    result = runner.invoke(
        cli.app,
        ["download", "PN00001MM", "--start", "1", "--end", "2", "--format", "pdf"],
    )
    assert result.exit_code == 2

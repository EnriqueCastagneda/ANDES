"""Smoke tests: imports, metadata integrity, CLI and MCP availability."""

from __future__ import annotations

import importlib
import os

import pytest
from typer.testing import CliRunner

from bcrp_downloader.cli.main import app
from bcrp_downloader.core.paths import METADATA_PATH


@pytest.mark.parametrize(
    "module",
    [
        "bcrp_downloader",
        "bcrp_downloader.core.api",
        "bcrp_downloader.core.http",
        "bcrp_downloader.core.metadata",
        "bcrp_downloader.core.paths",
        "bcrp_downloader.gui.theme",
        "bcrp_downloader.cli.main",
        "bcrp_downloader.mcp.server",
        "app",
    ],
)
def test_modules_import(module: str) -> None:
    assert importlib.import_module(module) is not None


@pytest.mark.skipif(
    not os.path.exists(METADATA_PATH), reason="metadata cache not downloaded"
)
def test_metadata_file_integrity() -> None:
    import pandas as pd

    df = pd.read_csv(METADATA_PATH, sep=";", encoding="latin-1")
    assert len(df) > 1000
    assert "Código de serie" in df.columns
    assert "Frecuencia" in df.columns


def test_cli_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("search", "download", "gui", "mcp"):
        assert command in result.stdout


def test_mcp_server_loads() -> None:
    from bcrp_downloader.mcp.server import server

    if server is None:
        pytest.skip("optional 'mcp' dependency not installed")
    assert server is not None

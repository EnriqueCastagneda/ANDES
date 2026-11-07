"""Rutas de datos y configuración por plataforma (XDG, Windows, macOS)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from andes.core import paths


def test_xdg_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert paths._user_data_dir() == tmp_path / "share" / "andes"


def test_xdg_config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert paths._user_config_dir() == tmp_path / "config" / "andes"


def test_default_data_dir_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDES_DATA_DIR", str(tmp_path / "explicito"))
    assert paths._default_data_dir() == str(tmp_path / "explicito")
    monkeypatch.delenv("ANDES_DATA_DIR")
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "flet"))
    assert paths._default_data_dir() == str(tmp_path / "flet")


def test_frozen_app_uses_user_directories(tmp_path, monkeypatch):
    monkeypatch.delenv("ANDES_DATA_DIR", raising=False)
    monkeypatch.delenv("ANDES_CONFIG_DIR", raising=False)
    monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    assert paths._default_data_dir() == str(paths._user_data_dir())
    assert paths._default_config_dir() == str(paths._user_config_dir())


@pytest.mark.skipif(os.name != "nt", reason="solo Windows")
def test_windows_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert paths._user_data_dir() == Path(tmp_path / "Local") / "ANDES"
    assert paths._user_config_dir() == Path(tmp_path / "Roaming") / "ANDES"

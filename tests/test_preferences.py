"""Preferencias: carpeta de guardado, validación y persistencia atómica."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from andes.core import preferences


@pytest.fixture()
def prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "PREFS_PATH", str(tmp_path / "prefs.json"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path / "prefs.json"


def test_default_output_dir_prefers_downloads(prefs, tmp_path):
    (tmp_path / "Downloads").mkdir()
    assert preferences.default_output_dir() == str(
        tmp_path / "Downloads" / "ANDES"
    )


def test_default_output_dir_falls_back_to_home(prefs, tmp_path):
    assert preferences.default_output_dir() == str(tmp_path / "ANDES")


def test_default_output_dir_honors_env(prefs, tmp_path, monkeypatch):
    target = tmp_path / "env-out"
    monkeypatch.setenv("ANDES_OUTPUT_DIR", str(target))
    assert preferences.default_output_dir() == str(target.resolve())


def test_output_dir_is_saved_and_created(prefs, tmp_path):
    target = tmp_path / "guardado"
    assert preferences.save_output_dir(str(target)) == str(target)
    assert preferences.load_output_dir() == str(target)
    assert preferences.ensure_output_dir() == str(target)
    assert target.is_dir()


def test_ensure_output_dir_uses_default_on_first_download(prefs, tmp_path):
    (tmp_path / "Downloads").mkdir()
    expected = str(tmp_path / "Downloads" / "ANDES")
    assert preferences.load_output_dir() == ""
    assert preferences.ensure_output_dir() == expected
    assert preferences.load_output_dir() == expected
    assert Path(expected).is_dir()


def test_normalize_expands_variables_quotes_and_relative(prefs, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert preferences.normalize_output_path("$HOME/datos") == str(
        (tmp_path / "datos").resolve()
    )
    assert preferences.normalize_output_path(f'"{tmp_path}/con espacios"') == str(
        (tmp_path / "con espacios").resolve()
    )
    assert preferences.normalize_output_path("relativa") == str(
        (tmp_path / "relativa").resolve()
    )


def test_path_pointing_to_file_is_rejected(prefs, tmp_path):
    archivo = tmp_path / "archivo.txt"
    archivo.write_text("x", encoding="utf-8")
    with pytest.raises(preferences.OutputDirError):
        preferences.prepare_output_dir(str(archivo))


def test_empty_and_null_paths_are_rejected(prefs):
    for value in ("", "   ", "ruta\x00invalida"):
        with pytest.raises(preferences.OutputDirError):
            preferences.normalize_output_path(value)


@pytest.mark.skipif(
    getattr(os, "geteuid", lambda: 1)() == 0, reason="root ignora permisos"
)
def test_readonly_directory_is_rejected(prefs, tmp_path):
    target = tmp_path / "solo-lectura"
    target.mkdir()
    target.chmod(0o500)
    try:
        with pytest.raises(preferences.OutputDirError):
            preferences.prepare_output_dir(str(target))
    finally:
        target.chmod(0o700)


def test_ensure_output_dir_recovers_from_stale_path(prefs, tmp_path):
    archivo = tmp_path / "ya-no-es-carpeta"
    archivo.write_text("x", encoding="utf-8")
    preferences.save_prefs(output_dir=str(archivo))
    assert preferences.ensure_output_dir() == str(tmp_path / "ANDES")
    assert preferences.load_output_dir() == str(tmp_path / "ANDES")


def test_clear_output_dir_returns_to_default(prefs, tmp_path):
    preferences.save_output_dir(str(tmp_path / "elegida"))
    preferences.clear_output_dir()
    assert preferences.load_output_dir() == ""


def test_prefs_are_written_atomically(prefs, tmp_path):
    preferences.save_output_dir(str(tmp_path / "salida"))
    leftovers = list(tmp_path.glob(".prefs-*"))
    assert leftovers == []
    assert prefs.is_file()


def test_corrupt_prefs_are_ignored(prefs):
    prefs.write_text("{no-json", encoding="utf-8")
    assert preferences.load_prefs() == {}
    assert preferences.load_output_dir() == ""


def test_normalize_output_path_normalizes_nfd_to_nfc(tmp_path, monkeypatch):
    """macOS (HFS+/APFS) guarda acentos en NFD; la ruta debe guardarse en NFC."""
    import unicodedata

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    nfd = unicodedata.normalize("NFD", "andés salida")
    out = preferences.normalize_output_path(nfd)
    assert unicodedata.is_normalized("NFC", out)
    assert out.endswith("andés salida")


def test_load_output_dir_normalizes_nfd(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "PREFS_PATH", str(tmp_path / "prefs.json"))
    import unicodedata

    nfd = unicodedata.normalize("NFD", "/tmp/andés salida")
    preferences.save_prefs(output_dir=nfd)
    assert unicodedata.is_normalized("NFC", preferences.load_output_dir())


def test_macos_data_path(prefs, tmp_path, monkeypatch):
    """macOS: datos y configuración en ~/Library/Application Support/andes."""
    from andes.core import paths

    monkeypatch.setattr(paths.sys, "platform", "darwin")
    expected = Path.home() / "Library" / "Application Support" / "andes"
    assert paths._user_data_dir() == expected
    assert paths._user_config_dir() == expected

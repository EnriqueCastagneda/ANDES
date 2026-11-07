"""Preferencias: carpeta de guardado por defecto y persistencia."""
from __future__ import annotations

from pathlib import Path

from andes.core import preferences


def test_default_output_dir_prefers_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "PREFS_PATH", str(tmp_path / "prefs.json"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Downloads").mkdir()
    assert preferences.default_output_dir() == str(
        tmp_path / "Downloads" / "ANDES"
    )


def test_default_output_dir_falls_back_to_home(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "PREFS_PATH", str(tmp_path / "prefs.json"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert preferences.default_output_dir() == str(tmp_path / "ANDES")


def test_output_dir_is_saved_and_created(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "PREFS_PATH", str(tmp_path / "prefs.json"))
    target = tmp_path / "guardado"
    preferences.save_output_dir(str(target))
    assert preferences.load_output_dir() == str(target)
    assert preferences.ensure_output_dir() == str(target)
    assert target.is_dir()


def test_ensure_output_dir_uses_default_on_first_download(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "PREFS_PATH", str(tmp_path / "prefs.json"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Downloads").mkdir()
    expected = str(tmp_path / "Downloads" / "ANDES")
    assert preferences.load_output_dir() == ""
    assert preferences.ensure_output_dir() == expected
    assert preferences.load_output_dir() == expected
    assert Path(expected).is_dir()

def test_default_output_dir_honors_env(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "PREFS_PATH", str(tmp_path / "prefs.json"))
    target = tmp_path / "env-out"
    monkeypatch.setenv("ANDES_OUTPUT_DIR", str(target))
    assert preferences.default_output_dir() == str(target.resolve())

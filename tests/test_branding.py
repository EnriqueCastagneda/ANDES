"""Identidad de marca y temas de ANDES."""
from __future__ import annotations

import json
import re
from pathlib import Path

import flet as ft

from andes import APP_NAME, APP_TAGLINE, APP_VERSION
from andes.core import branding
from andes.gui import theme as theme_module
from andes.gui.theme import ThemeController, resolve_theme


class _FakePage:
    def __init__(self):
        self.theme = None
        self.dark_theme = None
        self.theme_mode = None
        self.updates = 0

    def update(self):
        self.updates += 1


def test_brand_names():
    assert APP_NAME == "ANDES"
    assert APP_TAGLINE == "Open Data Platform"
    assert branding.ACRONYM_ES.startswith("Archivo Nacional")
    assert branding.ACRONYM_EN.startswith("Andean Network")


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = re.search(
        r'^version = "([^"]+)"', pyproject.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert declared, "pyproject.toml must declare a static version"
    assert APP_VERSION == declared.group(1)
    assert branding.APP_VERSION == declared.group(1)


def test_required_colors_are_exact():
    dark = branding.theme_dark().color_scheme
    light = branding.theme_light().color_scheme
    assert dark.surface.lower() == "#1b293d"
    assert dark.on_surface.lower() == "#d8b56d"
    assert light.surface.lower() == "#f1eadc"
    assert light.on_surface.lower() == "#2a3f48"


def test_logo_and_mark_match_theme():
    assert branding.logo_for(ft.ThemeMode.LIGHT) == "andes_logo_claro.png"
    assert branding.logo_for(ft.ThemeMode.DARK) == "andes_logo_oscuro.png"
    assert branding.mark_for(ft.ThemeMode.LIGHT) == "andes_isotipo_claro.png"
    assert branding.mark_for(ft.ThemeMode.DARK) == "andes_isotipo_oscuro.png"


def test_resolve_theme_by_hour():
    from datetime import datetime

    assert resolve_theme(datetime(2026, 1, 1, 10)) == ft.ThemeMode.LIGHT
    assert resolve_theme(datetime(2026, 1, 1, 23)) == ft.ThemeMode.DARK


def test_controller_applies_both_themes_and_persists(tmp_path, monkeypatch):
    prefs = tmp_path / "prefs.json"
    monkeypatch.setattr(theme_module, "_PREFS", str(prefs))
    page = _FakePage()
    controller = ThemeController(page)
    controller.manual = ft.ThemeMode.DARK
    controller.apply()
    assert page.theme is not None and page.dark_theme is not None
    assert page.theme_mode == ft.ThemeMode.DARK

    mode = controller.toggle()
    assert mode == ft.ThemeMode.LIGHT
    assert page.theme_mode == ft.ThemeMode.LIGHT
    assert json.loads(prefs.read_text(encoding="utf-8"))["theme_mode"] == "light"

    restored = ThemeController(_FakePage())
    assert restored.manual == ft.ThemeMode.LIGHT


def test_chart_palette_is_distinct():
    assert len(set(branding.CHART_COLORS)) == len(branding.CHART_COLORS)
    assert len(branding.CHART_COLORS) >= 8
    assert all(color.startswith("#") and len(color) == 7
               for color in branding.CHART_COLORS)
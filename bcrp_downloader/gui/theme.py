"""Temas de ANDES: claro y oscuro con persistencia local.

El modo oscuro usa fondo ``#1b293d`` y texto ``#d8b56d``; el claro usa fondo
``#f1eadc`` y texto ``#2a3f48``. La preferencia manual se guarda en
``data/prefs.json`` para recordarla entre sesiones.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime

import flet as ft

from ..core import branding
from ..core.paths import DATA_DIR

DAY_START_HOUR = 6
DAY_END_HOUR = 18
_PREFS = os.path.join(DATA_DIR, "prefs.json")
_KEY = "theme_mode"


def resolve_theme(now: datetime | None = None) -> ft.ThemeMode:
    """Tema por defecto según la hora local (claro de día, oscuro de noche)."""
    moment = now or datetime.now()
    if DAY_START_HOUR <= moment.hour < DAY_END_HOUR:
        return ft.ThemeMode.LIGHT
    return ft.ThemeMode.DARK


def _read_preference() -> ft.ThemeMode | None:
    try:
        with open(_PREFS, encoding="utf-8") as handle:
            value = json.load(handle).get(_KEY)
    except (OSError, ValueError):
        return None
    return {"light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}.get(value)


def _write_preference(mode: ft.ThemeMode) -> None:
    payload = {}
    try:
        with open(_PREFS, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        payload = {}
    payload[_KEY] = "light" if mode == ft.ThemeMode.LIGHT else "dark"
    try:
        os.makedirs(os.path.dirname(_PREFS), exist_ok=True)
        with open(_PREFS, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except OSError:
        pass


class ThemeController:
    """Aplica los temas institucionales y permite alternarlos."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.manual: ft.ThemeMode | None = _read_preference()
        self._timer: threading.Timer | None = None

    @property
    def current(self) -> ft.ThemeMode:
        return self.manual or resolve_theme()

    @property
    def is_light(self) -> bool:
        return self.current == ft.ThemeMode.LIGHT

    def apply(self) -> None:
        try:
            self.page.theme = branding.theme_light()
            self.page.dark_theme = branding.theme_dark()
            self.page.theme_mode = self.current
            self.page.update()
        except Exception:
            pass

    def start(self) -> None:
        self.apply()
        self._schedule()

    def _schedule(self) -> None:
        self._timer = threading.Timer(60, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        if self.manual is None:
            self.apply()
        self._schedule()

    def toggle(self) -> ft.ThemeMode:
        self.manual = (
            ft.ThemeMode.DARK if self.is_light else ft.ThemeMode.LIGHT
        )
        _write_preference(self.manual)
        self.apply()
        return self.manual
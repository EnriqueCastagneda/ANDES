"""Application theme: light by day (06:00-17:59), dark otherwise."""

from __future__ import annotations

import threading
from datetime import datetime

import flet as ft

DAY_START_HOUR = 6
DAY_END_HOUR = 18


def resolve_theme(now: datetime | None = None) -> ft.ThemeMode:
    """Return the theme that matches the local time."""
    moment = now or datetime.now()
    if DAY_START_HOUR <= moment.hour < DAY_END_HOUR:
        return ft.ThemeMode.LIGHT
    return ft.ThemeMode.DARK


class ThemeController:
    """Apply the time-based theme and allow a manual override.

    The controller re-checks the clock every minute so a running app switches
    automatically when the day/night boundary is crossed.
    """

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.manual: ft.ThemeMode | None = None
        self._timer: threading.Timer | None = None

    @property
    def current(self) -> ft.ThemeMode:
        return self.manual or resolve_theme()

    @property
    def is_light(self) -> bool:
        return self.current == ft.ThemeMode.LIGHT

    def apply(self) -> None:
        try:
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
        self.apply()
        return self.manual

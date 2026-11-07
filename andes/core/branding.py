"""Identidad de marca de ANDES: nombres, paleta y temas.

Los colores principales son contractuales y no deben alterarse:
- Oscuro: fondo ``#1b293d`` y texto/destaque ``#d8b56d``.
- Claro: fondo ``#f1eadc`` y texto/destaque ``#2a3f48``.
"""

from __future__ import annotations

import flet as ft

APP_NAME = "ANDES"
APP_TAGLINE = "Open Data Platform"
ACRONYM_ES = "Archivo Nacional de Datos Estadísticos y Sociales"
ACRONYM_EN = "Andean Network for Data, Evidence and Statistics"
APP_DESCRIPTION = (
    "Plataforma de acceso, integración, exploración y consulta de "
    "estadísticas y datos abiertos."
)
APP_VERSION = "2.0.1"
REPOSITORY_URL = "https://github.com/EnriqueCastagneda/ANDES"
LICENSE_NAME = "GNU General Public License v3.0 or later"

# Colores obligatorios.
DARK_BG = "#1b293d"
DARK_TEXT = "#d8b56d"
LIGHT_BG = "#f1eadc"
LIGHT_TEXT = "#2a3f48"

# Fuentes de datos base, además de los portales descubiertos en Gob.pe.
DATA_SITES = (
    (
        "Banco Central de Reserva del Perú (BCRP)",
        "https://estadisticas.bcrp.gob.pe",
    ),
    (
        "Ministerio de Economía y Finanzas (MEF) — Datos Abiertos",
        "https://datosabiertos.mef.gob.pe",
    ),
    (
        "Instituto Nacional de Estadística e Informática (INEI) — "
        "Población proyectada",
        "https://www.gob.pe/institucion/inei",
    ),
    (
        "Instituto Nacional de Estadística e Informática (INEI) — "
        "Índice temático",
        "https://www.inei.gob.pe/estadisticas-indice-tematico/",
    ),
)

# Paleta categórica accesible para gráficos (compatible con ambos temas).
CHART_COLORS = (
    "#c08a3e",
    "#2f6f7e",
    "#8c5a2b",
    "#5b8c5a",
    "#9b4d5a",
    "#4a6fa5",
    "#a67c52",
    "#3f7f6f",
)

# Rutas relativas a ``assets_dir="assets"`` (Flet antepone el directorio).
ASSETS = {
    "logo_light": "andes_logo_claro.png",
    "logo_dark": "andes_logo_oscuro.png",
    "mark_light": "andes_isotipo_claro.png",
    "mark_dark": "andes_isotipo_oscuro.png",
    "icon": "icon.png",
    "icon_dir": "icon",
}


def _scheme_dark() -> ft.ColorScheme:
    return ft.ColorScheme(
        primary=DARK_TEXT,
        on_primary=DARK_BG,
        primary_container="#3b3427",
        on_primary_container="#f0d9a4",
        secondary="#9fb3c8",
        on_secondary="#101a28",
        secondary_container="#2b3f57",
        on_secondary_container="#dbe6f2",
        tertiary="#b8a06a",
        on_tertiary="#1b293d",
        tertiary_container="#3a3221",
        on_tertiary_container="#efe0b8",
        error="#e08a8a",
        on_error="#2a1111",
        error_container="#4a2424",
        on_error_container="#f3c9c9",
        surface=DARK_BG,
        on_surface=DARK_TEXT,
        on_surface_variant="#b9c6d4",
        outline="#5b7188",
        outline_variant="#3a4f66",
        surface_container_lowest="#16222f",
        surface_container_low=DARK_BG,
        surface_container="#22334a",
        surface_container_high="#283c55",
        surface_container_highest="#30465f",
        surface_bright="#2c4159",
        surface_dim=DARK_BG,
        inverse_surface=DARK_TEXT,
        on_inverse_surface=DARK_BG,
        inverse_primary="#2a3f48",
        surface_tint=DARK_TEXT,
    )


def _scheme_light() -> ft.ColorScheme:
    return ft.ColorScheme(
        primary=LIGHT_TEXT,
        on_primary=LIGHT_BG,
        primary_container="#d7e0e3",
        on_primary_container="#1d2c33",
        secondary="#5d6f75",
        on_secondary="#ffffff",
        secondary_container="#dfe7e9",
        on_secondary_container="#2a3f48",
        tertiary="#8a6a3b",
        on_tertiary="#ffffff",
        tertiary_container="#eadfc8",
        on_tertiary_container="#4a3617",
        error="#a33a3a",
        on_error="#ffffff",
        error_container="#f2d5d5",
        on_error_container="#5a1a1a",
        surface=LIGHT_BG,
        on_surface=LIGHT_TEXT,
        on_surface_variant="#5d6f75",
        outline="#8f9b99",
        outline_variant="#c9bda6",
        surface_container_lowest="#fbf7ef",
        surface_container_low=LIGHT_BG,
        surface_container="#e8dfcd",
        surface_container_high="#ded3bd",
        surface_container_highest="#d4c8af",
        surface_bright="#faf5ea",
        surface_dim="#e3d9c5",
        inverse_surface=LIGHT_TEXT,
        on_inverse_surface=LIGHT_BG,
        inverse_primary=DARK_TEXT,
        surface_tint=LIGHT_TEXT,
    )


def theme_light() -> ft.Theme:
    """Tema claro institucional (fondo cálido, texto azul verdoso)."""
    return ft.Theme(color_scheme=_scheme_light())


def theme_dark() -> ft.Theme:
    """Tema oscuro institucional (fondo profundo, texto dorado)."""
    return ft.Theme(color_scheme=_scheme_dark())


def logo_for(theme_mode: ft.ThemeMode) -> str:
    """Logotipo horizontal con contraste correcto para el tema."""
    return ASSETS["logo_light"] if theme_mode == ft.ThemeMode.LIGHT else ASSETS["logo_dark"]


def mark_for(theme_mode: ft.ThemeMode) -> str:
    """Isotipo con contraste correcto para el tema."""
    return ASSETS["mark_light"] if theme_mode == ft.ThemeMode.LIGHT else ASSETS["mark_dark"]
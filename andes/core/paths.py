"""Filesystem paths and public endpoints."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent


def _home() -> Path:
    """Carpeta del usuario; si no hay USERPROFILE/HOME, usa el cwd."""
    try:
        return Path.home()
    except RuntimeError:
        return Path.cwd()


# Prefer the repository assets; fall back to the assets shipped in the wheel.
ASSETS_DIR = str(
    PROJECT_ROOT / "assets"
    if (PROJECT_ROOT / "assets").is_dir()
    else PACKAGE_ROOT / "assets"
)

def _user_data_dir() -> Path:
    """Directorio de datos por usuario (XDG en Linux, LocalAppData en Windows)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(
            _home() / "AppData" / "Local"
        )
        return Path(base) / "ANDES"
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "andes"
    base = os.environ.get("XDG_DATA_HOME") or str(
        _home() / ".local" / "share"
    )
    return Path(base) / "andes"


def _user_config_dir() -> Path:
    """Directorio de configuración por usuario (XDG_CONFIG_HOME en Linux)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(
            _home() / "AppData" / "Roaming"
        )
        return Path(base) / "ANDES"
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "andes"
    base = os.environ.get("XDG_CONFIG_HOME") or str(_home() / ".config")
    return Path(base) / "andes"


def _default_data_dir() -> str:
    """Prioriza variables de Flet/ANDES; en apps empaquetadas usa datos de usuario."""
    explicit = os.environ.get("ANDES_DATA_DIR")
    if explicit:
        return explicit
    storage = os.environ.get("FLET_APP_STORAGE_DATA")
    if storage:
        return storage
    if getattr(sys, "frozen", False):
        return str(_user_data_dir())
    return "data"


def _default_config_dir() -> str:
    """Configuración junto a los datos en Flet; XDG aparte en apps empaquetadas."""
    explicit = os.environ.get("ANDES_CONFIG_DIR")
    if explicit:
        return explicit
    storage = os.environ.get("FLET_APP_STORAGE_DATA")
    if storage:
        return storage
    if getattr(sys, "frozen", False):
        return str(_user_config_dir())
    return "data"


METADATA_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
DATA_DIR = _default_data_dir()
CONFIG_DIR = _default_config_dir()
OUTPUT_DIR = os.environ.get("ANDES_OUTPUT_DIR", "outputs")
METADATA_PATH = os.path.join(DATA_DIR, "metadata_bcrp.csv")

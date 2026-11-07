"""Preferencias persistentes de ANDES (tema y carpeta de guardado)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import DATA_DIR

PREFS_PATH = os.path.join(DATA_DIR, "prefs.json")


def load_prefs() -> dict:
    try:
        with open(PREFS_PATH, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_prefs(**updates) -> dict:
    payload = load_prefs()
    payload.update(updates)
    try:
        os.makedirs(os.path.dirname(PREFS_PATH) or ".", exist_ok=True)
        with open(PREFS_PATH, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return payload


def load_output_dir() -> str:
    value = load_prefs().get("output_dir")
    return str(value) if value else ""


def save_output_dir(path: str) -> None:
    save_prefs(output_dir=path)


def default_output_dir() -> str:
    """Carpeta propuesta: ANDES_OUTPUT_DIR, Downloads/ANDES, Documents/ANDES o ~/ANDES."""
    env = os.environ.get("ANDES_OUTPUT_DIR")
    if env:
        return str(Path(env).expanduser().resolve())
    home = Path.home()
    for base in (home / "Downloads", home / "Documents", home):
        if base.is_dir():
            return str(base / "ANDES")
    return str(Path.cwd() / "outputs")


def ensure_output_dir(path: str | None = None) -> str:
    """Resuelve, crea y persiste la carpeta de guardado."""
    target = path or load_output_dir() or default_output_dir()
    try:
        os.makedirs(target, exist_ok=True)
    except OSError:
        target = str(Path.cwd() / "outputs")
        os.makedirs(target, exist_ok=True)
    if load_output_dir() != target:
        save_output_dir(target)
    return target
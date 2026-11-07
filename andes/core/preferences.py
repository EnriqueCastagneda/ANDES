"""Preferencias persistentes de ANDES (tema y carpeta de guardado).

La carpeta de guardado se normaliza (variables de entorno, ``~``), se valida y
se prueba escribiendo un archivo temporal antes de persistirla. El JSON se
guarda de forma atómica para no dejarlo corrupto si la app se cierra a medias.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .paths import CONFIG_DIR, DATA_DIR, _home

PREFS_PATH = os.path.join(CONFIG_DIR, "prefs.json")

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class OutputDirError(ValueError):
    """La ruta de guardado es inválida o no se puede escribir."""


def load_prefs() -> dict:
    """Lee las preferencias; devuelve ``{}`` si no existen o están dañadas."""
    try:
        with open(PREFS_PATH, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write_json(path: str, payload: dict) -> None:
    """Escribe el JSON en un temporal y lo reemplaza de forma atómica."""
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    handle_fd, tmp = tempfile.mkstemp(dir=parent, prefix=".prefs-", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def save_prefs(**updates) -> dict:
    """Actualiza y persiste las preferencias indicadas."""
    payload = load_prefs()
    payload.update(updates)
    try:
        _atomic_write_json(PREFS_PATH, payload)
    except OSError:
        pass
    return payload


def load_output_dir() -> str:
    """Carpeta persistida, o cadena vacía si aún no se eligió."""
    value = load_prefs().get("output_dir")
    return value.strip() if isinstance(value, str) else ""


def save_output_dir(path: str) -> str:
    """Valida, crea y persiste la carpeta de guardado; devuelve su ruta."""
    target = prepare_output_dir(path)
    save_prefs(output_dir=target)
    return target


def clear_output_dir() -> None:
    """Olvida la carpeta elegida para volver a la predeterminada."""
    payload = load_prefs()
    if "output_dir" in payload:
        payload.pop("output_dir", None)
        try:
            _atomic_write_json(PREFS_PATH, payload)
        except OSError:
            pass


def normalize_output_path(path: str) -> str:
    """Convierte una ruta escrita por el usuario en una ruta absoluta."""
    raw = str(path or "").strip().strip('"').strip("'")
    if not raw:
        raise OutputDirError("La ruta está vacía.")
    if "\x00" in raw:
        raise OutputDirError("La ruta contiene caracteres no válidos.")
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if os.name == "nt":
        _validate_windows_path(expanded)
    try:
        target = Path(expanded).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise OutputDirError(f"Ruta no válida: {exc}") from exc
    return str(target)


def prepare_output_dir(path: str) -> str:
    """Crea la carpeta si falta y comprueba que se puede escribir en ella."""
    target = Path(normalize_output_path(path))
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputDirError(f"No se pudo crear la carpeta: {exc}") from exc
    if not target.is_dir():
        raise OutputDirError("La ruta apunta a un archivo, no a una carpeta.")
    _probe_writable(target)
    return str(target)


def _probe_writable(target: Path) -> None:
    try:
        handle_fd, probe = tempfile.mkstemp(prefix=".andes-", dir=target)
        os.close(handle_fd)
        os.unlink(probe)
    except OSError as exc:
        raise OutputDirError(f"La carpeta no admite escritura: {exc}") from exc


def _validate_windows_path(path: str) -> None:
    drive, rest = os.path.splitdrive(path)
    if any(char in rest for char in '<>:"|?*'):
        raise OutputDirError("La ruta contiene caracteres no permitidos en Windows.")
    for part in re.split(r"[\\/]+", rest):
        if part.split(".")[0].upper() in _WINDOWS_RESERVED:
            raise OutputDirError(f"Nombre reservado en Windows: {part}")


def default_output_dir() -> str:
    """Carpeta propuesta: ANDES_OUTPUT_DIR, Downloads/ANDES, Documents/ANDES o ~/ANDES."""
    env = os.environ.get("ANDES_OUTPUT_DIR", "").strip()
    if env:
        return normalize_output_path(env)
    home = _home()
    for base in (home / "Downloads", home / "Documents", home / "Escritorio"):
        if base.is_dir():
            return str(base / "ANDES")
    storage = os.environ.get("FLET_APP_STORAGE_DATA", "").strip()
    if storage:
        return str(Path(storage) / "exports")
    return str(home / "ANDES")


def ensure_output_dir(path: str | None = None) -> str:
    """Resuelve una carpeta escribible y la persiste.

    Si la ruta guardada ya no sirve (borrada, sin permisos, unidad ausente), se
    prueba la predeterminada y, como último recurso, una carpeta temporal local.
    """
    stored = load_output_dir()
    candidates = [path] if path else [stored, default_output_dir()]
    candidates.extend(
        [
            str(Path(DATA_DIR) / "exports"),
            str(Path(tempfile.gettempdir()) / "ANDES"),
        ]
    )
    errors: list[str] = []
    for candidate in dict.fromkeys(value for value in candidates if value):
        try:
            target = prepare_output_dir(candidate)
        except OutputDirError as exc:
            errors.append(str(exc))
            continue
        if target != stored:
            save_prefs(output_dir=target)
        return target
    detail = errors[-1] if errors else "No hay una carpeta disponible."
    raise OutputDirError(f"No se pudo preparar la carpeta de guardado: {detail}")

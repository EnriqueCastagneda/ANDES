"""Local metadata catalogue: download, load and filter."""

from __future__ import annotations

import os

import pandas as pd
import requests

from . import catalog, sources
from .http import HEADERS
from .paths import DATA_DIR, METADATA_PATH, METADATA_URL

KNOWN_CODE_COL = "Código de serie"
KNOWN_NAME_COL = "Nombre de serie"


def download_metadata():
    """Descarga el catálogo oficial de metadatos si no existe localmente."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(METADATA_PATH):
        try:
            res = requests.get(METADATA_URL, headers=HEADERS, timeout=60)
            res.raise_for_status()
            with open(METADATA_PATH, "wb") as f:
                f.write(res.content)
        except Exception as e:
            raise RuntimeError(f"Error al descargar metadatos: {e}") from e
    return METADATA_PATH


def load_metadata():
    """Carga el catálogo CSV y normaliza columnas."""
    path = download_metadata()
    df = pd.read_csv(
        path,
        sep=";",
        encoding="latin-1",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    if "Unnamed: 18" in df.columns:
        df = df.drop(columns=["Unnamed: 18"])
    df[KNOWN_CODE_COL] = df[KNOWN_CODE_COL].str.strip().str.lower()
    df[KNOWN_NAME_COL] = df[KNOWN_NAME_COL].str.strip().str.lower()
    return df



def filter_metadata(df, filters):
    """Return rows of df matching a dict of filter criteria.

    Supported keys (all optional):
      codigo, nombre, grupo            -> substring match (case-insensitive)
      categoria, fuente, frecuencia,
      grupo_publicacion, area          -> exact match
      creacion_desde/creacion_hasta    -> Fecha de creación range (YYYY-MM-DD)
      actual_desde/actual_hasta        -> Fecha de actualización range
      inicio, fin                      -> substring match on period strings
    """
    out = df
    substr = {
        "codigo": KNOWN_CODE_COL,
        "nombre": KNOWN_NAME_COL,
        "grupo": "Grupo de serie",
        "inicio": "Fecha de inicio",
        "fin": "Fecha de fin",
    }
    exact = {
        "categoria": "Categoría de serie",
        "fuente": "Fuente",
        "frecuencia": "Frecuencia",
        "grupo_publicacion": "Grupo de publicación",
        "area": "Área que publica",
        "grupo_serie": "Grupo de serie",
    }
    for key, col in substr.items():
        val = (filters.get(key) or "").strip().lower()
        if val:
            out = out[out[col].astype(str).str.lower().str.contains(val, regex=False)]
    for key, col in exact.items():
        val = (filters.get(key) or "").strip()
        if val and val not in ("Todas", "Todos"):
            out = out[out[col] == val]

    date_ranges = {
        "creacion_desde": ("Fecha de creación", ">="),
        "creacion_hasta": ("Fecha de creación", "<="),
        "actual_desde": ("Fecha de actualización", ">="),
        "actual_hasta": ("Fecha de actualización", "<="),
    }
    for key, (col, op) in date_ranges.items():
        val = (filters.get(key) or "").strip()
        if not val:
            continue
        series = pd.to_datetime(out[col], errors="coerce")
        limit = pd.to_datetime(val, errors="coerce")
        if pd.isna(limit):
            continue
        if op == ">=":
            out = out[series >= limit]
        else:
            out = out[series <= limit]
    return out


# --- Ruta rápida: catálogo SQLite + FTS5 -----------------------------------
# Mantiene los mismos nombres de columna que ``load_metadata`` para que la GUI
# y el MCP puedan cambiar de fuente sin tocar el resto del código.

_COLUMN_BY_FIELD = {
    field: column for field, column in catalog.COLUMNS.items()
}


def _as_frame(rows: list[dict]) -> pd.DataFrame:
    """Convierte filas del catálogo al DataFrame con columnas del CSV oficial."""
    columns = list(_COLUMN_BY_FIELD.values())
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)
    frame = frame.rename(columns=_COLUMN_BY_FIELD)
    frame = frame.reindex(columns=columns, fill_value="")
    frame[KNOWN_CODE_COL] = frame[KNOWN_CODE_COL].str.lower()
    frame[KNOWN_NAME_COL] = frame[KNOWN_NAME_COL].str.lower()
    return frame


_FILTER_KEYS = {
    "institucion": "institution",
    "frecuencia": "frequency",
    "categoria": "category",
    "area": "area",
    "fuente": "source",
    "grupo_serie": "group_name",
    "grupo_publicacion": "pub_group",
    "inicio": "start",
    "fin": "end",
    "creacion_desde": "created_from",
    "creacion_hasta": "created_to",
    "actual_desde": "updated_from",
    "actual_hasta": "updated_to",
}

_CATALOG_FILTERS = {
    "institution", "frequency", "category", "area", "source", "pub_group", "group_name",
    "start", "end", "created_from", "created_to", "updated_from", "updated_to",
}


def search_catalog(
    query: str = "",
    *,
    limit: int | None = 100,
    offset: int = 0,
    filters: dict | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Busca en el catálogo local (FTS5) sin descargar el CSV completo.

    Acepta los mismos filtros que ``filter_metadata`` usando las claves en
    español (``frecuencia``, ``categoria``, ``area``, ``fuente``,
    ``grupo_serie``, ``grupo_publicacion``, ``creacion_desde/hasta``,
    ``actual_desde/hasta``, ``inicio``, ``fin``) o los nombres del catálogo.

    Devuelve un DataFrame con las mismas columnas que ``load_metadata``.
    """
    options = dict(filters or {})
    options.update(kwargs)
    translated = {}
    for key, value in options.items():
        if value in (None, "", "Todas", "Todos"):
            continue
        translated[_FILTER_KEYS.get(key, key)] = value
    translated = {
        key: value
        for key, value in translated.items()
        if key in _CATALOG_FILTERS
    }

    rows = catalog.search(query, limit=limit, offset=offset, **translated)
    return _as_frame(rows)


def series_info(code: str) -> dict | None:
    """Metadatos de una serie, con las claves del CSV oficial."""
    row = catalog.get(code)
    if row is None:
        return None
    return {
        column: row[field]
        for field, column in catalog.COLUMNS.items()
        if field in row
    }


def frequency_for(codes: list[str]) -> str:
    """Deduce la frecuencia común de varios códigos desde el catálogo."""
    freqs = []
    for code in codes:
        info = catalog.get(code)
        if info is None:
            raise ValueError(f"Código de serie desconocido: {code}")
        freqs.append(info["frequency"])
    unique = list(dict.fromkeys(freqs))
    if len(unique) != 1:
        raise ValueError(
            "Las series deben compartir frecuencia; se obtuvo: " + ", ".join(unique)
        )
    return unique[0]


def catalog_frequencies() -> list[tuple[str, int]]:
    """Frecuencias disponibles y su número de series."""
    return catalog.frequencies()


def catalog_count() -> int:
    """Número total de series indexadas."""
    return catalog.count()


def catalog_values(field: str) -> list[str]:
    """Valores distintos de una columna del catálogo (para filtros de la GUI)."""
    return catalog.distinct(field)


def catalog_institutions() -> list[tuple[str, str]]:
    """Instituciones presentes en el catálogo como ``(id, nombre corto)``."""
    present = set(catalog.distinct("institution"))
    registered = [
        (source.id, source.short_name)
        for source in sources.sources()
        if not present or source.id in present
    ]
    return registered or [(source.id, source.short_name) for source in sources.sources()]


def institution_options() -> list[tuple[str, str]]:
    """Instituciones registradas, sin consultar la base (para dibujar la GUI)."""
    return [(source.id, source.short_name) for source in sources.sources()]



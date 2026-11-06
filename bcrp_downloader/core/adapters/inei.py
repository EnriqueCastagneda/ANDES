"""Población total proyectada por distrito (INEI, 2018-2026).

El adaptador descarga una vez el XLSX publicado en gob.pe, lo cachea y lo
indexa como una serie por distrito (código ``INEI-POP-<ubigeo>``). La búsqueda
es local sobre el catálogo y la descarga lee la fila del ubigeo.
"""

from __future__ import annotations

import json
import math
import os
import re
import time

import pandas as pd
import requests

from .. import catalog
from ..paths import DATA_DIR
from ..portals import spec_for

URL = (
    "https://cdn.www.gob.pe/uploads/document/file/8261096/"
    "6894980-peru-poblacion-total-proyectada-al-30-de-junio-de-cada-ano-"
    "segun-departamento-provincia-y-distrito-2018-2026.xlsx?v=1768402069"
)
CACHE_DIR = os.path.join(DATA_DIR, "inei")
YEARS = list(range(2018, 2027))
HEADERS = {"User-Agent": "Mozilla/5.0 (ANDES/2.0)"}
_YEAR_COLUMN = re.compile(r"^20(1[89]|2[0-6])$")


def _numeric(value) -> float | None:
    if isinstance(value, (int, float)) and not (
        isinstance(value, float) and math.isnan(value)
    ):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _ubigeo(value) -> str | None:
    """Normaliza el ubigeo (string '010101' o float 10101.0)."""
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d{6}", text):
            return text
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return f"{int(value):06d}"
    return None


def _year_columns(frame: pd.DataFrame) -> tuple[int, dict[int, int]]:
    """Columnas del cuadro que encabezan un año de proyección."""
    columns: dict[int, int] = {}
    for column in range(frame.shape[1]):
        for row in range(min(6, len(frame))):
            header = frame.iloc[row, column]
            if isinstance(header, str) and _YEAR_COLUMN.match(header.strip()):
                columns[column] = int(header.strip())
                break
            if isinstance(header, (int, float)) and not (
                isinstance(header, float) and math.isnan(header)
            ) and 2018 <= int(header) <= 2026:
                columns[column] = int(header)
                break
    return 0, columns


def _bounds(start: str, end: str) -> tuple[str, str]:
    """Normaliza ``YYYY`` / ``YYYY-MM`` / ``YYYY-MM-DD`` a (low, high) ISO."""
    low = re.sub(r"[^0-9-]", "", start)
    high = re.sub(r"[^0-9-]", "", end)
    if len(low) == 4:
        low = f"{low}-01"
    if len(high) == 4:
        high = f"{high}-12"
    if len(low) == 7:
        low = f"{low}-01"
    if len(high) == 7:
        high = f"{high}-01"
    return low[:10], high[:10]


class IneiAdapter:
    """Adaptador nativo de población distrital INEI."""

    institution = "inei"

    def __init__(self) -> None:
        self._spec = spec_for("inei")

    # ------------------------------------------------------------------ #
    def _cache_path(self) -> str:
        os.makedirs(CACHE_DIR, exist_ok=True)
        return os.path.join(CACHE_DIR, "poblacion_distrito.xlsx")

    def _fetch_file(self) -> str:
        path = self._cache_path()
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < 30 * 86400:
            return path
        response = requests.get(URL, headers=HEADERS, timeout=180)
        response.raise_for_status()
        with open(path, "wb") as handle:
            handle.write(response.content)
        return path

    def _load(self) -> pd.DataFrame:
        path = self._fetch_file()
        frame = pd.read_excel(path, sheet_name=0, header=None)
        year_row, year_columns = _year_columns(frame)
        rows: list[dict] = []
        department = ""
        for index in range(len(frame)):
            ubigeo = _ubigeo(frame.iloc[index, 0])
            if not ubigeo or ubigeo == "000000":
                continue
            name = frame.iloc[index, 1]
            if not isinstance(name, str) or not name.strip():
                continue
            if ubigeo.endswith("0000"):
                department = name.strip()
                continue
            if ubigeo.endswith("00"):
                continue  # provincia o departamento: solo distritos
            points: list[tuple[str, float]] = []
            for column, year in year_columns.items():
                value = _numeric(frame.iloc[index, column])
                if value is not None:
                    points.append((f"{year:04d}-01-01", value))
            if len(points) >= 2:
                rows.append(
                    {
                        "ubigeo": ubigeo,
                        "name": name.strip(),
                        "department": department,
                        "points": points,
                    }
                )
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    def _ensure_indexed(self) -> int:
        if catalog.count_prefix("INEI-POP", "inei") > 0:
            return 0
        frame = self._load()
        rows: list[dict] = []
        for _, record in frame.iterrows():
            ubigeo = record["ubigeo"]
            points = record["points"]
            start = min(point[0] for point in points)
            end = max(point[0] for point in points)
            rows.append(
                {
                    "institution": "inei",
                    "code": f"INEI-POP-{ubigeo}",
                    "category": "Población",
                    "group_name": "Población distrital",
                    "name": f"Población proyectada - {record['name']}",
                    "description": "Población total proyectada al 30 de junio",
                    "unit": "personas",
                    "source": "INEI",
                    "frequency": "Anual",
                    "pub_group": "Población",
                    "area": record.get("department") or "Población",
                    "start": start,
                    "end": end,
                    "memo": json.dumps(
                        {"kind": "inei", "ubigeo": ubigeo}, ensure_ascii=False
                    ),
                }
            )
        return catalog.upsert(rows)

    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        *,
        filters: dict | None = None,
        limit: int | None = 300,
    ) -> pd.DataFrame:
        from .. import metadata

        self._ensure_indexed()
        scoped = dict(filters or {})
        scoped["institucion"] = "inei"
        return metadata.search_catalog(
            query, filters=scoped, limit=limit
        )

    def fetch(self, codes: list[str], start: str, end: str,
              frequency: str | None = None) -> pd.DataFrame:
        low, high = _bounds(start, end)
        frame = self._load()
        frames = []
        for code in codes:
            match = re.search(r"INEI-POP-(\d{6})", code.upper())
            if not match:
                continue
            row = frame[frame["ubigeo"] == match.group(1)]
            if row.empty:
                continue
            points = [
                (period, value)
                for period, value in row.iloc[0]["points"]
                if low <= period[:10] <= high
            ]
            if not points:
                continue
            frames.append(
                pd.DataFrame(
                    {
                        "fecha": [point[0] for point in points],
                        code.upper(): [point[1] for point in points],
                    }
                )
            )
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
            columns=["fecha"]
        )

    def info(self, code: str) -> dict:
        return {
            "institution": "inei",
            "code": code,
            "source": "INEI",
            "url": URL,
            "license": "Información de carácter referencial",
            "updated": time.strftime("%Y-%m-%d"),
        }
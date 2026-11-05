"""Series anuales/trimestrales de los cuadros estadísticos del MEF.

Los cuadros son archivos .xls con matrices por año, matrices trimestrales o
columnas de años. Este módulo los normaliza a series (periodo, valor) sin
depender de servicios externos.
"""

from __future__ import annotations

import math
import os
import re

import pandas as pd

_YEAR = re.compile(r"^(19|20)\d{2}$")
_QUARTER = re.compile(r"^(I|II|III|IV)\s*T?$", re.IGNORECASE)
_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not (
        isinstance(value, float) and math.isnan(value)
    )


def _year_of(value) -> int | None:
    if _is_number(value) and 1900 <= int(value) <= 2100:
        return int(value)
    if isinstance(value, str):
        text = value.strip().replace(" ", "")
        if _YEAR.match(text):
            return int(text)
    return None


def _label_of(row: pd.Series, limit: int = 5) -> str:
    for index in range(min(limit, len(row))):
        value = row.iloc[index]
        if isinstance(value, str) and value.strip() and not _YEAR.match(value.strip()):
            return re.sub(r"\s+", " ", value.strip())
    return ""


def _annual_header(df: pd.DataFrame) -> tuple[int, dict[int, int]] | None:
    for row in range(min(20, len(df))):
        columns = {}
        for column in range(df.shape[1]):
            year = _year_of(df.iloc[row, column])
            if year:
                columns[column] = year
        if len(columns) >= 2:
            return row, columns
    return None


def _quarter_header(
    df: pd.DataFrame,
) -> tuple[int, dict[int, tuple[int, int]]] | None:
    for row in range(1, min(20, len(df))):
        columns = {}
        current_year = None
        for column in range(df.shape[1]):
            year = _year_of(df.iloc[row - 1, column])
            if year:
                current_year = year
            value = df.iloc[row, column]
            if isinstance(value, str) and current_year:
                token = re.sub(r"\s+", " ", value.strip()).upper()
                match = _QUARTER.match(token)
                if match:
                    roman = match.group(1).upper()
                    quarter = {"I": 1, "II": 2, "III": 3, "IV": 4}[roman]
                    columns[column] = (current_year, quarter)
        if len(columns) >= 4:
            return row, columns
    return None


def _vertical_years(df: pd.DataFrame) -> tuple[int, dict[int, int]] | None:
    for column in range(min(4, df.shape[1])):
        values = {}
        for row in range(len(df)):
            year = _year_of(df.iloc[row, column])
            if year:
                values[row] = year
        if len(values) >= 3:
            return column, values
    return None


def _numeric(value) -> float | None:
    if _is_number(value):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _horizontal_annual(df, header, url, title) -> list[dict]:
    row_index, columns = header
    series: list[dict] = []
    section = ""
    for row in range(row_index + 1, len(df)):
        label = _label_of(df.iloc[row])
        points = []
        for column, year in columns.items():
            number = _numeric(df.iloc[row, column])
            if number is not None:
                points.append((f"{year:04d}-01-01", number))
        if label and points:
            series.append(
                {
                    "label": label,
                    "category": section or title,
                    "frequency": "Anual",
                    "points": points,
                    "selector": {"kind": "row", "row": row},
                }
            )
        elif label and not points:
            section = label
    return series


def _horizontal_quarterly(df, header, url, title) -> list[dict]:
    row_index, columns = header
    series: list[dict] = []
    section = ""
    for row in range(row_index + 1, len(df)):
        label = _label_of(df.iloc[row])
        points = []
        for column, (year, quarter) in columns.items():
            number = _numeric(df.iloc[row, column])
            if number is not None:
                month = 3 * (quarter - 1) + 1
                points.append((f"{year:04d}-{month:02d}-01", number))
        if label and points:
            series.append(
                {
                    "label": label,
                    "category": section or title,
                    "frequency": "Trimestral",
                    "points": points,
                    "selector": {"kind": "row", "row": row},
                }
            )
        elif label and not points:
            section = label
    return series


def _vertical_annual(df, vertical, url, title) -> list[dict]:
    year_column, years = vertical
    first_row = min(years)
    headers: dict[int, str] = {}
    for column in range(year_column + 1, df.shape[1]):
        parts = []
        for row in range(0, first_row):
            value = df.iloc[row, column]
            if isinstance(value, str) and value.strip():
                parts.append(re.sub(r"\s+", " ", value.strip()))
        if parts:
            headers[column] = " - ".join(dict.fromkeys(parts))
    series = []
    for column, name in headers.items():
        points = []
        for row, year in years.items():
            number = _numeric(df.iloc[row, column])
            if number is not None:
                points.append((f"{year:04d}-01-01", number))
        if len(points) >= 2:
            series.append(
                {
                    "label": name,
                    "category": title,
                    "frequency": "Anual",
                    "points": points,
                    "selector": {"kind": "column", "column": column},
                }
            )
    return series


def extract(path: str, url: str, title: str) -> list[dict]:
    """Extrae todas las series temporales de un cuadro .xls."""
    stamp = os.path.getmtime(path)
    cached = _CACHE.get(path)
    if cached and cached[0] == stamp:
        return cached[1]

    frame = pd.read_excel(path, sheet_name=0, header=None)
    result: list[dict] = []
    annual = _annual_header(frame)
    if annual:
        result = _horizontal_annual(frame, annual, url, title)
    if not result:
        quarterly = _quarter_header(frame)
        if quarterly:
            result = _horizontal_quarterly(frame, quarterly, url, title)
    if not result:
        vertical = _vertical_years(frame)
        if vertical:
            result = _vertical_annual(frame, vertical, url, title)

    _CACHE[path] = (stamp, result)
    return result


def title_of(path: str, index: int) -> str:
    """Título legible del cuadro (primera línea con texto)."""
    try:
        frame = pd.read_excel(path, sheet_name=0, header=None, nrows=6)
    except Exception:
        return f"Cuadro {index}"
    parts = []
    for row in range(min(4, len(frame))):
        for column in range(min(3, frame.shape[1])):
            value = frame.iloc[row, column]
            if isinstance(value, str) and value.strip():
                text = re.sub(r"\s+", " ", value.strip())
                if text.lower().startswith(("cuadro", "gráfico", "grafico")):
                    continue
                parts.append(text)
                break
        if parts:
            break
    subtitle = parts[0] if parts else ""
    return f"Cuadro {index:02d} - {subtitle}" if subtitle else f"Cuadro {index:02d}"

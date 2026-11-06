"""Model Context Protocol server exposing the BCRP catalogue."""

from __future__ import annotations

from typing import Any

from ..core.api import download_series_data, export_series, find_pdf_url
from ..core.metadata import (
    KNOWN_CODE_COL,
    KNOWN_NAME_COL,
    filter_metadata,
    load_metadata,
)


def _build_server():
    """Return an MCP server instance across SDK generations."""
    try:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP

        return FastMCP("andes")
    except Exception:
        pass
    try:  # mcp 2.x renamed FastMCP to MCPServer
        from mcp.server.mcpserver import MCPServer

        return MCPServer("andes")
    except Exception:
        return None


server = _build_server()


def search_series(
    query: str,
    frequency: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search BCRP series by code or name.

    Args:
        query: Text matched against the series code and name.
        frequency: Optional exact frequency (Diaria, Mensual, ...).
        category: Optional exact category.
        limit: Maximum number of results.

    Returns:
        A list of dicts with code, name, category and frequency.
    """
    df = load_metadata()
    text = (query or "").lower()
    mask = (
        df[KNOWN_CODE_COL].str.contains(text, regex=False)
        | df[KNOWN_NAME_COL].str.contains(text, regex=False)
    )
    df = df[mask]
    filters: dict[str, str] = {}
    if frequency:
        filters["frecuencia"] = frequency
    if category:
        filters["categoria"] = category
    if filters:
        df = filter_metadata(df, filters)
    results = []
    for _, row in df.head(max(1, limit)).iterrows():
        results.append(
            {
                "code": str(row[KNOWN_CODE_COL]).upper(),
                "name": str(row[KNOWN_NAME_COL]),
                "category": str(row.get("Categoría de serie", "")),
                "frequency": str(row.get("Frecuencia", "")),
            }
        )
    return results


def get_metadata(series_code: str) -> dict[str, Any]:
    """Return the metadata of one series, including a PDF link if present."""
    df = load_metadata()
    row = df[df[KNOWN_CODE_COL] == str(series_code).strip().lower()]
    if row.empty:
        raise ValueError(f"Serie no encontrada: {series_code}")
    data = row.iloc[0]
    description = str(data.get("Descripción de la serie", ""))
    if description.lower() in ("nan", "none"):
        description = ""
    return {
        "code": str(data[KNOWN_CODE_COL]).upper(),
        "name": str(data[KNOWN_NAME_COL]),
        "category": str(data.get("Categoría de serie", "")),
        "group": str(data.get("Grupo de serie", "")),
        "frequency": str(data.get("Frecuencia", "")),
        "source": str(data.get("Fuente", "")),
        "publisher_area": str(data.get("Área que publica", "")),
        "start": str(data.get("Fecha de inicio", "")),
        "end": str(data.get("Fecha de fin", "")),
        "description": description,
        "pdf_url": find_pdf_url(description),
    }


def download_series(
    series_code: str, start_date: str, end_date: str, format: str = "csv"
) -> dict[str, Any]:
    """Download a series and return the saved path and row count."""
    df = download_series_data(series_code, start_date, end_date)
    if df.empty:
        raise ValueError(
            f"No hay datos para {series_code} entre {start_date} y {end_date}"
        )
    path = export_series(df, series_code, start_date, end_date, format.lower())
    return {"path": path, "rows": len(df), "format": format.lower()}


if server is not None:

    server.tool(name="search_series")(search_series)
    server.tool(name="get_metadata")(get_metadata)
    server.tool(name="download_series")(download_series)


def run() -> None:
    """Run the MCP server over stdio."""
    if server is None:
        raise RuntimeError("El paquete 'mcp' no está instalado.")
    server.run()

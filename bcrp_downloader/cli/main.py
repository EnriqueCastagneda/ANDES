"""Command line interface built with Typer."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

from .. import APP_NAME, APP_VERSION
from ..core.api import EXPORT_FORMATS, download_series_data, export_series
from ..core.metadata import KNOWN_CODE_COL, KNOWN_NAME_COL, filter_metadata, load_metadata

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=f"{APP_NAME} {APP_VERSION}: explora y descarga series del BCRP.",
)


def _filtered(query: str, frequency: str | None, category: str | None):
    df = load_metadata()
    mask = (
        df[KNOWN_CODE_COL].str.contains(query.lower(), regex=False)
        | df[KNOWN_NAME_COL].str.contains(query.lower(), regex=False)
    )
    df = df[mask]
    filters = {}
    if frequency:
        filters["frecuencia"] = frequency
    if category:
        filters["categoria"] = category
    if filters:
        df = filter_metadata(df, filters)
    return df


@app.command()
def search(
    query: str = typer.Argument(..., help="Texto a buscar en código o nombre."),
    frequency: str | None = typer.Option(None, "--frequency", "-f", help="Diaria, Mensual, Trimestral o Anual."),
    category: str | None = typer.Option(None, "--category", "-c", help="Categoría exacta."),
    limit: int = typer.Option(20, "--limit", "-n", help="Máximo de resultados."),
) -> None:
    """Search series by code or name."""
    df = _filtered(query, frequency, category)
    if df.empty:
        typer.echo("Sin resultados.")
        raise typer.Exit(code=1)
    for _, row in df.head(limit).iterrows():
        typer.echo(f"{row[KNOWN_CODE_COL].upper():<14} {row[KNOWN_NAME_COL][:90]}")
    total = len(df)
    if total > limit:
        typer.echo(f"... {total - limit} más ({total} en total)")


@app.command()
def download(
    series_code: str = typer.Argument(..., help="Código de la serie, p. ej. PN00001MM."),
    start: str = typer.Option(..., "--start", "-s", help="Periodo inicial (ej. 2020-1)."),
    end: str = typer.Option(..., "--end", "-e", help="Periodo final (ej. 2024-12)."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Ruta de salida."),
    fmt: str = typer.Option("csv", "--format", help="csv|json|xls|xml|txt|html."),
) -> None:
    """Download one series to a file."""
    fmt = fmt.lower()
    if fmt not in EXPORT_FORMATS.values():
        typer.echo(f"Formato no soportado: {fmt}", err=True)
        raise typer.Exit(code=2)
    df = download_series_data(series_code, start, end)
    if df.empty:
        typer.echo("No hay datos para el rango consultado.", err=True)
        raise typer.Exit(code=1)
    out_dir = str(out.parent) if out else None
    generated = export_series(df, series_code, start, end, fmt, out_dir=out_dir)
    if out and Path(generated) != out:
        shutil.move(generated, out)
        generated = str(out)
    typer.echo(f"Guardado: {generated} ({len(df)} periodos)")


@app.command()
def gui(
    web: bool = typer.Option(False, "--web", help="Abrir en el navegador."),
    port: int = typer.Option(8550, "--port", help="Puerto para el modo web."),
) -> None:
    """Launch the Flet desktop interface."""
    import flet as ft

    from ..gui.views import main as gui_main

    if web:
        ft.run(gui_main, port=port, view=ft.AppView.WEB_BROWSER)
    else:
        ft.run(gui_main)


@app.command()
def mcp() -> None:
    """Start the MCP server over stdio."""
    from ..mcp.server import run

    run()


if __name__ == "__main__":
    app()

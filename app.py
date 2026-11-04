# BCRP Downloader - explorador y descargador de series estadísticas del BCRP.
# Copyright (C) 2025 BCRP Downloader contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""BCRP Downloader: app de escritorio (Flet) para el catálogo de series del BCRP."""

from __future__ import annotations

import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from html import escape
from pathlib import Path

import pandas as pd
import requests

import flet as ft

APP_NAME = "BCRP Downloader"
APP_VERSION = "v1.0.0"
APP_DESCRIPTION = (
    "Explora el catálogo de series estadísticas del Banco Central de Reserva "
    "del Perú y descarga sus series temporales."
)
APP_STACK = "Python, Flet 1.0.5, pandas, requests"
BCRP_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
METADATA_PATH = DATA_DIR / "metadata_bcrp.csv"

METADATA_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
API_URL = (
    "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
    "{codigo}/{formato}/{inicio}/{fin}/esp"
)
FORMATS = ["csv", "json", "xls", "xml", "txt", "html"]
FREQUENCIES = ["Todos", "Diaria", "Mensual", "Trimestral", "Anual"]
MAX_RESULTS = 300
HTTP_RETRIES = 3
HTTP_TIMEOUT = 60
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (BCRP-Downloader)"}

COL_CODE = "Código de serie"
COL_NAME = "Nombre de serie"
COL_CATEGORY = "Categoría de serie"
COL_GROUP = "Grupo de serie"
COL_DESC = "Descripción de la serie"
COL_UNIT = "Unidad de medida"
COL_SOURCE = "Fuente"
COL_FREQ = "Frecuencia"
COL_PUBGROUP = "Grupo de publicación"
COL_AREA = "Área que publica"
COL_CREATED = "Fecha de creación"
COL_UPDATED = "Fecha de actualización"
COL_START = "Fecha de inicio"
COL_END = "Fecha de fin"
REQUIRED_COLUMNS = [
    COL_CODE, COL_NAME, COL_CATEGORY, COL_GROUP, COL_DESC, COL_UNIT, COL_SOURCE,
    COL_FREQ, COL_PUBGROUP, COL_AREA, COL_CREATED, COL_UPDATED, COL_START, COL_END,
]

# Tokens de diseño
BG = "#0b0b0d"
SURFACE = "#18181b"
SURFACE_INNER = "#27272a"
HOVER = "#323238"
ACCENT = "#3b82f6"
TEXT = "#fafafa"
TEXT_MUTED = "#a1a1aa"
BORDER = ft.Colors.with_opacity(0.10, ft.Colors.WHITE)
RADIUS = 12
RADIUS_LG = 16


# ---------------------------------------------------------------- HTTP

def _is_blocked_response(resp) -> bool:
    """True si la respuesta es la página HTML de bloqueo de la CDN.

    El BCRP devuelve JSON válido con Content-Type text/html: se intenta
    parsear JSON primero y, si parsea, nunca se considera bloqueo.
    """
    text = getattr(resp, "text", None)
    if text is None:
        content = getattr(resp, "content", b"") or b""
        text = content.decode("utf-8", errors="ignore")
    try:
        json.loads(text)
        return False
    except (ValueError, TypeError):
        pass
    head = text.lstrip()[:1000].lower()
    return "<html" in head or "<!doctype" in head


def _http_get(url: str, retries: int = HTTP_RETRIES, delay: float = 1.0,
              timeout: float = HTTP_TIMEOUT, check_blocked: bool = True):
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
            resp.raise_for_status()
            if check_blocked and _is_blocked_response(resp):
                raise RuntimeError("Respuesta de bloqueo de la CDN")
            return resp
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            if attempt < retries - 1 and delay:
                time.sleep(delay)
    raise RuntimeError(f"No se pudo obtener {url} tras {retries} intentos: {last_error}")


def _http_get_json(url: str, retries: int = HTTP_RETRIES, delay: float = 1.0,
                   timeout: float = HTTP_TIMEOUT) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
            resp.raise_for_status()
            try:
                return json.loads(resp.text)
            except ValueError:
                if _is_blocked_response(resp):
                    raise RuntimeError("Respuesta de bloqueo de la CDN")
                raise RuntimeError("Respuesta no es JSON válido")
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            if attempt < retries - 1 and delay:
                time.sleep(delay)
    raise RuntimeError(f"No se pudo obtener JSON tras {retries} intentos: {last_error}")


# ---------------------------------------------------------------- Metadatos

def _norm(value) -> str:
    return str(value).strip().lower()


def download_metadata(path: Path = METADATA_PATH, force: bool = False) -> Path:
    """Descarga el catálogo de metadatos solo si no existe."""
    path = Path(path)
    if path.exists() and not force:
        return path
    resp = _http_get(METADATA_URL, check_blocked=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return path


def load_metadata(path: Path = METADATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="latin-1", dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    df["_code_norm"] = df[COL_CODE].map(_norm)
    df["_name_norm"] = df[COL_NAME].map(_norm)
    return df


def _parse_meta_date(value):
    return pd.to_datetime(value, errors="coerce", dayfirst=True, format="mixed")


def parse_api_date(value: str | date | datetime) -> date:
    """Acepta YYYY-M, YYYY-MM y YYYY-MM-DD."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parts = str(value).strip().split("-")
    try:
        nums = [int(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"Fecha inválida: {value!r}") from exc
    if len(nums) == 2:
        nums.append(1)
    if len(nums) != 3:
        raise ValueError(f"Fecha inválida: {value!r}")
    return date(*nums)


def format_api_date(value) -> str:
    d = parse_api_date(value)
    return f"{d.year}-{d.month}"


def _is_all(value) -> bool:
    return value is None or str(value).strip() in ("", "Todas", "Todos")


def _in_range(series: pd.Series, start, end) -> pd.Series:
    dates = series.map(_parse_meta_date)
    mask = pd.Series(True, index=series.index)
    if start is not None:
        mask &= dates >= pd.Timestamp(start)
    if end is not None:
        mask &= dates <= pd.Timestamp(end)
    return mask


def filter_metadata(df: pd.DataFrame, text: str = "", frecuencia: str = "Todos",
                    area: str = "Todas", fuente: str = "Todas",
                    categoria: str = "Todas", grupo: str = "Todos",
                    grupo_publicacion: str = "Todos",
                    creacion_desde=None, creacion_hasta=None,
                    actualizacion_desde=None, actualizacion_hasta=None) -> pd.DataFrame:
    """Filtrado compuesto (AND)."""
    mask = pd.Series(True, index=df.index)
    query = _norm(text or "")
    if query:
        code = df["_code_norm"] if "_code_norm" in df else df[COL_CODE].map(_norm)
        name = df["_name_norm"] if "_name_norm" in df else df[COL_NAME].map(_norm)
        mask &= code.str.contains(query, regex=False) | name.str.contains(query, regex=False)
    for col, val in (
        (COL_FREQ, frecuencia), (COL_AREA, area), (COL_SOURCE, fuente),
        (COL_CATEGORY, categoria), (COL_GROUP, grupo), (COL_PUBGROUP, grupo_publicacion),
    ):
        if not _is_all(val):
            mask &= df[col].map(_norm) == _norm(val)
    if creacion_desde is not None or creacion_hasta is not None:
        mask &= _in_range(df[COL_CREATED], creacion_desde, creacion_hasta)
    if actualizacion_desde is not None or actualizacion_hasta is not None:
        mask &= _in_range(df[COL_UPDATED], actualizacion_desde, actualizacion_hasta)
    return df[mask]


def find_pdf_url(text) -> str | None:
    """Primer enlace terminado en .pdf (admite mayúsculas y query string)."""
    if not text:
        return None
    match = re.search(r"https?://[^\s\"'<>]+?\.pdf(?:\?[^\s\"'<>]*)?(?=$|[\s\"'<>)\],;])",
                      str(text), flags=re.IGNORECASE)
    return match.group(0) if match else None


# ---------------------------------------------------------------- Series y exportación

def build_api_url(codigo: str, formato: str, inicio, fin) -> str:
    return API_URL.format(codigo=codigo, formato=formato,
                          inicio=format_api_date(inicio), fin=format_api_date(fin))


def fetch_series(codigo: str, inicio, fin) -> pd.DataFrame:
    data = _http_get_json(build_api_url(codigo, "json", inicio, fin))
    periods = data.get("periods", [])
    names = [s.get("name", f"serie_{i}") for i, s in
             enumerate(data.get("config", {}).get("series", []))]
    rows = []
    for p in periods:
        values = p.get("values", [])
        row = {"Periodo": p.get("name")}
        for i, v in enumerate(values):
            row[names[i] if i < len(names) else f"valor_{i}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def export_dataframe(df: pd.DataFrame, formato: str, path: Path) -> Path:
    formato = formato.lower()
    path = Path(path)
    if formato == "xls":
        raise ValueError("XLS debe descargarse del endpoint nativo, no exportarse localmente")
    if formato not in FORMATS:
        raise ValueError(f"Formato desconocido: {formato}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if formato == "csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    elif formato == "json":
        path.write_text(json.dumps(json.loads(df.to_json(orient="records")),
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    elif formato == "txt":
        df.to_csv(path, index=False, sep="\t", encoding="utf-8")
    elif formato == "xml":
        root = ET.Element("data")
        for _, row in df.iterrows():
            item = ET.SubElement(root, "row")
            for col, val in row.items():
                tag = re.sub(r"\W+", "_", str(col)).strip("_") or "col"
                if tag[0].isdigit():
                    tag = f"_{tag}"
                ET.SubElement(item, tag).text = "" if pd.isna(val) else str(val)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    elif formato == "html":
        table = df.to_html(index=False, escape=True)
        path.write_text(
            "<!DOCTYPE html>\n<html lang=\"es\"><head><meta charset=\"utf-8\">"
            f"<title>{escape(path.stem)}</title></head><body>{table}</body></html>",
            encoding="utf-8")
    return path


def download_series(codigo: str, formato: str, inicio, fin,
                    out_dir: Path = OUTPUT_DIR) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{codigo}.{formato}"
    if formato == "xls":
        resp = _http_get(build_api_url(codigo, "xls", inicio, fin), check_blocked=False)
        if _is_blocked_response(resp):
            raise RuntimeError("Respuesta de bloqueo de la CDN")
        path.write_bytes(resp.content)
        return path
    df = fetch_series(codigo, inicio, fin)
    if df.empty:
        raise RuntimeError(f"Sin datos para {codigo} en el rango")
    return export_dataframe(df, formato, path)


# ---------------------------------------------------------------- UI

def _field_border(color) -> ft.OutlineInputBorder:
    return ft.OutlineInputBorder(border_radius=RADIUS, side=ft.BorderSide(1, color))


def _field_border_states() -> dict:
    return {
        ft.ControlState.DEFAULT: _field_border(BORDER),
        ft.ControlState.FOCUSED: _field_border(ACCENT),
    }


def main(page: ft.Page):
    page.title = APP_NAME
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 16
    page.window.width = 1280
    page.window.height = 800

    url_launcher = ft.UrlLauncher()
    page.services.append(url_launcher)

    def notify(message: str, color: str = ACCENT):
        page.show_dialog(ft.SnackBar(ft.Text(message, color=TEXT), bgcolor=color))

    try:
        download_metadata()
        meta = load_metadata()
    except Exception as exc:  # sin red ni caché
        meta = pd.DataFrame(columns=REQUIRED_COLUMNS + ["_code_norm", "_name_norm"])
        notify(f"No se pudo cargar el catálogo: {exc}", ft.Colors.RED_700)

    state = {
        "freq": "Todos", "selected": set(), "active": None, "focus": -1,
        "rows": [], "adv_open": False,
        "created": [None, None], "updated": [None, None],
        "start": date(2020, 1, 1), "end": date.today(),
    }
    adv = {"area": "Todas", "fuente": "Todas", "categoria": "Todas", "grupo": "Todos"}

    # ----- Inspector
    inspector = ft.ListView(expand=True, spacing=8, auto_scroll=False)
    pdf_slot = ft.Container()
    header_code = ft.Text("Selecciona una serie", size=16, weight=ft.FontWeight.BOLD, color=TEXT)
    header_badge = ft.Container(visible=False)

    async def open_pdf(e, url):
        try:
            await url_launcher.launch_url(url)
        except Exception as exc:
            notify(f"No se pudo abrir el PDF: {exc}", ft.Colors.RED_700)

    def show_inspector(row):
        state["active"] = row[COL_CODE] if row is not None else None
        inspector.controls.clear()
        pdf_slot.content = None
        if row is None:
            header_code.value = "Selecciona una serie"
            header_badge.visible = False
        else:
            header_code.value = row[COL_CODE]
            header_badge.content = ft.Text(row[COL_FREQ] or "-", size=11, color=TEXT)
            header_badge.visible = True
            inspector.controls.append(ft.Text(row[COL_NAME], size=14, color=TEXT,
                                              weight=ft.FontWeight.W_600))
            for col in REQUIRED_COLUMNS:
                if col in (COL_CODE, COL_NAME):
                    continue
                inspector.controls.append(ft.Column(spacing=2, controls=[
                    ft.Text(col, size=11, color=TEXT_MUTED),
                    ft.Text(row[col] or "-", size=13, color=TEXT, selectable=True),
                ]))
            pdf = find_pdf_url(row[COL_DESC])
            if pdf:
                async def handler(e, u=pdf):
                    await open_pdf(e, u)
                pdf_slot.content = ft.Button(
                    content=ft.Text("Descargar documentación PDF", color=TEXT),
                    icon=ft.Icons.PICTURE_AS_PDF, bgcolor=ft.Colors.RED_700,
                    on_click=handler)
        page.update()

    # ----- Lista
    results = ft.ListView(expand=True, spacing=8, padding=ft.Padding.only(right=6))
    count_text = ft.Text("", size=12, color=TEXT_MUTED)

    def row_by_code(code):
        sub = meta[meta[COL_CODE] == code]
        return sub.iloc[0] if len(sub) else None

    def toggle(code):
        if code in state["selected"]:
            state["selected"].discard(code)
        else:
            state["selected"].add(code)
        show_inspector(row_by_code(code))
        render_results()

    async def download_one(code):
        await run_download([code])

    def build_card(idx, row):
        code = row[COL_CODE]
        selected = code in state["selected"]
        focused = idx == state["focus"]

        def on_hover(e, c=code):
            e.control.bgcolor = HOVER if e.data in (True, "true") else (
                SURFACE_INNER if c in state["selected"] else SURFACE)
            e.control.update()

        async def dl(e, c=code):
            await download_one(c)

        return ft.Container(
            data=code, on_hover=on_hover, padding=10, border_radius=RADIUS,
            bgcolor=SURFACE_INNER if selected else SURFACE,
            border=ft.Border.all(1, ACCENT if (selected or focused) else BORDER),
            on_click=lambda e, c=code: toggle(c),
            content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                ft.Icon(ft.Icons.CHECK_BOX if selected else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                        color=ACCENT if selected else TEXT_MUTED, size=20),
                ft.Container(
                    content=ft.Text(code, size=11, color=TEXT, weight=ft.FontWeight.BOLD),
                    bgcolor=ACCENT, border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3)),
                ft.Container(expand=True, content=ft.Text(
                    row[COL_NAME], size=13, color=TEXT, max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS)),
                ft.IconButton(icon=ft.Icons.DOWNLOAD, icon_color=ACCENT, tooltip="Descargar",
                              on_click=dl),
            ]))

    def apply_filters():
        return filter_metadata(
            meta, text=search.value or "", frecuencia=state["freq"],
            area=adv["area"], fuente=adv["fuente"], categoria=adv["categoria"],
            grupo=adv["grupo"],
            creacion_desde=state["created"][0], creacion_hasta=state["created"][1],
            actualizacion_desde=state["updated"][0], actualizacion_hasta=state["updated"][1])

    def refresh(e=None):
        filtered = apply_filters()
        count_text.value = f"{len(filtered)} series" + (
            f" (mostrando {MAX_RESULTS})" if len(filtered) > MAX_RESULTS else "")
        state["rows"] = [r for _, r in filtered.head(MAX_RESULTS).iterrows()]
        state["focus"] = -1
        render_results()

    def render_results():
        results.controls = [build_card(i, r) for i, r in enumerate(state["rows"])]
        page.update()

    # ----- Buscador y píldoras
    search = ft.TextField(
        hint_text="Buscar por código o nombre…", prefix_icon=ft.Icons.SEARCH,
        filled=True, fill_color=SURFACE_INNER, color=TEXT,
        border=_field_border_states(), on_change=refresh)

    pills = ft.Row(spacing=6, wrap=True)

    def build_pills():
        pills.controls = []
        for f in FREQUENCIES:
            active = state["freq"] == f

            def click(e, f=f):
                state["freq"] = f
                build_pills()
                refresh()
            pills.controls.append(ft.Container(
                content=ft.Text(f, size=12, color=TEXT), on_click=click,
                height=32, padding=ft.Padding.symmetric(horizontal=12), border_radius=16,
                alignment=ft.Alignment.CENTER,
                bgcolor=ACCENT if active else SURFACE_INNER,
                border=ft.Border.all(1, ACCENT if active else BORDER)))

    # ----- Filtros avanzados
    def uniques(col):
        return sorted(v for v in meta[col].unique() if v) if col in meta else []

    def dropdown(label, key, col, all_label):
        def on_select(e):
            adv[key] = e.control.value or all_label
            refresh()
        return ft.Dropdown(
            label=label, value=all_label, text_size=12, color=TEXT, filled=True,
            fill_color=SURFACE_INNER, border=_field_border_states(), on_select=on_select,
            options=[ft.DropdownOption(key=all_label, text=all_label)] +
                    [ft.DropdownOption(key=v, text=v) for v in uniques(col)])

    dd_area = dropdown("Área que publica", "area", COL_AREA, "Todas")
    dd_fuente = dropdown("Fuente", "fuente", COL_SOURCE, "Todas")
    dd_cat = dropdown("Categoría de serie", "categoria", COL_CATEGORY, "Todas")
    dd_grupo = dropdown("Grupo de serie", "grupo", COL_GROUP, "Todos")

    def date_text(d):
        return d.strftime("%Y-%m-%d") if d else "—"

    def make_range_button(label, key, idx, store):
        btn = ft.Button(content=ft.Text(f"{label}: —", size=11, color=TEXT),
                        bgcolor=SURFACE_INNER, icon=ft.Icons.CALENDAR_MONTH)

        def on_change(e):
            store[key][idx] = e.control.value
            btn.content.value = f"{label}: {date_text(e.control.value)}"
            refresh()

        def open_picker(e):
            page.show_dialog(ft.DatePicker(
                value=store[key][idx], first_date=datetime(1900, 1, 1),
                last_date=datetime(2100, 12, 31), on_change=on_change))
        btn.on_click = open_picker
        return btn

    range_btns = [
        make_range_button("Creación desde", "created", 0, state),
        make_range_button("Creación hasta", "created", 1, state),
        make_range_button("Actualización desde", "updated", 0, state),
        make_range_button("Actualización hasta", "updated", 1, state),
    ]

    def clear_filters(e):
        for dd, k, label in ((dd_area, "area", "Todas"), (dd_fuente, "fuente", "Todas"),
                             (dd_cat, "categoria", "Todas"), (dd_grupo, "grupo", "Todos")):
            dd.value = label
            adv[k] = label
        state["created"] = [None, None]
        state["updated"] = [None, None]
        labels = ["Creación desde", "Creación hasta", "Actualización desde", "Actualización hasta"]
        for b, l in zip(range_btns, labels):
            b.content.value = f"{l}: —"
        refresh()

    def export_listing(e):
        try:
            fmt = fmt_dd.value if fmt_dd.value != "xls" else "csv"
            filtered = apply_filters().drop(columns=["_code_norm", "_name_norm"], errors="ignore")
            path = export_dataframe(filtered, fmt, OUTPUT_DIR / f"listado_bcrp.{fmt}")
            notify(f"Listado guardado en {path}")
        except Exception as exc:
            notify(f"Error al exportar: {exc}", ft.Colors.RED_700)

    adv_panel = ft.Container(
        visible=False, padding=12, bgcolor=SURFACE, border_radius=RADIUS,
        border=ft.Border.all(1, BORDER),
        content=ft.Column(spacing=8, controls=[
            dd_area, dd_fuente, dd_cat, dd_grupo, *range_btns,
            ft.Row(controls=[
                ft.Button(content=ft.Text("Limpiar", color=TEXT), bgcolor=SURFACE_INNER,
                          on_click=clear_filters),
                ft.Button(content=ft.Text("Descargar listado", color=TEXT), bgcolor=ACCENT,
                          icon=ft.Icons.DOWNLOAD, on_click=export_listing),
            ])]))

    def toggle_adv(e):
        state["adv_open"] = not state["adv_open"]
        adv_panel.visible = state["adv_open"]
        page.update()

    adv_btn = ft.Button(content=ft.Text("Filtros Avanzados ⚙️", color=TEXT),
                        icon=ft.Icons.TUNE, bgcolor=SURFACE_INNER, on_click=toggle_adv)

    # ----- Acerca de
    def close_about(e):
        page.pop_dialog()

    def show_about(e):
        page.show_dialog(ft.AlertDialog(
            bgcolor=SURFACE, title=ft.Text(APP_NAME, color=TEXT),
            content=ft.Column(tight=True, spacing=6, controls=[
                ft.Text(f"Versión {APP_VERSION}", color=TEXT),
                ft.Text(APP_DESCRIPTION, color=TEXT_MUTED),
                ft.Text(f"Stack: {APP_STACK}", color=TEXT_MUTED),
                ft.Text("Fuente de datos: Banco Central de Reserva del Perú", color=TEXT_MUTED),
                ft.TextButton(content=ft.Text(BCRP_URL), on_click=open_bcrp),
            ]),
            actions=[ft.TextButton(content=ft.Text("Cerrar"), on_click=close_about)]))

    async def open_bcrp(e):
        try:
            await url_launcher.launch_url(BCRP_URL)
        except Exception as exc:
            notify(f"No se pudo abrir el enlace: {exc}", ft.Colors.RED_700)

    # ----- Parámetros y descarga
    def make_date_button(key, label):
        btn = ft.Button(content=ft.Text(f"{label}: {date_text(state[key])}", color=TEXT),
                        icon=ft.Icons.CALENDAR_MONTH, bgcolor=SURFACE_INNER)

        def on_change(e):
            if e.control.value:
                state[key] = e.control.value
                btn.content.value = f"{label}: {date_text(state[key])}"
                page.update()

        def open_picker(e):
            page.show_dialog(ft.DatePicker(
                value=state[key], first_date=datetime(1900, 1, 1),
                last_date=datetime(2100, 12, 31), on_change=on_change))
        btn.on_click = open_picker
        return btn

    fmt_dd = ft.Dropdown(
        label="Formato", value="csv", text_size=12, color=TEXT, filled=True,
        fill_color=SURFACE_INNER, border=_field_border_states(),
        options=[ft.DropdownOption(key=f, text=f.upper()) for f in FORMATS])

    async def run_download(codes):
        if not codes:
            notify("Selecciona al menos una serie", ft.Colors.ORANGE_700)
            return
        ok = 0
        errors = []
        for code in codes:
            try:
                await asyncio.to_thread(
                    download_series, code, fmt_dd.value, state["start"], state["end"])
                ok += 1
            except Exception as exc:
                errors.append(f"{code}: {exc}")
        if errors:
            notify(f"{ok}/{len(codes)} guardadas. Error: {errors[0]}", ft.Colors.RED_700)
        else:
            notify(f"{ok} serie(s) guardada(s) en {OUTPUT_DIR}")

    async def on_download(e):
        codes = sorted(state["selected"]) or ([state["active"]] if state["active"] else [])
        await run_download(codes)

    cta = ft.Container(
        border_radius=RADIUS,
        shadow=ft.BoxShadow(blur_radius=16, color=ft.Colors.with_opacity(0.45, ACCENT),
                            offset=ft.Offset(0, 4)),
        content=ft.Button(
            content=ft.Text("Descargar", color=TEXT, weight=ft.FontWeight.BOLD),
            icon=ft.Icons.DOWNLOAD, bgcolor=ACCENT, on_click=on_download))

    # ----- Teclado
    async def on_key(e: ft.KeyboardEvent):
        key = str(getattr(e, "key", "")).replace(" ", "")
        rows = state["rows"]
        if not rows:
            return
        if key in ("ArrowDown", "ArrowUp"):
            step = 1 if key == "ArrowDown" else -1
            state["focus"] = max(0, min(len(rows) - 1, state["focus"] + step))
            render_results()
            try:
                await results.scroll_to(offset=max(0, state["focus"] * 64 - 120), duration=150)
            except Exception:
                pass
        elif key in ("Enter", "", "Space") and 0 <= state["focus"] < len(rows):
            toggle(rows[state["focus"]][COL_CODE])

    page.on_keyboard_event = on_key

    # ----- Layout
    def card(content, **kw):
        return ft.Container(bgcolor=SURFACE, border_radius=RADIUS_LG, padding=16,
                            border=ft.Border.all(1, BORDER), **kw)

    left = card(expand=3, content=ft.Column(
        expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=10,
        controls=[
            ft.Text(APP_NAME, size=20, weight=ft.FontWeight.BOLD, color=TEXT),
            search, pills, adv_btn, adv_panel, count_text,
            ft.Container(expand=True, content=results),
            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                ft.TextButton(content=ft.Text("Acerca de"), icon=ft.Icons.INFO_OUTLINE,
                              on_click=show_about),
                ft.Text(APP_VERSION, size=12, color=TEXT_MUTED)]),
        ]))

    right = ft.Column(
        expand=2, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=12,
        controls=[
            card(content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=10,
                controls=[
                    ft.Text("Parámetros", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
                    make_date_button("start", "Inicio"), make_date_button("end", "Fin"),
                    fmt_dd, cta])),
            card(expand=True, content=ft.Column(
                expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=8,
                controls=[
                    ft.Row(controls=[header_code, header_badge]),
                    pdf_slot,
                    ft.Container(expand=True, content=inspector),
                ])),
        ])

    header_badge.bgcolor = ACCENT
    header_badge.border_radius = 8
    header_badge.padding = ft.Padding.symmetric(horizontal=8, vertical=2)

    build_pills()
    page.add(ft.Row(expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    spacing=16, controls=[left, right]))
    refresh()


if __name__ == "__main__":
    ft.run(main)

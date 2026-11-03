import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
import pandas as pd
import flet as ft

METADATA_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
DATA_DIR = "data"
OUTPUT_DIR = "outputs"
METADATA_PATH = os.path.join(DATA_DIR, "metadata_bcrp.csv")

KNOWN_CODE_COL = "Código de serie"
KNOWN_NAME_COL = "Nombre de serie"

# Supported download formats: label -> file extension
EXPORT_FORMATS = {
    "CSV": "csv",
    "JSON": "json",
    "XLS": "xls",
    "XML": "xml",
    "TXT": "txt",
    "HTML": "html",
}

# Browser-like headers to avoid CDN blocking on the BCRP API
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _is_blocked_response(resp):
    """Detect CDN/rate-limit blocks that return HTML instead of data.

    BCRP serves valid JSON with a misleading ``Content-Type: text/html``,
    so a body that parses as JSON is never treated as a block page.
    """
    body = resp.text.lstrip()
    if body.startswith("{") or body.startswith("["):
        try:
            resp.json()
            return False
        except ValueError:
            pass
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        return True
    head = body[:200]
    return head.startswith("<!DOCTYPE html>") or head.startswith("<html")


def _http_get_json(url, max_retries=3, timeout=30):
    """GET a URL with retries, skipping CDN block pages."""
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code != 200:
                last_error = RuntimeError(f"HTTP {resp.status_code} for {url}")
                continue
            if _is_blocked_response(resp):
                last_error = RuntimeError(f"CDN block page returned for {url}")
                continue
            return resp.json()
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_error}")


def _http_get_bytes(url, max_retries=3, timeout=30):
    """GET raw bytes (e.g. a native XLS) with retries, skipping CDN blocks."""
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code != 200:
                last_error = RuntimeError(f"HTTP {resp.status_code} for {url}")
                continue
            head = resp.content.lstrip()[:200]
            ctype = (resp.headers.get("Content-Type") or "").lower()
            is_html = head.startswith(b"<!DOCTYPE") or head.startswith(b"<html")
            if is_html and "html" in ctype:
                last_error = RuntimeError(f"CDN block page returned for {url}")
                continue
            return resp.content
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_error}")


def download_metadata():
    """Descarga el catálogo oficial de metadatos si no existe localmente."""
    if not os.path.exists(METADATA_PATH):
        try:
            res = requests.get(METADATA_URL, headers=HEADERS, timeout=60)
            res.raise_for_status()
            with open(METADATA_PATH, "wb") as f:
                f.write(res.content)
        except Exception as e:
            raise RuntimeError(f"Error al descargar metadatos: {e}")
    return METADATA_PATH


def load_metadata():
    """Carga el catálogo CSV y normaliza columnas."""
    path = download_metadata()
    df = pd.read_csv(path, sep=";", encoding="latin-1")
    if "Unnamed: 18" in df.columns:
        df = df.drop(columns=["Unnamed: 18"])
    df = df.astype(str)
    df[KNOWN_CODE_COL] = df[KNOWN_CODE_COL].str.strip().str.lower()
    df[KNOWN_NAME_COL] = df[KNOWN_NAME_COL].str.strip().str.lower()
    return df


def periods_to_dataframe(data, code):
    """Convert a BCRP API JSON payload to a fecha/valor DataFrame."""
    rows = []
    for p in data.get("periods", []):
        date_val = p.get("name")
        val = p.get("values", [None])[0]
        rows.append({"fecha": date_val, code.upper(): val})
    return pd.DataFrame(rows)


def _dataframe_to_xml(df):
    """Serialize a DataFrame to XML using the standard library."""
    root = ET.Element("serie")
    for _, row in df.iterrows():
        rec = ET.SubElement(root, "periodo")
        for col in df.columns:
            el = ET.SubElement(rec, re.sub(r"[^\w]", "_", str(col)))
            el.text = str(row[col])
    return ET.tostring(root, encoding="unicode")


def _dataframe_to_html(df, code, start, end):
    """Serialize a DataFrame to a small standalone HTML page."""
    table = df.to_html(index=False, border=0)
    return (
        "<!DOCTYPE html>\n<html lang='es'>\n<head>\n<meta charset='utf-8'>\n"
        f"<title>{code.upper()} {start} - {end}</title>\n"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#1b1b1b}"
        "table{border-collapse:collapse}th,td{padding:6px 12px;border-bottom:1px solid #ddd;"
        "text-align:left}th{background:#f5f5f5}</style>\n</head>\n<body>\n"
        f"<h2>{code.upper()} ({start} - {end})</h2>\n{table}\n</body>\n</html>\n"
    )


def export_series(df, code, start, end, fmt, out_dir=None):
    """Write a series DataFrame to disk in the requested format.

    Returns the full file path. Raises ValueError for unknown formats.
    """
    if out_dir is None:
        out_dir = OUTPUT_DIR
    fmt = fmt.lower()
    if fmt == "xls":
        raise ValueError("xls handled via native endpoint")
    if fmt not in ("csv", "json", "txt", "xml", "html"):
        raise ValueError(f"Formato no soportado: {fmt}")

    safe_code = re.sub(r"[^\w\-_.]", "_", code.upper())
    filename = f"bcrp_serie_{safe_code}_{start}_to_{end}.{fmt}"
    filepath = os.path.join(out_dir, filename)

    if fmt == "csv":
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
    elif fmt == "json":
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    elif fmt == "txt":
        df.to_csv(filepath, index=False, sep="\t", encoding="utf-8-sig")
    elif fmt == "xml":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_dataframe_to_xml(df))
    elif fmt == "html":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_dataframe_to_html(df, code, start, end))
    return filepath


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


def export_table(df, basename, fmt, out_dir=None):
    """Export an arbitrary DataFrame (e.g. a metadata listing) to disk."""
    if out_dir is None:
        out_dir = OUTPUT_DIR
    fmt = fmt.lower()
    if fmt == "xls":
        raise ValueError("xls only supported for series downloads")
    if fmt not in ("csv", "json", "txt", "xml", "html"):
        raise ValueError(f"Formato no soportado: {fmt}")
    filepath = os.path.join(out_dir, f"{basename}.{fmt}")
    if fmt == "csv":
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
    elif fmt == "json":
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    elif fmt == "txt":
        df.to_csv(filepath, index=False, sep="\t", encoding="utf-8-sig")
    elif fmt == "xml":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_dataframe_to_xml(df))
    elif fmt == "html":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_dataframe_to_html(df, basename, "", ""))
    return filepath


def main(page: ft.Page):
    # --- Design tokens: dark SaaS / Bento ---
    BG = "#0b0b0d"
    SURFACE = "#18181b"
    SURFACE_2 = "#27272a"
    SURFACE_3 = "#323238"
    BORDER = ft.Colors.with_opacity(0.10, ft.Colors.WHITE)
    ACCENT = "#3b82f6"
    ACCENT_SOFT = "#3b82f626"
    ACCENT_BORDER = "#3b82f666"
    TEXT = "#fafafa"
    MUTED = "#a1a1aa"
    RADIUS = 16

    page.title = "BCRP Data Extractor"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.window.width = 1180
    page.window.height = 760
    page.window.min_width = 980
    page.window.min_height = 640
    page.padding = 20
    page.vertical_alignment = ft.MainAxisAlignment.START

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def notify(message, color="red"):
        page.show_dialog(ft.SnackBar(ft.Text(message), bgcolor=color))

    df_metadata = pd.DataFrame()
    try:
        df_metadata = load_metadata()
    except Exception as e:
        notify(f"Error al cargar metadatos: {e}")
        return

    # Estado reactivo
    selected_code = ft.Text(value="", visible=False)
    selected_row = {"container": None}

    # --- Panel Izquierdo: Catálogo ---
    # Buscador flotante con icono y foco acentuado
    search_box = ft.TextField(
        hint_text="Buscar serie, código o categoría…",
        prefix_icon=ft.Icons.SEARCH,
        text_size=14,
        filled=True,
        fill_color=SURFACE_2,
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        hint_style=ft.TextStyle(size=14, color=MUTED),
        border={
            ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                border_radius=14, side=ft.BorderSide(1, BORDER)
            ),
            ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                border_radius=14, side=ft.BorderSide(1, ACCENT)
            ),
        },
    )

    series_list_view = ft.ListView(
        expand=1,
        spacing=4,
        padding=ft.Padding.only(top=8, bottom=8),
        auto_scroll=False,
    )

    # Filtros por etiqueta: el control se crea sólo al activarse.
    active_filters = {}

    def make_inline_dd(label, column, key):
        values = sorted(df_metadata[column].dropna().astype(str).unique())
        return ft.Dropdown(
            label=label,
            value="",
            dense=True,
            enable_filter=True,
            options=[ft.dropdown.Option(key="", text="Todos")]
            + [ft.dropdown.Option(key=v, text=v) for v in values],
            on_select=lambda e: apply_filters(None),
        )

    def make_inline_search(label, column, key):
        """Barra de búsqueda desplegable sin cargar el índice completo.

        Las sugerencias se calculan sólo al escribir y se limitan a 25, así
        no se envía al cliente una lista de miles de opciones.
        """
        def apply_pick(value):
            async def pick(e):
                sb.value = value
                sb.controls = []
                try:
                    await sb.close_view()
                except Exception:
                    pass
                apply_filters(None)
            return pick

        def on_change(e):
            q = (sb.value or "").strip().lower()
            if len(q) < 2:
                sb.controls = []
                page.update()
                return
            vals = df_metadata[column].dropna().astype(str)
            matches = vals[vals.str.lower().str.contains(q, regex=False)].unique()[:25]
            sb.controls = [
                ft.ListTile(title=ft.Text(m, size=13), dense=True, on_click=apply_pick(m))
                for m in matches
            ]
            page.update()

        sb = ft.SearchBar(
            bar_hint_text=f"Buscar {label.lower()}...",
            bar_leading=ft.Icon(ft.Icons.SEARCH),
            controls=[],
            on_change=on_change,
            on_submit=lambda e: apply_filters(None),
        )
        return sb

    FILTER_SPECS = [
        # Identificación (búsqueda, sin índice)
        ("codigo", "Código de serie", "Código de serie", "search"),
        ("nombre", "Nombre de serie", "Nombre de serie", "search"),
        # Clasificación (listas desplegables)
        ("categoria", "Categoría de serie", "Categoría de serie", "dropdown"),
        ("grupo", "Grupo de serie", "Grupo de serie", "dropdown"),
        ("fuente", "Fuente", "Fuente", "dropdown"),
        ("frecuencia", "Frecuencia", "Frecuencia", "dropdown"),
        ("grupo_publicacion", "Grupo de publicación", "Grupo de publicación", "dropdown"),
        ("area", "Área que publica", "Área que publica", "dropdown"),
    ]

    def make_filter_block(key, label, column, kind):
        holder = ft.Container(visible=False)
        label_text = ft.Text(
            label,
            size=12,
            color=MUTED,
            weight=ft.FontWeight.W_500,
        )
        chip = ft.Container(
            content=label_text,
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            border_radius=20,
            bgcolor=SURFACE_2,
            border=ft.Border.all(1, BORDER),
            ink=True,
            animate=ft.Animation(140, ft.AnimationCurve.EASE_OUT),
        )

        def set_selected(selected):
            if selected:
                label_text.color = "#ffffff"
                label_text.weight = ft.FontWeight.W_600
                chip.bgcolor = ACCENT
                chip.border = ft.Border.all(1, ACCENT)
            else:
                label_text.color = MUTED
                label_text.weight = ft.FontWeight.W_500
                chip.bgcolor = SURFACE_2
                chip.border = ft.Border.all(1, BORDER)

        def on_hover(e):
            if key not in active_filters:
                chip.bgcolor = SURFACE_3 if e.data == "true" else SURFACE_2
                page.update()

        chip.on_hover = on_hover

        async def on_label_click(e):
            if key in active_filters:
                # desactivar: quitar filtro y ocultar el control
                holder.content = None
                holder.visible = False
                active_filters.pop(key, None)
                set_selected(False)
                apply_filters(None)
            else:
                # activar: crear el control sólo ahora
                if kind == "search":
                    control = make_inline_search(label, column, key)
                    holder.content = control
                    holder.visible = True
                    active_filters[key] = control
                    set_selected(True)
                    page.update()
                    try:
                        await control.open_view()
                    except Exception:
                        pass
                    return
                control = make_inline_dd(label, column, key)
                holder.content = control
                holder.visible = True
                active_filters[key] = control
                set_selected(True)
            page.update()

        chip.on_click = on_label_click
        return ft.Column([chip, holder], spacing=4)

    filter_blocks = [make_filter_block(*spec) for spec in FILTER_SPECS]

    def make_item_download(code):
        def item_download(e):
            # selecciona y descarga directamente desde la lista
            selected_code.value = code
            do_download(code)
        return item_download

    def build_listbox(df: pd.DataFrame):
        series_list_view.controls.clear()
        selected_row["container"] = None
        if df.empty:
            series_list_view.controls.append(
                ft.Container(
                    content=ft.Text("No se encontraron resultados", size=13, color=MUTED),
                    padding=ft.Padding.symmetric(vertical=24, horizontal=12),
                    alignment=ft.Alignment.CENTER,
                )
            )
            page.update()
            return

        # Mostrar filas - limitado a 300 para rendimiento
        rows_to_show = df.head(300)

        for _, row in rows_to_show.iterrows():
            code_val = str(row[KNOWN_CODE_COL]).upper()
            name_val = str(row[KNOWN_NAME_COL]).upper()
            # Bind row values now so each handler keeps its own series
            row_values = {
                "Código": code_val,
                "Nombre": name_val,
                "Categoría": str(row["Categoría de serie"]).upper(),
                "Grupo": str(row["Grupo de serie"]).upper(),
                "Frecuencia": str(row["Frecuencia"]).upper(),
                "Fuente": str(row["Fuente"]).upper(),
                "Área publica": str(row["Área que publica"]).upper(),
            }

            card = ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                code_val,
                                size=11,
                                weight=ft.FontWeight.W_600,
                                color="#bfdbfe",
                            ),
                            bgcolor=ACCENT_SOFT,
                            border=ft.Border.all(1, ACCENT_BORDER),
                            border_radius=8,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                        ),
                        ft.Container(
                            content=ft.Text(name_val, size=13, color=TEXT),
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DOWNLOAD,
                            icon_size=18,
                            icon_color=MUTED,
                            tooltip="Descargar esta serie",
                            on_click=make_item_download(str(row[KNOWN_CODE_COL])),
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                bgcolor=SURFACE_2,
                border=ft.Border.all(1, BORDER),
                border_radius=12,
                ink=True,
                animate=ft.Animation(140, ft.AnimationCurve.EASE_OUT),
            )

            def make_item_clicked(code, values, card_ref):
                def item_clicked(e):
                    selected_code.value = code
                    # Feedback inmediato: resaltar la tarjeta elegida
                    prev = selected_row["container"]
                    if prev is not None:
                        prev.bgcolor = SURFACE_2
                        prev.border = ft.Border.all(1, BORDER)
                    selected_row["container"] = card_ref
                    card_ref.bgcolor = SURFACE_3
                    card_ref.border = ft.Border.all(1, ACCENT)

                    # Inspector estructurado clave-valor
                    info_details.controls.clear()
                    info_details.controls.append(
                        ft.Row(
                            [
                                ft.Text(values["Código"], size=16, weight=ft.FontWeight.W_600, color=TEXT),
                                ft.Container(expand=True),
                                ft.Container(
                                    content=ft.Text(values["Frecuencia"], size=10, color="#bfdbfe"),
                                    bgcolor=ACCENT_SOFT,
                                    border_radius=6,
                                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        )
                    )
                    info_details.controls.append(
                        ft.Text(values["Nombre"], size=12, color=MUTED)
                    )
                    info_details.controls.append(
                        ft.Divider(height=12, thickness=1, color=BORDER)
                    )
                    for label, val in values.items():
                        if label in ("Código", "Nombre", "Frecuencia"):
                            continue
                        info_details.controls.append(
                            ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Text(label, size=12, color=MUTED),
                                        width=110,
                                    ),
                                    ft.Container(
                                        content=ft.Text(val, size=12, color=TEXT),
                                        expand=True,
                                    ),
                                ],
                                spacing=8,
                            )
                        )
                    page.update()
                return item_clicked

            def make_hover(card_ref):
                def on_hover(e):
                    if selected_row["container"] is card_ref:
                        return
                    card_ref.bgcolor = SURFACE_3 if e.data == "true" else SURFACE_2
                    page.update()
                return on_hover

            card.on_hover = make_hover(card)
            card.on_click = make_item_clicked(str(row[KNOWN_CODE_COL]), row_values, card)
            series_list_view.controls.append(card)
        page.update()

    # Construir lista al iniciar (tras declarar info_details)
    # --- Panel Derecho: Parámetros y Metadatos ---
    # Selector de fecha con calendario (tipo datetime)
    def make_date_control(hint):
        field = ft.TextField(
            hint_text=hint,
            read_only=True,
            text_size=13,
            width=130,
            filled=True,
            fill_color=SURFACE_2,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=11),
            hint_style=ft.TextStyle(size=13, color=MUTED),
            border={
                ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                    border_radius=12, side=ft.BorderSide(1, BORDER)
                ),
                ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                    border_radius=12, side=ft.BorderSide(1, ACCENT)
                ),
            },
        )
        picker = ft.DatePicker(
            first_date=datetime(1990, 1, 1),
            last_date=datetime(2035, 12, 31),
        )

        def on_pick(e):
            if picker.value:
                field.value = picker.value.strftime("%Y-%m-%d")
                page.update()

        picker.on_change = on_pick

        def open_picker(e):
            page.show_dialog(picker)

        button = ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_size=18,
            icon_color=MUTED,
            tooltip="Elegir fecha",
            on_click=open_picker,
        )
        return ft.Row(
            [field, button],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    start_control = make_date_control("Fecha inicio")
    end_control = make_date_control("Fecha fin")

    # Referencias a los campos de texto internos para leer el valor
    start_input = start_control.controls[0]
    end_input = end_control.controls[0]

    # Selector de formato de descarga
    format_dd = ft.Dropdown(
        label="Formato",
        value="CSV",
        width=140,
        dense=True,
        filled=True,
        fill_color=SURFACE_2,
        options=[ft.dropdown.Option(key=k, text=k) for k in EXPORT_FORMATS],
        border={
            ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                border_radius=12, side=ft.BorderSide(1, BORDER)
            ),
            ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                border_radius=12, side=ft.BorderSide(1, ACCENT)
            ),
        },
    )

    # Panel de detalles - inspector estructurado clave-valor
    info_details = ft.Column(
        [
            ft.Container(
                content=ft.Text(
                    "Selecciona una serie para ver sus metadatos",
                    size=12,
                    color=MUTED,
                ),
                padding=ft.Padding.symmetric(vertical=8),
            )
        ],
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
    )

    # --- Filtros avanzados: sólo fechas ---
    def make_filter_date(label):
        field = ft.TextField(
            label=label,
            dense=True,
            read_only=True,
            width=150,
            filled=True,
            fill_color=SURFACE_2,
            label_style=ft.TextStyle(size=11, color=MUTED),
            border={
                ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                    border_radius=10, side=ft.BorderSide(1, BORDER)
                ),
                ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                    border_radius=10, side=ft.BorderSide(1, ACCENT)
                ),
            },
        )
        picker = ft.DatePicker(first_date=datetime(1900, 1, 1), last_date=datetime(2035, 12, 31))

        def on_pick(e):
            if picker.value:
                field.value = picker.value.strftime("%Y-%m-%d")
                page.update()

        picker.on_change = on_pick
        button = ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_size=18,
            icon_color=MUTED,
            tooltip=label,
            on_click=lambda e: page.show_dialog(picker),
        )
        return ft.Row([field, button], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    filtro_creacion_desde = make_filter_date("Creación desde")
    filtro_creacion_hasta = make_filter_date("Creación hasta")
    filtro_actual_desde = make_filter_date("Actualización desde")
    filtro_actual_hasta = make_filter_date("Actualización hasta")

    def gather_filters():
        # Sólo los interruptores activos aportan su valor (carga perezosa)
        filters = {key: dd.value for key, dd in active_filters.items()}
        filters.update(
            {
                "creacion_desde": filtro_creacion_desde.controls[0].value,
                "creacion_hasta": filtro_creacion_hasta.controls[0].value,
                "actual_desde": filtro_actual_desde.controls[0].value,
                "actual_hasta": filtro_actual_hasta.controls[0].value,
            }
        )
        return filters

    # Aplica filtros de los desplegables + búsqueda de texto
    def apply_filters(e):
        df = filter_metadata(df_metadata, gather_filters())
        query = search_box.value.strip().lower()
        if query:
            mask = df.apply(
                lambda r: query in str(r[KNOWN_CODE_COL]) or query in str(r[KNOWN_NAME_COL]),
                axis=1,
            )
            df = df[mask]
        build_listbox(df)

    search_box.on_change = apply_filters

    # Descarga de una serie (reutilizada por el botón y por cada fila)
    def do_download(code):
        code = code.strip()
        if not code:
            notify("Selecciona una serie de la lista", ft.Colors.AMBER)
            return

        start = start_input.value.strip()
        end = end_input.value.strip()

        if not start or not end:
            notify("Elige las fechas de inicio y fin", ft.Colors.AMBER)
            return

        fmt = (format_dd.value or "CSV").lower()
        if fmt not in EXPORT_FORMATS.values():
            notify(f"Formato no soportado: {fmt}", ft.Colors.AMBER)
            return

        safe_code = re.sub(r"[^\w\-_.]", "_", code.upper())

        # XLS: BCRP entrega un .xls binario genuino sólo por su endpoint
        if fmt == "xls":
            api_url = f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/xls/{start}/{end}/esp"
            try:
                content = _http_get_bytes(api_url, max_retries=3, timeout=30)
            except Exception as ex:
                notify(f"Error API: {ex}")
                return
            filepath = os.path.join(OUTPUT_DIR, f"bcrp_serie_{safe_code}_{start}_to_{end}.xls")
            with open(filepath, "wb") as f:
                f.write(content)
            notify(f"Guardado: {filepath}", ft.Colors.GREEN)
            return

        api_url = f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}/esp"
        try:
            data = _http_get_json(api_url, max_retries=3, timeout=30)
        except Exception as ex:
            notify(f"Error API: {ex}")
            return

        if not data.get("periods", []):
            notify("No hay datos para el rango consultado", ft.Colors.AMBER)
            return

        df_result = periods_to_dataframe(data, code)
        try:
            filepath = export_series(df_result, code, start, end, fmt)
        except Exception as ex:
            notify(f"Error al exportar: {ex}")
            return

        notify(f"Guardado: {filepath}", ft.Colors.GREEN)

    def download_click(e):
        do_download(selected_code.value)

    download_btn = ft.Button(
        content="Descargar",
        icon=ft.Icons.DOWNLOAD,
        on_click=download_click,
        height=44,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            bgcolor=ACCENT,
            color="#ffffff",
            elevation=4,
            shadow_color=ACCENT_BORDER,
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_600),
        ),
    )

    # --- Menú de filtros avanzados: sólo fechas ---
    def clear_filters(e):
        for dc in (filtro_creacion_desde, filtro_creacion_hasta, filtro_actual_desde, filtro_actual_hasta):
            dc.controls[0].value = ""
        page.update()

    def download_listing(e):
        """Exporta el listado filtrado (metadatos) en el formato elegido."""
        df = filter_metadata(df_metadata, gather_filters())
        query = search_box.value.strip().lower()
        if query:
            mask = df.apply(
                lambda r: query in str(r[KNOWN_CODE_COL]) or query in str(r[KNOWN_NAME_COL]),
                axis=1,
            )
            df = df[mask]
        if df.empty:
            notify("No hay resultados para descargar", ft.Colors.AMBER)
            return
        fmt = (format_dd.value or "CSV").lower()
        if fmt == "xls":
            fmt = "csv"  # xls sólo aplica a series
        try:
            filepath = export_table(df, "bcrp_listado_filtrado", fmt)
        except Exception as ex:
            notify(f"Error al exportar: {ex}")
            return
        notify(f"Guardado: {filepath} ({len(df)} series)", ft.Colors.GREEN)

    def apply_advanced(e):
        apply_filters(None)
        page.pop_dialog()

    filter_dialog = ft.AlertDialog(
        modal=True,
        bgcolor=SURFACE,
        shape=ft.RoundedRectangleBorder(radius=16),
        title=ft.Text("Filtros por fecha", size=18, weight=ft.FontWeight.W_700, color=TEXT),
        content=ft.Container(
            width=360,
            content=ft.Column(
                [
                    ft.Text("Rango de creación", size=11, color=MUTED),
                    ft.Row([filtro_creacion_desde, filtro_creacion_hasta], spacing=12),
                    ft.Text("Rango de actualización", size=11, color=MUTED),
                    ft.Row([filtro_actual_desde, filtro_actual_hasta], spacing=12),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Limpiar", on_click=clear_filters, style=ft.ButtonStyle(color=MUTED)),
            ft.TextButton(
                "Descargar listado",
                icon=ft.Icons.FILTER_LIST,
                on_click=download_listing,
                style=ft.ButtonStyle(color=TEXT),
            ),
            ft.Button(
                "Aplicar",
                on_click=apply_advanced,
                style=ft.ButtonStyle(
                    bgcolor=ACCENT,
                    color="#ffffff",
                    shape=ft.RoundedRectangleBorder(radius=10),
                ),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def open_filters(e):
        page.show_dialog(filter_dialog)

    filter_btn = ft.OutlinedButton(
        content="Filtros por fecha",
        icon=ft.Icons.FILTER_ALT,
        on_click=open_filters,
        height=38,
        style=ft.ButtonStyle(
            color=TEXT,
            side=ft.BorderSide(1, BORDER),
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
    )

    # Construir lista al iniciar
    build_listbox(df_metadata)

    # Filtros: etiquetas que revelan su control bajo demanda
    filters_grid = ft.ResponsiveRow(filter_blocks, spacing=8, run_spacing=6)
    for block in filters_grid.controls:
        block.col = {"xs": 12, "sm": 6}

    filters_grid_box = ft.Container(
        content=ft.Column([filters_grid], scroll=ft.ScrollMode.AUTO, height=176),
        padding=ft.Padding.symmetric(horizontal=2, vertical=2),
    )

    # Layout principal: dos superficies elevadas (Bento)
    left_panel = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Catálogo de Series", size=18, weight=ft.FontWeight.W_700, color=TEXT),
                        ft.Container(expand=True),
                        ft.Text(f"{len(df_metadata):,} series", size=11, color=MUTED),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("Explora y filtra el catálogo del BCRP", size=12, color=MUTED),
                search_box,
                filters_grid_box,
                filter_btn,
                ft.Text("Resultados", size=12, color=MUTED),
                ft.Container(content=series_list_view, expand=True),
            ],
            spacing=12,
            expand=True,
        ),
        expand=3,
        padding=18,
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=RADIUS,
    )

    # Panel derecho: parámetros y metadatos
    params_card = ft.Container(
        content=ft.Column(
            [
                ft.Text("Rango de fechas", size=11, color=MUTED),
                ft.Row(
                    [start_control, end_control],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("Formato de salida", size=11, color=MUTED),
                ft.Row(
                    [format_dd, download_btn],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
        ),
        padding=14,
        bgcolor=SURFACE_2,
        border=ft.Border.all(1, BORDER),
        border_radius=12,
    )

    right_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("Parámetros", size=18, weight=ft.FontWeight.W_700, color=TEXT),
                ft.Text("Define el rango y el formato de salida", size=12, color=MUTED),
                params_card,
                ft.Text("Detalles de la serie", size=12, color=MUTED),
                ft.Container(
                    content=info_details,
                    padding=14,
                    bgcolor=SURFACE_2,
                    border=ft.Border.all(1, BORDER),
                    border_radius=12,
                    expand=True,
                ),
            ],
            spacing=12,
            expand=True,
        ),
        expand=2,
        padding=18,
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=RADIUS,
    )

    page.add(
        ft.Row([left_panel, right_panel], spacing=16, expand=True),
    )


def _sanitize_ld_library_path():
    """Drop stale library dirs that shadow system GLib/GTK.

    Tools like rig install an old libglib in ``~/.local/share/rig/lib`` and
    leave it in ``LD_LIBRARY_PATH``.  That copy lacks symbols required by the
    system libgio (``g_source_set_static_name``), which breaks GTK and the
    Flutter desktop client.  Keep every other entry untouched.
    """
    current = os.environ.get("LD_LIBRARY_PATH")
    if not current:
        return
    bad_markers = ("/.local/share/rig/lib",)
    kept = [
        p
        for p in current.split(":")
        if p and not any(marker in p for marker in bad_markers)
    ]
    os.environ["LD_LIBRARY_PATH"] = ":".join(kept)


def _filter_gdk_cursor_noise():
    """Suppress harmless Flutter/GTK teardown noise on stderr.

    The prebuilt Flet desktop client prints a few warnings that look alarming
    but are not errors:

    - ``Gdk-Message: ... Unable to load  from the cursor theme`` — Flutter asks
      GDK for a cursor with an empty name.
    - ``embedder.cc ... 'FlutterEngineRemoveView' returned 'kInvalidArguments'
      ... The implicit view cannot be removed.`` — the engine refuses to remove
      its implicit view during shutdown.
    - ``Attempted to set message handler on an FlBinaryMessenger without an
      engine`` — plugin teardown after the engine is gone.
    - ``Atk-CRITICAL ... atk_socket_embed: assertion 'plug_id != NULL' failed``
      — GTK accessibility warning at window creation.

    Every other line is forwarded unchanged.
    """
    if not sys.platform.startswith("linux"):
        return
    if not os.environ.get("WAYLAND_DISPLAY"):
        return

    noise = (
        b"Unable to load  from the cursor theme",
        b"'FlutterEngineRemoveView' returned 'kInvalidArguments'",
        b"The implicit view cannot be removed",
        b"Attempted to set message handler on an FlBinaryMessenger without an engine",
        b"atk_socket_embed: assertion 'plug_id != NULL' failed",
    )

    def is_noise(line):
        return any(token in line for token in noise)

    real_stderr_fd = os.dup(2)
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 2)
    os.close(write_fd)

    import threading

    def pump():
        with os.fdopen(read_fd, "rb", buffering=0) as reader:
            pending = b""
            for chunk in iter(lambda: reader.read(4096), b""):
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if not is_noise(line):
                        os.write(real_stderr_fd, line + b"\n")
            if pending and not is_noise(pending):
                os.write(real_stderr_fd, pending)

    # Daemon thread: never blocks interpreter shutdown; the pipe closes with
    # the process, so any final client lines are simply dropped.
    threading.Thread(target=pump, daemon=True).start()


if __name__ == "__main__":
    _sanitize_ld_library_path()
    _filter_gdk_cursor_noise()
    ft.run(main)

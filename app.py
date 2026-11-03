import io
import json
import os
import re
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
    page.title = "BCRP Data Extractor"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.window.width = 1100
    page.window.height = 720
    page.window.min_width = 900
    page.window.min_height = 600
    page.padding = 0
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

    # --- Panel Izquierdo: Catálogo ---
    # Barra de búsqueda minimalista
    search_box = ft.TextField(
        hint_text="Buscar serie, código o categoría",
        prefix_icon=ft.Icons.SEARCH,
        hint_style=ft.TextStyle(size=14),
        text_size=14,
        border=ft.OutlineInputBorder(
            border_radius=8,
            side=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        ),
    )

    series_list_view = ft.ListView(
        expand=1,
        spacing=4,
        padding=ft.Padding.only(top=8, bottom=8),
        auto_scroll=False,
    )

    # Menú de categorías
    category_dd = ft.Dropdown(
        label="Categoría",
        value="Todas",
        options=[ft.dropdown.Option(key="Todas", text="Todas las categorías")]
        + [
            ft.dropdown.Option(key=c, text=f"{c} ({n})")
            for c, n in df_metadata["Categoría de serie"].value_counts().items()
        ],
    )

    def make_item_download(code):
        def item_download(e):
            # selecciona y descarga directamente desde la lista
            selected_code.value = code
            do_download(code)
        return item_download

    def build_listbox(df: pd.DataFrame):
        series_list_view.controls.clear()
        if df.empty:
            series_list_view.controls.append(
                ft.Text("No se encontraron resultados", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
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

            def make_item_clicked(code, values):
                def item_clicked(e):
                    selected_code.value = code
                    # Actualizar panel de detalles
                    info_details.controls.clear()
                    for label, val in values.items():
                        info_details.controls.append(
                            ft.Row(
                                [
                                    ft.Text(f"{label}:", size=12, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ft.Text(val, size=12, color=ft.Colors.ON_SURFACE),
                                ],
                                spacing=4,
                            )
                        )
                    page.update()
                return item_clicked

            # Fondo plano con hover sutil, con botón de descarga directa
            series_list_view.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(
                                f"{code_val}",
                                size=13,
                                weight=ft.FontWeight.W_500,
                                color=ft.Colors.ON_SURFACE,
                            ),
                            ft.Container(
                                content=ft.Text(
                                    f" - {name_val}",
                                    size=13,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DOWNLOAD,
                                icon_size=18,
                                tooltip="Descargar esta serie",
                                on_click=make_item_download(str(row[KNOWN_CODE_COL])),
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                    border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                    ink=True,
                    on_click=make_item_clicked(str(row[KNOWN_CODE_COL]), row_values),
                )
            )
        page.update()

    # Construir lista al iniciar (tras declarar info_details)
    # --- Panel Derecho: Parámetros y Metadatos ---
    # Selector de fecha con calendario (tipo datetime)
    def make_date_control(hint):
        field = ft.TextField(
            hint_text=hint,
            read_only=True,
            text_size=14,
            width=130,
            border=ft.OutlineInputBorder(
                border_radius=8,
                side=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            ),
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
            tooltip="Elegir fecha",
            on_click=open_picker,
        )
        return ft.Row(
            [field, button],
            spacing=4,
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
        options=[ft.dropdown.Option(key=k, text=k) for k in EXPORT_FORMATS],
    )

    # Panel de detalles - tipo inspector minimalista
    info_details = ft.Column(
        [ft.Text("Selecciona una serie para ver sus metadatos", size=12, color=ft.Colors.ON_SURFACE_VARIANT)],
        spacing=4,
        scroll=ft.ScrollMode.AUTO,
    )

    # --- Menú de filtros avanzados ---
    filtro_codigo = ft.TextField(label="Código de serie", dense=True)
    filtro_nombre = ft.TextField(label="Nombre de serie", dense=True)
    filtro_grupo = ft.TextField(label="Grupo de serie", dense=True)
    filtro_inicio = ft.TextField(label="Fecha de inicio (ej. Ene-1992)", dense=True)
    filtro_fin = ft.TextField(label="Fecha de fin (ej. Dic-2025)", dense=True)

    def make_filter_dd(label, column, extra_blank="Todas"):
        values = sorted(df_metadata[column].dropna().astype(str).unique())
        return ft.Dropdown(
            label=label,
            value=extra_blank,
            dense=True,
            options=[ft.dropdown.Option(key=extra_blank, text=extra_blank)]
            + [ft.dropdown.Option(key=v, text=v) for v in values],
        )

    filtro_categoria = make_filter_dd("Categoría de serie", "Categoría de serie")
    filtro_fuente = make_filter_dd("Fuente", "Fuente")
    filtro_frecuencia = make_filter_dd("Frecuencia", "Frecuencia")
    filtro_grupo_pub = make_filter_dd("Grupo de publicación", "Grupo de publicación")
    filtro_area = make_filter_dd("Área que publica", "Área que publica")

    def make_filter_date(label):
        field = ft.TextField(label=label, dense=True, read_only=True, width=150)
        picker = ft.DatePicker(first_date=datetime(1900, 1, 1), last_date=datetime(2035, 12, 31))

        def on_pick(e):
            if picker.value:
                field.value = picker.value.strftime("%Y-%m-%d")
                page.update()

        picker.on_change = on_pick
        button = ft.IconButton(icon=ft.Icons.CALENDAR_MONTH, tooltip=label, on_click=lambda e: page.show_dialog(picker))
        return ft.Row([field, button], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    filtro_creacion_desde = make_filter_date("Creación desde")
    filtro_creacion_hasta = make_filter_date("Creación hasta")
    filtro_actual_desde = make_filter_date("Actualización desde")
    filtro_actual_hasta = make_filter_date("Actualización hasta")

    # Función de búsqueda reactiva (respeta la categoría y los filtros)
    def search_changed(e):
        query = search_box.value.strip().lower()
        category = category_dd.value
        df = df_metadata
        if category and category != "Todas":
            df = df[df["Categoría de serie"] == category]
        if query:
            mask = df.apply(
                lambda r: query in str(r[KNOWN_CODE_COL]) or query in str(r[KNOWN_NAME_COL]),
                axis=1,
            )
            df = df[mask]
        build_listbox(df)

    search_box.on_change = search_changed
    category_dd.on_select = search_changed

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
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            bgcolor=ft.Colors.SURFACE,
            color=ft.Colors.ON_SURFACE,
        ),
        height=40,
    )

    # --- Menú de filtros avanzados (diálogo) ---
    def gather_filters():
        return {
            "codigo": filtro_codigo.value,
            "nombre": filtro_nombre.value,
            "grupo": filtro_grupo.value,
            "inicio": filtro_inicio.value,
            "fin": filtro_fin.value,
            "categoria": filtro_categoria.value,
            "fuente": filtro_fuente.value,
            "frecuencia": filtro_frecuencia.value,
            "grupo_publicacion": filtro_grupo_pub.value,
            "area": filtro_area.value,
            "creacion_desde": filtro_creacion_desde.controls[0].value,
            "creacion_hasta": filtro_creacion_hasta.controls[0].value,
            "actual_desde": filtro_actual_desde.controls[0].value,
            "actual_hasta": filtro_actual_hasta.controls[0].value,
        }

    def apply_filters(e):
        df = filter_metadata(df_metadata, gather_filters())
        # resetear el buscador y el desplegable de categoría rápido
        search_box.value = ""
        category_dd.value = "Todas"
        build_listbox(df)
        page.pop_dialog()

    def clear_filters(e):
        for f in (filtro_codigo, filtro_nombre, filtro_grupo, filtro_inicio, filtro_fin):
            f.value = ""
        for d in (filtro_categoria, filtro_fuente, filtro_frecuencia, filtro_grupo_pub, filtro_area):
            d.value = "Todas"
        for dc in (filtro_creacion_desde, filtro_creacion_hasta, filtro_actual_desde, filtro_actual_hasta):
            dc.controls[0].value = ""
        page.update()

    def download_listing(e):
        """Exporta el listado filtrado (metadatos) en el formato elegido."""
        df = filter_metadata(df_metadata, gather_filters())
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

    filter_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Filtros de series", size=18, weight=ft.FontWeight.W_600),
        content=ft.Container(
            width=520,
            content=ft.Column(
                [
                    filtro_codigo,
                    filtro_nombre,
                    filtro_grupo,
                    filtro_categoria,
                    filtro_grupo_pub,
                    filtro_fuente,
                    filtro_frecuencia,
                    filtro_area,
                    ft.Row([filtro_inicio, filtro_fin], spacing=12),
                    ft.Row([filtro_creacion_desde, filtro_creacion_hasta], spacing=12),
                    ft.Row([filtro_actual_desde, filtro_actual_hasta], spacing=12),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                height=420,
            ),
        ),
        actions=[
            ft.TextButton("Limpiar", on_click=clear_filters),
            ft.TextButton("Descargar listado", icon=ft.Icons.FILTER_LIST, on_click=download_listing),
            ft.Button("Aplicar", on_click=apply_filters),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def open_filters(e):
        page.show_dialog(filter_dialog)

    filter_btn = ft.OutlinedButton(
        content="Filtros avanzados",
        icon=ft.Icons.FILTER_ALT,
        on_click=open_filters,
        height=40,
    )

    # Construir lista al iniciar
    build_listbox(df_metadata)

    # Layout principal: split vista abierta estilo "open plane"
    # Panel izquierdo: catálogo (60%)
    left_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("Catálogo de Series", size=20, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE),
                ft.Container(
                    content=category_dd,
                    padding=ft.Padding.only(bottom=4),
                ),
                ft.Container(
                    content=search_box,
                    padding=ft.Padding.only(bottom=4),
                ),
                ft.Container(
                    content=filter_btn,
                    padding=ft.Padding.only(bottom=4),
                ),
                ft.Text("Resultados", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Container(
                    content=series_list_view,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=8,
                    expand=True,
                    bgcolor=ft.Colors.SURFACE,
                ),
            ],
            expand=True,
        ),
        expand=3,
        padding=ft.Padding(16, 16, 12, 16),
    )

    # Panel derecho: parámetros y detalles (40%)
    right_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("Parámetros y Metadatos", size=20, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Rango de fechas", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                            ft.Row(
                                [start_control, end_control],
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [format_dd, download_btn],
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Divider(height=24, thickness=1, color=ft.Colors.OUTLINE_VARIANT),
                            ft.Text("Detalles de la serie", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                            ft.Container(
                                content=info_details,
                                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                                border_radius=8,
                                padding=ft.Padding(12, 8),
                                expand=True,
                            ),
                        ],
                        expand=True,
                    ),
                    expand=True,
                ),
            ],
            expand=True,
        ),
        expand=2,
        padding=ft.Padding(12, 16, 16, 16),
    )

    # Divisor vertical delgado
    divider = ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT, thickness=1)

    page.add(
        ft.Row([left_panel, divider, right_panel], spacing=0, expand=True),
    )


if __name__ == "__main__":
    ft.run(main)

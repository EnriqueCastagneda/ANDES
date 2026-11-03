import os
import re
import requests
import pandas as pd
import flet as ft

METADATA_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
DATA_DIR = "data"
OUTPUT_DIR = "outputs"
METADATA_PATH = os.path.join(DATA_DIR, "metadata_bcrp.csv")

KNOWN_CODE_COL = "Código de serie"
KNOWN_NAME_COL = "Nombre de serie"

# Browser-like headers to avoid CDN blocking on the BCRP API
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _is_blocked_response(resp):
    """Detect CDN/rate-limit blocks that return HTML instead of data."""
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        return True
    body = resp.text[:200].lstrip()
    return body.startswith("<!DOCTYPE html>") or body.startswith("<html")


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
        border_radius=8,
        height=40,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=14,
    )

    series_list_view = ft.ListView(
        expand=1,
        spacing=4,
        padding=ft.Padding.only(top=8, bottom=8),
        auto_scroll=False,
    )

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

            def make_item_clicked(code):
                def item_clicked(e):
                    selected_code.value = code
                    # Actualizar panel de detalles
                    info_details.controls.clear()
                    # Metadatos esenciales en formato clave-valor
                    details_items = [
                        ("Código", code.upper()),
                        ("Nombre", str(row[KNOWN_NAME_COL]).upper()),
                        ("Categoría", str(row["Categoría de serie"]).upper()),
                        ("Grupo", str(row["Grupo de serie"]).upper()),
                        ("Frecuencia", str(row["Frecuencia"]).upper()),
                        ("Fuente", str(row["Fuente"]).upper()),
                        ("Área publica", str(row["Área que publica"]).upper()),
                    ]
                    for label, val in details_items:
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

            # Fondo plano con hover sutil
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
                            ft.Text(f" - {name_val}", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                    ink=True,
                    on_click=make_item_clicked(str(row[KNOWN_CODE_COL])),
                )
            )
        page.update()

    # Construir lista al iniciar (tras declarar info_details)
    # --- Panel Derecho: Parámetros y Metadatos ---
    # Campo de fechas estilo minimalista
    start_input = ft.TextField(
        hint_text="2020-1",
        width=200,
        text_size=14,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )
    end_input = ft.TextField(
        hint_text="2026-12",
        width=200,
        text_size=14,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    # Panel de detalles - tipo inspector minimalista
    info_details = ft.Column(
        [ft.Text("Selecciona una serie para ver sus metadatos", size=12, color=ft.Colors.ON_SURFACE_VARIANT)],
        spacing=4,
        scroll=ft.ScrollMode.AUTO,
    )

    # Función de búsqueda reactiva
    def search_changed(e):
        query = search_box.value.strip().lower()
        if not query:
            build_listbox(df_metadata)
            return
        mask = df_metadata.apply(
            lambda r: query in str(r[KNOWN_CODE_COL]) or query in str(r[KNOWN_NAME_COL]),
            axis=1,
        )
        filtered_df = df_metadata[mask]
        build_listbox(filtered_df)

    search_box.on_change = search_changed

    # Botón de descarga - el único elemento con color fuerte (acento)
    def download_click(e):
        code = selected_code.value.strip()
        if not code:
            notify("Selecciona una serie de la lista", ft.Colors.AMBER)
            return

        start = start_input.value.strip()
        end = end_input.value.strip()

        if not start or not end:
            notify("Ingresa rango de fechas inicio y fin", ft.Colors.AMBER)
            return

        api_url = f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}/esp"
        try:
            data = _http_get_json(api_url, max_retries=3, timeout=30)
        except Exception as ex:
            notify(f"Error API: {ex}")
            return

        periods = data.get("periods", [])
        if not periods:
            notify("No hay datos para el rango consultado", ft.Colors.AMBER)
            return

        # Construir DataFrame fecha/valor
        rows = []
        for p in periods:
            date_val = p.get("name")
            val = p.get("values", [None])[0]
            rows.append({"fecha": date_val, code.upper(): val})

        df_result = pd.DataFrame(rows)
        safe_code = re.sub(r"[^\w\-_.]", "_", code.upper())
        filename = f"bcrp_serie_{safe_code}_{start}_to_{end}.csv"
        filepath = os.path.join(OUTPUT_DIR, filename)
        df_result.to_csv(filepath, index=False, encoding="utf-8-sig")

        notify(f"Guardado: {filepath}", ft.Colors.GREEN)

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

    # Construir lista al iniciar
    build_listbox(df_metadata)

    # Layout principal: split vista abierta estilo "open plane"
    # Panel izquierdo: catálogo (60%)
    left_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("Catálogo de Series", size=20, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE),
                ft.Container(
                    content=search_box,
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
                                [start_input, end_input],
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            download_btn,
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

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


def download_metadata():
    """Descarga el catálogo oficial de metadatos si no existe localmente."""
    if not os.path.exists(METADATA_PATH):
        try:
            res = requests.get(METADATA_URL)
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
    page.window_width = 1100
    page.window_height = 720
    page.window_min_width = 900
    page.window_min_height = 600
    page.padding = 0
    page.vertical_alignment = ft.MainAxisAlignment.START

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df_metadata = pd.DataFrame()
    try:
        df_metadata = load_metadata()
    except Exception as e:
        page.snack_bar = ft.SnackBar(ft.Text(f"Error al cargar metadatos: {e}"), bgcolor="red")
        page.snack_bar.open = True
        page.update()
        return

    # Estado reactivo
    selected_code = ft.Text(value="", visible=False)

    # --- Panel Izquierdo: Catálogo ---
    # Barra de búsqueda minimalista
    search_box = ft.TextField(
        hint_text="Buscar serie, código o categoría",
        prefix_icon=ft.icons.SEARCH,
        border_radius=8,
        height=40,
        border_color=ft.colors.OUTLINE_VARIANT,
        focused_border_color=ft.colors.PRIMARY,
        text_size=14,
    )

    series_list_view = ft.ListView(
        expand=1,
        spacing=4,
        padding=ft.padding.only(top=8, bottom=8),
        auto_scroll=False,
    )

    def build_listbox(df: pd.DataFrame):
        series_list_view.controls.clear()
        if df.empty:
            series_list_view.controls.append(
                ft.Text("No se encontraron resultados", size=12, color=ft.colors.on_surface_variant)
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
                                    ft.Text(f"{label}:", size=12, weight=ft.FontWeight.W_500, color=ft.colors.on_surface_secondary),
                                    ft.Text(val, size=12, color=ft.colors.on_surface),
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
                                color=ft.colors.on_surface,
                            ),
                            ft.Text(f" - {name_val}", size=13, color=ft.colors.on_surface_variant),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CenterAlignment,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border=ft.border.only(bottom=ft.border.BorderSide(1, ft.colors.outline_variant)),
                    ink=True,
                    on_click=make_item_clicked(str(row[KNOWN_CODE_COL])),
                )
            )
        page.update()

    # Construir lista al iniciar
    build_listbox(df_metadata)

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

    # --- Panel Derecho: Parámetros y Metadatos ---
    # Campo de fechas estilo minimalista
    start_input = ft.TextField(
        hint_text="2020-1",
        width=200,
        text_size=14,
        border_color=ft.colors.OUTLINE_VARIANT,
        focused_border_color=ft.colors.PRIMARY,
    )
    end_input = ft.TextField(
        hint_text="2026-12",
        width=200,
        text_size=14,
        border_color=ft.colors.OUTLINE_VARIANT,
        focused_border_color=ft.colors.PRIMARY,
    )

    # Panel de detalles - tipo inspector minimalista
    info_details = ft.Column(
        [ft.Text("Selecciona una serie para ver sus metadatos", size=12, color=ft.colors.on_surface_variant)],
        spacing=4,
        scroll=ft.ScrollMode.AUTO,
    )

    # Botón de descarga - el único elemento con color fuerte (acento)
    def download_click(e):
        code = selected_code.value.strip()
        if not code:
            page.snack_bar = ft.SnackBar(
                ft.Text("Selecciona una serie de la lista", bgcolor="amber"),
                open=True,
            )
            page.update()
            return

        start = start_input.value.strip()
        end = end_input.value.strip()

        if not start or not end:
            page.snack_bar = ft.SnackBar(
                ft.Text("Ingresa rango de fechas inicio y fin", bgcolor="amber"),
                open=True,
            )
            page.update()
            return

        api_url = f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}/esp"
        try:
            resp = requests.get(api_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Error API: {ex}"), bgcolor="red", open=True)
            page.update()
            return

        periods = data.get("periods", [])
        if not periods:
            page.snack_bar = ft.SnackBar(
                ft.Text("No hay datos para el rango consultado", bgcolor="amber"), open=True
            )
            page.update()
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

        page.snack_bar = ft.SnackBar(
            ft.Text(f"Guardado: {filepath}", bgcolor="green"), open=True
        )
        page.update()

    download_btn = ft.ElevatedButton(
        text="Descargar",
        icon=ft.icons.DOWNLOAD,
        on_click=download_click,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            bgcolor=ft.colors.SURFACE,
            color=ft.colors.on_surface,
        ),
        height=40,
    )

    # Layout principal: split vista abierta estilo "open plane"
    # Panel izquierdo: catálogo (60%)
    left_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("Catálogo de Series", size=20, weight=ft.FontWeight.W_600, color=ft.colors.on_surface),
                ft.Container(
                    content=search_box,
                    padding=ft.padding.only(bottom=4),
                ),
                ft.Text("Resultados", size=12, color=ft.colors.on_surface_secondary),
                ft.Container(
                    content=series_list_view,
                    border=ft.border.all(1, ft.colors.outline_variant),
                    border_radius=8,
                    expand=True,
                    bgcolor=ft.colors.surface,
                ),
            ],
            expand=True,
        ),
        expand=3,
        padding=ft.padding(16, 16, 12, 16),
    )

    # Panel derecho: parámetros y detalles (40%)
    right_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("Parámetros y Metadatos", size=20, weight=ft.FontWeight.W_600, color=ft.colors.on_surface),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Rango de fechas", size=12, color=ft.colors.on_surface_secondary),
                            ft.Row(
                                [start_input, end_input],
                                spacing=12,
                                vertical_alignment=ft.CenterAlignment,
                            ),
                            download_btn,
                            ft.Divider(height=24, thickness=1, color=ft.colors.outline_variant),
                            ft.Text("Detalles de la serie", size=12, color=ft.colors.on_surface_secondary),
                            ft.Container(
                                content=info_details,
                                border=ft.border.all(1, ft.colors.outline_variant),
                                border_radius=8,
                                padding=ft.padding(12, 8),
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
        padding=ft.padding(12, 16, 16, 16),
    )

    # Divisor vertical delgado
    divider = ft.VerticalDivider(width=1, color=ft.colors.outline_variant, thickness=1)

    page.add(
        ft.Row([left_panel, divider, right_panel], spacing=0, expand=True),
    )


if __name__ == "__main__":
    ft.run(main)
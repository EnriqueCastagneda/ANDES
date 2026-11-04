"""Flet user interface for BCRP Downloader."""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime

import flet as ft
import pandas as pd

from .. import APP_NAME, APP_VERSION
from ..core.api import (
    EXPORT_FORMATS,
    export_series,
    export_table,
    find_pdf_url,
    periods_to_dataframe,
)
from ..core.http import _http_get_bytes, _http_get_json
from ..core.metadata import (
    KNOWN_CODE_COL,
    KNOWN_NAME_COL,
    filter_metadata,
    load_metadata,
)
from ..core.paths import DATA_DIR, OUTPUT_DIR
from .theme import ThemeController


def main(page: ft.Page):
    # --- Design tokens: dark SaaS / Bento ---
    # Semantic Material 3 roles: they resolve per page.theme_mode.
    BG = ft.Colors.SURFACE_CONTAINER_LOW
    SURFACE = ft.Colors.SURFACE
    SURFACE_2 = ft.Colors.SURFACE_CONTAINER
    SURFACE_3 = ft.Colors.SURFACE_CONTAINER_HIGH
    BORDER = ft.Colors.OUTLINE_VARIANT
    ACCENT = ft.Colors.PRIMARY
    ACCENT_SOFT = ft.Colors.PRIMARY_CONTAINER
    ACCENT_BORDER = ft.Colors.PRIMARY
    TEXT = ft.Colors.ON_SURFACE
    MUTED = ft.Colors.ON_SURFACE_VARIANT
    ON_ACCENT = ft.Colors.ON_PRIMARY
    BADGE_TEXT = ft.Colors.ON_PRIMARY_CONTAINER
    RADIUS = 16

    page.title = APP_NAME
    page.theme = ft.Theme(color_scheme_seed="#3b82f6")
    page.dark_theme = ft.Theme(color_scheme_seed="#3b82f6")
    page.bgcolor = BG
    page.window.width = 1180
    page.window.height = 760
    page.window.min_width = 980
    page.window.min_height = 640
    page.padding = 20
    page.vertical_alignment = ft.MainAxisAlignment.START

    theme_controller = ThemeController(page)
    theme_controller.start()

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Notificaciones: toasts cronológicos + historial de sesión ---
    notifications = []
    unread = {"count": 0}
    toast_state = {"running": False}
    toast_column = ft.Column([], spacing=8, width=360)
    toast_container = ft.Container(
        content=toast_column, right=20, top=20, width=360
    )
    copied_bubble = ft.Container(
        content=ft.Text(
            "Copied!",
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SECONDARY_CONTAINER,
        ),
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        border=ft.Border.all(1, BORDER),
        border_radius=20,
        padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        right=0,
        bottom=34,
        visible=False,
        opacity=0,
        offset=ft.Offset(0, -0.2),
        animate_opacity=180,
        animate_offset=180,
        shadow=ft.BoxShadow(
            blur_radius=12,
            color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
            offset=ft.Offset(0, 4),
        ),
    )
    toast_stack = ft.Stack([toast_container], expand=True)
    try:
        page.overlay.append(toast_stack)
    except Exception:
        pass
    bubble_state = {"generation": 0}

    def _accent_for(color):
        if color in (ft.Colors.GREEN, ft.Colors.AMBER, ft.Colors.ERROR):
            return color
        if isinstance(color, str) and color.lower() in ("red", "error"):
            return ft.Colors.ERROR
        return ACCENT

    def _relative_time(moment):
        seconds = int((datetime.now() - moment).total_seconds())
        if seconds < 5:
            return "hace unos segundos"
        if seconds < 60:
            return f"hace {seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"hace {minutes} min"
        hours = minutes // 60
        if hours < 24:
            return f"hace {hours} h"
        return moment.strftime("%d/%m %H:%M")

    def _drain_toasts():
        """Remove the oldest toast first, keeping strict FIFO order."""
        while True:
            if not toast_column.controls:
                toast_state["running"] = False
                if not toast_column.controls:
                    return
                toast_state["running"] = True
                continue
            time.sleep(3.5)
            if not toast_column.controls:
                continue
            first = toast_column.controls[0]
            try:
                first.opacity = 0
                first.offset = ft.Offset(0.18, 0)
                refresh(first)
            except Exception:
                pass
            time.sleep(0.25)
            if toast_column.controls:
                toast_column.controls.pop(0)
            refresh(toast_column)

    def _record_notification(message, color):
        notifications.append(
            {"message": message, "color": color, "time": datetime.now()}
        )
        unread["count"] += 1

    def show_copied_bubble():
        """Show a small themed bubble above the About modal, then fade out."""
        bubble_state["generation"] += 1
        token = bubble_state["generation"]
        copied_bubble.visible = True
        copied_bubble.opacity = 1
        copied_bubble.offset = ft.Offset(0, 0)
        refresh(copied_bubble)

        def hide():
            time.sleep(1.4)
            if token != bubble_state["generation"]:
                return
            copied_bubble.opacity = 0
            copied_bubble.offset = ft.Offset(0, -0.2)
            refresh(copied_bubble)
            time.sleep(0.22)
            if token == bubble_state["generation"]:
                copied_bubble.visible = False
                refresh(copied_bubble)

        page.run_thread(hide)

    def notify(message, color="red"):
        _record_notification(message, color)
        accent = _accent_for(color)
        toast = ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=4, height=36, bgcolor=accent, border_radius=2),
                    ft.Text(message, size=12, color=TEXT, expand=True),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            bgcolor=SURFACE_2,
            border=ft.Border.all(1, BORDER),
            border_radius=12,
            shadow=ft.BoxShadow(
                blur_radius=12,
                color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
                offset=ft.Offset(0, 4),
            ),
            animate_opacity=220,
            animate_offset=220,
            opacity=0,
            offset=ft.Offset(0.18, 0),
        )
        toast_column.controls.append(toast)
        refresh(toast_column)
        toast.opacity = 1
        toast.offset = ft.Offset(0, 0)
        refresh(toast)
        update_bell()
        if not toast_state["running"]:
            toast_state["running"] = True
            page.run_thread(_drain_toasts)

    # El catálogo se carga en segundo plano para no bloquear la UI.
    df_metadata = pd.DataFrame()
    metadata_state = {"ready": False}

    # Servicios: abrir enlaces externos y portapapeles.
    url_launcher = ft.UrlLauncher()
    clipboard = ft.Clipboard()
    try:
        page.services.extend([url_launcher, clipboard])
    except Exception:
        pass

    # Estado reactivo
    selected_code = ft.Text(value="", visible=False)

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

    # La lista tiene su propio scroll; el pie del panel queda fijo debajo.
    series_list_view = ft.ListView(
        expand=1,
        spacing=4,
        auto_scroll=False,
    )

    # Selector de frecuencia mutuamente excluyente (pills)
    FREQ_OPTIONS = ["Todos", "Diaria", "Mensual", "Trimestral", "Anual"]
    freq_state = {"value": "Todos"}
    freq_pills = []

    ui_state = {"mounted": False}

    def refresh(*controls):
        """Patch only the given controls once the page is mounted."""
        if ui_state["mounted"]:
            for control in controls:
                try:
                    control.update()
                except Exception:
                    page.update()
        else:
            page.update()

    def make_frequency_selector():
        row = ft.Row(spacing=8, wrap=False)
        for option in FREQ_OPTIONS:
            text = ft.Text(option, size=12, color=MUTED, weight=ft.FontWeight.W_500)
            pill = ft.Container(
                content=text,
                height=34,
                padding=ft.Padding.symmetric(horizontal=14, vertical=0),
                alignment=ft.Alignment.CENTER,
                border_radius=17,
                bgcolor=SURFACE_2,
                border=ft.Border.all(1, BORDER),
                ink=True,
                animate=ft.Animation(140, ft.AnimationCurve.EASE_OUT),
            )
            freq_pills.append((option, pill, text))

            def make_click(value):
                def on_click(e):
                    set_frequency(value)
                    apply_filters(None)
                return on_click

            pill.on_click = make_click(option)
            row.controls.append(pill)
        return row

    frequency_selector = make_frequency_selector()

    def set_frequency(value, repaint=True):
        freq_state["value"] = value
        for opt, p, t in freq_pills:
            active = opt == value
            p.bgcolor = ACCENT if active else SURFACE_2
            p.border = ft.Border.all(1, ACCENT if active else BORDER)
            t.color = ON_ACCENT if active else MUTED
            t.weight = ft.FontWeight.W_600 if active else ft.FontWeight.W_500
        if repaint and freq_pills:
            refresh(*(p for _, p, _ in freq_pills))

    set_frequency("Todos", repaint=False)

    def make_item_download(code):
        def item_download(e):
            do_download(code)
        return item_download

    # Estado de selección múltiple y foco de teclado
    selected_codes = set()
    focused = {"index": -1}
    visible_cards = []

    def toggle_selection(entry):
        code = entry["code"]
        if code in selected_codes:
            selected_codes.discard(code)
        else:
            selected_codes.add(code)

    def apply_entry_style(entry):
        card = entry["card"]
        if entry["code"] in selected_codes:
            card.bgcolor = SURFACE_3
            card.border = ft.Border.all(1, ACCENT)
            entry["checkbox"].value = True
        else:
            card.bgcolor = SURFACE_2
            if entry["index"] == focused["index"]:
                card.border = ft.Border.all(1, ft.Colors.PRIMARY)
            else:
                card.border = ft.Border.all(1, BORDER)
            entry["checkbox"].value = False

    def restyle_cards():
        for entry in visible_cards:
            apply_entry_style(entry)

    def build_listbox(df: pd.DataFrame):
        series_list_view.controls.clear()
        visible_cards.clear()
        if df.empty:
            focused["index"] = -1
            series_list_view.controls.append(
                ft.Container(
                    content=ft.Text("No se encontraron resultados", size=13, color=MUTED),
                    padding=ft.Padding.symmetric(vertical=24, horizontal=12),
                    alignment=ft.Alignment.CENTER,
                )
            )
            refresh(series_list_view)
            return

        # Mostrar filas - limitado a 300 para rendimiento
        rows_to_show = df.head(300)

        for idx, (_, row) in enumerate(rows_to_show.iterrows()):
            code_raw = str(row[KNOWN_CODE_COL])
            code_val = code_raw.upper()
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
                "Inicio": str(row["Fecha de inicio"]),
                "Fin": str(row["Fecha de fin"]),
                "Unidad": str(row["Unidad de medida"]),
                "Descripción": "" if str(row["Descripción de la serie"]).lower() in ("nan", "none", "") else str(row["Descripción de la serie"]),
            }

            checkbox = ft.Checkbox(
                value=code_raw in selected_codes,
                width=28,
                height=28,
                visual_density=ft.VisualDensity.COMPACT,
                fill_color=ACCENT,
                check_color=ON_ACCENT,
                shape=ft.RoundedRectangleBorder(radius=5),
                tooltip="Seleccionar serie",
            )

            card = ft.Container(
                content=ft.Row(
                    [
                        checkbox,
                        ft.Container(
                            content=ft.Text(
                                code_val,
                                size=11,
                                weight=ft.FontWeight.W_600,
                                color=BADGE_TEXT,
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
                            on_click=make_item_download(code_raw),
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

            entry = {
                "code": code_raw,
                "values": row_values,
                "card": card,
                "checkbox": checkbox,
                "index": idx,
            }

            def make_checkbox_change(entry_ref):
                def on_change(e):
                    if e.control.value:
                        selected_codes.add(entry_ref["code"])
                    else:
                        selected_codes.discard(entry_ref["code"])
                    apply_entry_style(entry_ref)
                    refresh(entry_ref["card"])
                    update_master_state()
                return on_change

            checkbox.on_change = make_checkbox_change(entry)

            def make_click(entry_ref):
                def on_click(e):
                    # Clic simple: sólo mostrar metadatos, sin cambiar selección.
                    previous = focused["index"]
                    focused["index"] = entry_ref["index"]
                    selected_code.value = entry_ref["code"]
                    show_details(entry_ref["values"])
                    for idx in {previous, entry_ref["index"]}:
                        if 0 <= idx < len(visible_cards):
                            apply_entry_style(visible_cards[idx])
                            refresh(visible_cards[idx]["card"])
                return on_click

            def make_double_tap(entry_ref):
                def on_double_tap(e):
                    # Doble clic: alternar selección múltiple.
                    previous = focused["index"]
                    focused["index"] = entry_ref["index"]
                    toggle_selection(entry_ref)
                    for idx in {previous, entry_ref["index"]}:
                        if 0 <= idx < len(visible_cards):
                            apply_entry_style(visible_cards[idx])
                            refresh(visible_cards[idx]["card"])
                return on_double_tap

            def make_hover(entry_ref):
                def on_hover(e):
                    if entry_ref["code"] in selected_codes:
                        return
                    entry_ref["card"].bgcolor = SURFACE_3 if e.data == "true" else SURFACE_2
                    refresh(entry_ref["card"])
                return on_hover

            card.on_hover = make_hover(entry)
            gesture = ft.GestureDetector(
                content=card,
                on_tap=make_click(entry),
                on_double_tap=make_double_tap(entry),
            )
            visible_cards.append(entry)
            series_list_view.controls.append(gesture)

        if focused["index"] < 0 or focused["index"] >= len(visible_cards):
            focused["index"] = 0
        restyle_cards()
        update_master_state()
        refresh(series_list_view)

    # Construir lista al iniciar (tras declarar info_details)
    # --- Panel Derecho: Parámetros y Metadatos ---
    # Selector de fecha con calendario (tipo datetime)
    ES_LOCALE = ft.Locale(language_code="es", country_code="ES")

    def make_date_control(hint):
        field = ft.TextField(
            hint_text=hint,
            read_only=True,
            text_size=13,
            width=110,
            filled=True,
            fill_color=SURFACE_2,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=11),
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
            locale=ES_LOCALE,
            help_text="Seleccionar fecha",
            cancel_text="Cancelar",
            confirm_text="Aceptar",
            field_hint_text="aaaa-mm-dd",
            field_label_text=hint,
            error_invalid_text="Fecha no válida",
            error_format_text="Formato: aaaa-mm-dd",
        )

        def on_pick(e):
            if picker.value:
                field.value = picker.value.strftime("%Y-%m-%d")
                refresh(field)

        picker.on_change = on_pick

        def open_picker(e):
            page.show_dialog(picker)

        def clear_date(e):
            field.value = ""
            picker.value = None
            refresh(field)

        calendar_btn = ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_size=18,
            icon_color=MUTED,
            tooltip="Elegir fecha",
            width=32,
            height=32,
            on_click=open_picker,
        )
        clear_btn = ft.IconButton(
            icon=ft.Icons.CLEAR,
            icon_size=16,
            icon_color=MUTED,
            tooltip="Borrar fecha",
            width=32,
            height=32,
            on_click=clear_date,
        )
        return ft.Row(
            [field, calendar_btn, clear_btn],
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
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    def show_details(values):
        """Render the structured key-value inspector for one series."""
        info_details.controls.clear()
        info_details.controls.append(
            ft.Row(
                [
                    ft.Text(values["Código"], size=16, weight=ft.FontWeight.W_600, color=TEXT),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text(values["Frecuencia"], size=10, color=BADGE_TEXT),
                        bgcolor=ACCENT_SOFT,
                        border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
        info_details.controls.append(ft.Text(values["Nombre"], size=12, color=MUTED))
        info_details.controls.append(ft.Divider(height=12, thickness=1, color=BORDER))
        for label, val in values.items():
            if label in ("Código", "Nombre", "Frecuencia", "Descripción"):
                continue
            info_details.controls.append(
                ft.Row(
                    [
                        ft.Container(content=ft.Text(label, size=12, color=MUTED), width=110),
                        ft.Container(content=ft.Text(val, size=12, color=TEXT), expand=True),
                    ],
                    spacing=8,
                )
            )
        if values.get("Descripción"):
            info_details.controls.append(ft.Divider(height=8, thickness=1, color=BORDER))
            info_details.controls.append(
                ft.Text("Descripción", size=11, weight=ft.FontWeight.W_600, color=MUTED)
            )
            info_details.controls.append(
                ft.Text(values["Descripción"], size=12, color=TEXT, selectable=True)
            )
            pdf_url = find_pdf_url(values["Descripción"])
            if pdf_url:
                async def open_pdf(e, url=pdf_url):
                    try:
                        await url_launcher.launch_url(url)
                    except Exception as ex:
                        notify(f"No se pudo abrir el PDF: {ex}", ft.Colors.AMBER)

                info_details.controls.append(
                    ft.Button(
                        content="Descargar documentación PDF",
                        icon=ft.Icons.PICTURE_AS_PDF,
                        on_click=open_pdf,
                        height=38,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.ERROR,
                            color=ft.Colors.ON_ERROR,
                            elevation=2,
                            shadow_color=ft.Colors.with_opacity(0.4, ft.Colors.ERROR),
                            shape=ft.RoundedRectangleBorder(radius=10),
                            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_600),
                        ),
                    )
                )

        refresh(info_details)

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
        picker = ft.DatePicker(
            first_date=datetime(1900, 1, 1),
            last_date=datetime(2035, 12, 31),
            locale=ES_LOCALE,
            help_text="Seleccionar fecha",
            cancel_text="Cancelar",
            confirm_text="Aceptar",
            field_hint_text="aaaa-mm-dd",
            field_label_text=label,
            error_invalid_text="Fecha no válida",
            error_format_text="Formato: aaaa-mm-dd",
        )

        def on_pick(e):
            if picker.value:
                field.value = picker.value.strftime("%Y-%m-%d")
                refresh(field)

        picker.on_change = on_pick

        def clear_date(e):
            field.value = ""
            picker.value = None
            refresh(field)

        calendar_btn = ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_size=18,
            icon_color=MUTED,
            tooltip=label,
            width=32,
            height=32,
            on_click=lambda e: page.show_dialog(picker),
        )
        clear_btn = ft.IconButton(
            icon=ft.Icons.CLEAR,
            icon_size=16,
            icon_color=MUTED,
            tooltip=f"Borrar {label.lower()}",
            width=32,
            height=32,
            on_click=clear_date,
        )
        return ft.Row(
            [field, calendar_btn, clear_btn],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    filtro_creacion_desde = make_filter_date("Creación desde")
    filtro_creacion_hasta = make_filter_date("Creación hasta")
    filtro_actual_desde = make_filter_date("Actualización desde")
    filtro_actual_hasta = make_filter_date("Actualización hasta")

    def gather_filters():
        filters = {"frecuencia": freq_state["value"]}
        try:
            filters.update(
                {
                    "area": adv_area.value,
                    "fuente": adv_fuente.value,
                    "categoria": adv_categoria.value,
                    "grupo_serie": adv_grupo.value,
                }
            )
        except NameError:
            pass
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
        if not metadata_state["ready"]:
            return
        df = filter_metadata(df_metadata, gather_filters())
        query = search_box.value.strip().lower()
        if query:
            mask = df[KNOWN_CODE_COL].str.contains(
                query, regex=False
            ) | df[KNOWN_NAME_COL].str.contains(query, regex=False)
            df = df[mask]
        build_listbox(df)

    search_state = {"generation": 0}

    async def debounced_filter():
        search_state["generation"] += 1
        token = search_state["generation"]
        await asyncio.sleep(0.25)
        if token == search_state["generation"]:
            apply_filters(None)

    def on_search_change(e):
        page.run_task(debounced_filter)

    search_box.on_change = on_search_change

    # Descarga de una serie (reutilizada por el botón y por cada fila)
    def do_download(code, silent=False):
        code = code.strip()
        if not code:
            if not silent:
                notify("Selecciona una serie de la lista", ft.Colors.AMBER)
            return None

        start = start_input.value.strip()
        end = end_input.value.strip()

        if not start or not end:
            if not silent:
                notify("Elige las fechas de inicio y fin", ft.Colors.AMBER)
            return None

        fmt = (format_dd.value or "CSV").lower()
        if fmt not in EXPORT_FORMATS.values():
            if not silent:
                notify(f"Formato no soportado: {fmt}", ft.Colors.AMBER)
            return None

        safe_code = re.sub(r"[^\w\-_.]", "_", code.upper())

        # XLS: BCRP entrega un .xls binario genuino sólo por su endpoint
        if fmt == "xls":
            api_url = f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/xls/{start}/{end}/esp"
            try:
                content = _http_get_bytes(api_url, max_retries=3, timeout=30)
            except Exception as ex:
                if not silent:
                    notify(f"Error API: {ex}")
                return None
            filepath = os.path.join(OUTPUT_DIR, f"bcrp_serie_{safe_code}_{start}_to_{end}.xls")
            with open(filepath, "wb") as f:
                f.write(content)
            if not silent:
                notify(f"Guardado: {filepath}", ft.Colors.GREEN)
            return filepath

        api_url = f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}/esp"
        try:
            data = _http_get_json(api_url, max_retries=3, timeout=30)
        except Exception as ex:
            if not silent:
                notify(f"Error API: {ex}")
            return None

        if not data.get("periods", []):
            if not silent:
                notify("No hay datos para el rango consultado", ft.Colors.AMBER)
            return None

        df_result = periods_to_dataframe(data, code)
        try:
            filepath = export_series(df_result, code, start, end, fmt)
        except Exception as ex:
            if not silent:
                notify(f"Error al exportar: {ex}")
            return None

        if not silent:
            notify(f"Guardado: {filepath}", ft.Colors.GREEN)
        return filepath

    download_state = {"running": False}
    progress_bar = ft.ProgressBar(
        value=0,
        color=ACCENT,
        bgcolor=SURFACE_3,
        height=6,
        visible=False,
    )
    progress_text = ft.Text("", size=11, color=MUTED, visible=False)
    progress_box = ft.Column(
        [progress_text, progress_bar],
        spacing=6,
        visible=False,
    )

    def download_click(e):
        if download_state["running"]:
            return
        codes = (
            list(selected_codes)
            if selected_codes
            else ([selected_code.value] if selected_code.value else [])
        )
        if not codes:
            notify("Selecciona una serie de la lista", ft.Colors.AMBER)
            return
        if not start_input.value.strip() or not end_input.value.strip():
            notify("Elige las fechas de inicio y fin", ft.Colors.AMBER)
            return

        total = len(codes)
        download_state["running"] = True
        download_btn.disabled = True
        progress_box.visible = True
        progress_text.visible = True
        progress_bar.visible = True
        progress_bar.value = 0 if total > 1 else None
        progress_text.value = f"Preparando {total} serie(s)…"
        refresh(download_btn, progress_box)

        def worker():
            saved = failed = 0
            for index, code in enumerate(codes, start=1):
                progress_text.value = f"Descargando serie {index} de {total}…"
                progress_bar.value = index / total if total > 1 else None
                refresh(progress_bar, progress_text)
                if do_download(code, silent=True):
                    saved += 1
                else:
                    failed += 1
            download_state["running"] = False
            download_btn.disabled = False
            progress_box.visible = False
            refresh(download_btn, progress_box)
            if total == 1:
                msg = "Serie descargada" if saved else "No se pudo descargar la serie"
                color = ft.Colors.GREEN if saved else ft.Colors.AMBER
            else:
                msg = f"Descargadas {saved} series"
                if failed:
                    msg += f" ({failed} fallidas)"
                color = ft.Colors.GREEN if saved else ft.Colors.AMBER
            notify(msg, color)

        page.run_thread(worker)

    download_btn = ft.Button(
        content="Descargar",
        icon=ft.Icons.DOWNLOAD,
        on_click=download_click,
        height=44,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            bgcolor=ACCENT,
            color=ON_ACCENT,
            elevation=4,
            shadow_color=ACCENT_BORDER,
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_600),
        ),
    )

    # --- Filtros avanzados colapsables ---
    def make_adv_dd(label, column):
        # The catalogue may still be loading when the UI is built.
        values = (
            sorted(df_metadata[column].dropna().astype(str).unique())
            if column in df_metadata.columns
            else []
        )
        return ft.Dropdown(
            label=label,
            value="",
            dense=True,
            filled=True,
            fill_color=SURFACE,
            text_size=12,
            label_style=ft.TextStyle(size=11, color=MUTED),
            options=[ft.dropdown.Option(key="", text="Todos")]
            + [ft.dropdown.Option(key=v, text=v) for v in values],
            on_select=lambda e: apply_filters(None),
            border={
                ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                    border_radius=10, side=ft.BorderSide(1, BORDER)
                ),
                ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                    border_radius=10, side=ft.BorderSide(1, ACCENT)
                ),
            },
        )

    adv_area = make_adv_dd("Área que publica", "Área que publica")
    adv_fuente = make_adv_dd("Fuente", "Fuente")
    adv_categoria = make_adv_dd("Categoría de serie", "Categoría de serie")
    adv_grupo = make_adv_dd("Grupo de serie", "Grupo de serie")

    def clear_filters(e):
        for dd in (adv_area, adv_fuente, adv_categoria, adv_grupo):
            dd.value = ""
        for dc in (filtro_creacion_desde, filtro_creacion_hasta, filtro_actual_desde, filtro_actual_hasta):
            dc.controls[0].value = ""
        apply_filters(None)

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

    adv_grid = ft.ResponsiveRow(
        [adv_area, adv_fuente, adv_categoria, adv_grupo],
        spacing=10,
        run_spacing=10,
    )
    for ctrl in adv_grid.controls:
        ctrl.col = {"xs": 12, "sm": 6}

    advanced_panel = ft.Container(
        visible=False,
        content=ft.Column(
            [
                adv_grid,
                ft.Text("Rango de creación", size=11, color=MUTED),
                ft.Row([filtro_creacion_desde, filtro_creacion_hasta], spacing=10),
                ft.Text("Rango de actualización", size=11, color=MUTED),
                ft.Row([filtro_actual_desde, filtro_actual_hasta], spacing=10),
                ft.Row(
                    [
                        ft.TextButton("Limpiar", on_click=clear_filters, style=ft.ButtonStyle(color=MUTED)),
                        ft.TextButton(
                            "Descargar listado",
                            icon=ft.Icons.FILTER_LIST,
                            on_click=download_listing,
                            style=ft.ButtonStyle(color=TEXT),
                        ),
                    ],
                    spacing=4,
                ),
            ],
            spacing=10,
        ),
        padding=14,
        bgcolor=SURFACE_2,
        border=ft.Border.all(1, BORDER),
        border_radius=12,
    )

    filter_btn = ft.OutlinedButton(
        content="Filtros Avanzados ⚙️",
        icon=ft.Icons.TUNE,
        height=38,
        style=ft.ButtonStyle(
            color=TEXT,
            side=ft.BorderSide(1, BORDER),
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
    )

    def toggle_advanced(e):
        showing = not advanced_panel.visible
        advanced_panel.visible = showing
        filter_btn.style = ft.ButtonStyle(
            color=ACCENT if showing else TEXT,
            side=ft.BorderSide(1, ACCENT if showing else BORDER),
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        page.update()

    filter_btn.on_click = toggle_advanced

    # --- Selección maestra (sólo con filtros activos) ---
    master_checkbox = ft.Checkbox(
        value=False,
        disabled=True,
        width=28,
        height=28,
        visual_density=ft.VisualDensity.COMPACT,
        fill_color=ACCENT,
        check_color=ON_ACCENT,
        shape=ft.RoundedRectangleBorder(radius=5),
        tooltip="Seleccionar todos los resultados filtrados",
    )
    selection_text = ft.Text("", size=11, color=MUTED)

    def has_active_filters():
        """True when search, frequency, advanced filters or dates are set."""
        if (search_box.value or "").strip():
            return True
        if freq_state["value"] != "Todos":
            return True
        for dropdown in (adv_area, adv_fuente, adv_categoria, adv_grupo):
            if (dropdown.value or "").strip():
                return True
        for control in (
            filtro_creacion_desde,
            filtro_creacion_hasta,
            filtro_actual_desde,
            filtro_actual_hasta,
        ):
            if (control.controls[0].value or "").strip():
                return True
        return False

    def update_master_state():
        active = has_active_filters()
        master_checkbox.disabled = not active
        master_checkbox.value = bool(
            active
            and visible_cards
            and all(entry["code"] in selected_codes for entry in visible_cards)
        )
        selection_text.value = (
            f"{len(selected_codes)} seleccionada(s)" if selected_codes else ""
        )
        refresh(master_checkbox, selection_text)

    def on_master_change(e):
        if not has_active_filters():
            master_checkbox.value = False
            refresh(master_checkbox)
            return
        select = bool(e.control.value)
        for entry in visible_cards:
            if select:
                selected_codes.add(entry["code"])
            else:
                selected_codes.discard(entry["code"])
            apply_entry_style(entry)
        refresh(series_list_view)
        update_master_state()

    master_checkbox.on_change = on_master_change

    # Placeholder mientras el catálogo se carga en segundo plano.
    series_list_view.controls.append(
        ft.Container(
            content=ft.Text("Cargando catálogo…", size=13, color=MUTED),
            padding=ft.Padding.symmetric(vertical=24, horizontal=12),
            alignment=ft.Alignment.CENTER,
        )
    )

    # Navegación por teclado: flechas mueven el foco, Enter/Espacio marca
    async def on_keyboard(e):
        raw = e.key or ""
        key = raw.replace(" ", "").lower()
        if key == "escape" and history_state.get("open"):
            close_history()
            return
        if not visible_cards:
            return
        if key in ("arrowdown", "arrowup"):
            step = 1 if key == "arrowdown" else -1
            new_index = max(0, min(len(visible_cards) - 1, focused["index"] + step))
            if new_index != focused["index"]:
                previous = focused["index"]
                focused["index"] = new_index
                for idx in {previous, new_index}:
                    if 0 <= idx < len(visible_cards):
                        apply_entry_style(visible_cards[idx])
                        refresh(visible_cards[idx]["card"])
                try:
                    await series_list_view.scroll_to(delta=step * 64, duration=120)
                except Exception:
                    pass
        elif key == "enter" or raw == " " or key in ("space", "spacebar"):
            idx = focused["index"]
            if 0 <= idx < len(visible_cards):
                entry = visible_cards[idx]
                toggle_selection(entry)
                selected_code.value = entry["code"]
                show_details(entry["values"])
                apply_entry_style(entry)
                refresh(entry["card"])

    page.on_keyboard_event = on_keyboard

    # --- Acerca de ---
    async def open_bcrp_docs(e):
        try:
            await url_launcher.launch_url(
                "https://estadisticas.bcrp.gob.pe/estadisticas/series/"
            )
        except Exception:
            pass

    async def copy_contact(e):
        """Copy the author email and show the 'Copied!' micro-bubble."""
        try:
            await clipboard.set("EnriqueCastagneda@protonmail.com")
        except Exception:
            pass
        _record_notification("Correo copiado al portapapeles", ft.Colors.GREEN)
        update_bell()
        show_copied_bubble()

    about_email = ft.TextButton(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.MAIL_OUTLINE, size=14, color=ACCENT),
                ft.Text(
                    "EnriqueCastagneda@protonmail.com",
                    size=11,
                    color=ACCENT,
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        on_click=copy_contact,
        style=ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            overlay_color=ft.Colors.with_opacity(0.08, ACCENT),
        ),
        tooltip="Copiar correo al portapapeles",
    )
    email_with_bubble = ft.Stack(
        [about_email, copied_bubble],
        clip_behavior=ft.ClipBehavior.NONE,
    )

    about_dialog = ft.AlertDialog(
        modal=True,
        bgcolor=SURFACE,
        shape=ft.RoundedRectangleBorder(radius=16),
        title=ft.Row(
            [
                ft.Icon(ft.Icons.INFO_OUTLINE, color=ACCENT, size=20),
                ft.Text("Acerca de", size=18, weight=ft.FontWeight.W_700, color=TEXT),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Container(
            width=400,
            content=ft.Column(
                [
                    ft.Text(APP_NAME, size=16, weight=ft.FontWeight.W_700, color=TEXT),
                    ft.Text(f"Versión {APP_VERSION}", size=12, color=MUTED),
                    ft.Divider(height=16, thickness=1, color=BORDER),
                    ft.Text(
                        "Explorador y extractor de series estadísticas del Banco "
                        "Central de Reserva del Perú. Busca, filtra y descarga "
                        "metadatos y series históricas en CSV, JSON, XLS, XML, "
                        "TXT o HTML.",
                        size=12,
                        color=TEXT,
                    ),
                    ft.Divider(height=12, thickness=1, color=BORDER),
                    ft.Text(
                        "By Enrique Castañeda",
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=TEXT,
                    ),
                    email_with_bubble,
                    ft.Text(
                        "Stack: Python · Flet 1.0.5 · pandas · requests",
                        size=11,
                        color=MUTED,
                    ),
                    ft.Text(
                        "Fuente de datos: Banco Central de Reserva del Perú",
                        size=11,
                        color=MUTED,
                    ),
                ],
                spacing=8,
            ),
        ),
        actions=[
            ft.TextButton(
                "Sitio del BCRP",
                icon=ft.Icons.LINK,
                on_click=open_bcrp_docs,
                style=ft.ButtonStyle(color=TEXT),
            ),
            ft.Button(
                "Cerrar",
                on_click=lambda e: page.pop_dialog(),
                style=ft.ButtonStyle(
                    bgcolor=ACCENT,
                    color=ON_ACCENT,
                    shape=ft.RoundedRectangleBorder(radius=10),
                ),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def toggle_theme(e):
        mode = theme_controller.toggle()
        e.control.icon = (
            ft.Icons.LIGHT_MODE if mode == ft.ThemeMode.LIGHT else ft.Icons.DARK_MODE
        )
        page.update()

    history_state = {"open": False}

    bell_btn = ft.IconButton(
        icon=ft.Icons.NOTIFICATIONS_ROUNDED,
        icon_size=20,
        icon_color=MUTED,
        tooltip="Notificaciones",
    )

    def update_bell():
        count = unread["count"]
        bell_btn.tooltip = (
            f"Notificaciones ({count})" if count else "Notificaciones"
        )
        refresh(bell_btn)

    def close_history(e=None):
        if not history_state["open"]:
            return
        history_state["open"] = False
        page.pop_dialog()
        page.update()

    def open_notifications(e):
        history_state["open"] = True
        unread["count"] = 0
        update_bell()
        items = []
        if not notifications:
            items.append(
                ft.Text("Sin notificaciones en esta sesión.", size=12, color=MUTED)
            )
        else:
            for entry in reversed(notifications):
                accent = _accent_for(entry["color"])
                items.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    width=6,
                                    height=6,
                                    border_radius=3,
                                    bgcolor=accent,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(entry["message"], size=12, color=TEXT),
                                        ft.Text(
                                            _relative_time(entry["time"]),
                                            size=10,
                                            color=MUTED,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        bgcolor=SURFACE_2,
                        border=ft.Border.all(1, BORDER),
                        border_radius=10,
                    )
                )
        history_dialog = ft.AlertDialog(
            modal=True,
            on_dismiss=lambda ev: history_state.update(open=False),
            bgcolor=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.NOTIFICATIONS_ROUNDED, color=ACCENT, size=20),
                    ft.Text(
                        "Notificaciones",
                        size=18,
                        weight=ft.FontWeight.W_700,
                        color=TEXT,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    items,
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                    height=360,
                ),
            ),
            actions=[
                ft.TextButton(
                    "Cerrar",
                    on_click=close_history,
                    style=ft.ButtonStyle(color=MUTED),
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(history_dialog)

    bell_btn.on_click = open_notifications

    footer = ft.Row(
        [
            ft.TextButton(
                "Acerca de",
                icon=ft.Icons.INFO_OUTLINE,
                on_click=lambda e: page.show_dialog(about_dialog),
                style=ft.ButtonStyle(color=MUTED, text_style=ft.TextStyle(size=12)),
            ),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.LIGHT_MODE if theme_controller.is_light else ft.Icons.DARK_MODE,
                icon_size=18,
                icon_color=MUTED,
                tooltip="Cambiar tema",
                on_click=lambda e: toggle_theme(e),
            ),
            ft.Text(f"v{APP_VERSION}", size=11, color=MUTED),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    count_text = ft.Text("cargando…", size=11, color=MUTED)

    frequency_box = ft.Container(
        content=frequency_selector,
        padding=ft.Padding.symmetric(horizontal=2, vertical=2),
    )

    # Layout principal: dos superficies elevadas (Bento)
    left_panel_column = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Catálogo de Series", size=18, weight=ft.FontWeight.W_700, color=TEXT),
                        ft.Container(expand=True),
                        count_text,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("Explora y filtra el catálogo del BCRP", size=12, color=MUTED),
                search_box,
                frequency_box,
                filter_btn,
                advanced_panel,
                ft.Row(
                    [
                        master_checkbox,
                        ft.Text("Resultados", size=12, color=MUTED),
                        ft.Container(expand=True),
                        selection_text,
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    content=series_list_view,
                    expand=True,
                    padding=ft.Padding.only(top=8, bottom=8),
                ),
                footer,
            ],
            spacing=12,
            expand=True,
        )
    left_panel = ft.Container(
        content=left_panel_column,
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
                progress_box,
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
                ft.Row(
                    [
                        ft.Text("Parámetros", size=18, weight=ft.FontWeight.W_700, color=TEXT),
                        ft.Container(expand=True),
                        bell_btn,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
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
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        expand=2,
        padding=18,
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=RADIUS,
    )

    page.add(
        ft.Row(
            [left_panel, right_panel],
            spacing=16,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )
    ui_state["mounted"] = True

    def load_catalog():
        """Load the CSV off the UI thread, then render the list once."""
        nonlocal df_metadata
        try:
            df = load_metadata()
        except Exception as ex:
            notify(f"Error al cargar metadatos: {ex}")
            return
        df_metadata = df
        metadata_state["ready"] = True
        count_text.value = f"{len(df):,} series"
        for dropdown, column in (
            (adv_area, "Área que publica"),
            (adv_fuente, "Fuente"),
            (adv_categoria, "Categoría de serie"),
            (adv_grupo, "Grupo de serie"),
        ):
            values = sorted(df[column].dropna().astype(str).unique())
            dropdown.options = [ft.dropdown.Option(key="", text="Todos")] + [
                ft.dropdown.Option(key=v, text=v) for v in values
            ]
        build_listbox(df)
        refresh(series_list_view, count_text)

    page.run_thread(load_catalog)



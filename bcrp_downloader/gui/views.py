"""Flet user interface for BCRP Downloader."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime

import flet as ft
import pandas as pd

from .. import APP_NAME, APP_TAGLINE, APP_VERSION
from ..core import branding, gobpe, portals
from ..core.adapters import get_adapter
from ..core.api import (
    EXPORT_FORMATS,
    download_many,
    export_series,
    export_table,
    find_pdf_url,
    periods_to_dataframe,
)
from ..core.fetcher import fetch_series
from ..core.http import _http_get_bytes, _http_get_json
from ..core.metadata import (
    KNOWN_CODE_COL,
    KNOWN_NAME_COL,
    catalog_count,
    catalog_institutions,
    catalog_values,
    institution_filter_options,
    institution_options,
    load_metadata,
    search_catalog,
    series_info,
)
from ..core.paths import DATA_DIR, OUTPUT_DIR
from ..core.sources import get_source
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

    page.title = f"{APP_NAME} — {APP_TAGLINE}"
    try:
        page.window.icon = branding.ASSETS["icon"]
    except Exception:
        pass
    page.bgcolor = BG
    page.window.width = 1180
    page.window.height = 760
    page.window.min_width = 980
    page.window.min_height = 640
    page.padding = 20
    page.vertical_alignment = ft.MainAxisAlignment.START

    theme_controller = ThemeController(page)
    theme_controller.start()

    brand_tagline = ft.Text(
        APP_TAGLINE,
        size=11,
        color=MUTED,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        expand=True,
    )
    brand_tagline.visible = (
        page.width or page.window.width or 1180
    ) >= 480
    brand_logo = ft.Image(
        src=branding.logo_for(theme_controller.current),
        width=121,
        height=26,
        fit=ft.BoxFit.CONTAIN,
        tooltip=f"{APP_NAME} — {APP_TAGLINE}",
    )

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Notificaciones: toasts cronológicos + historial de sesión ---
    notifications = []
    unread = {"count": 0}
    toast_state = {"running": False}
    initial_toast_width = int(
        max(240, min(360, (page.width or page.window.width or 1180) * 0.9))
    )
    toast_column = ft.Column([], spacing=8, width=initial_toast_width)
    toast_container = ft.Container(
        content=toast_column, right=20, top=20, width=initial_toast_width
    )
    def make_copied_bubble():
        return ft.Container(
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
    bubble_state = {"generation": 0, "control": None}

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
        """Show the active About bubble, then fade it out."""
        bubble = bubble_state.get("control")
        if bubble is None:
            return
        bubble_state["generation"] += 1
        token = bubble_state["generation"]
        bubble.visible = True
        bubble.opacity = 1
        bubble.offset = ft.Offset(0, 0)
        refresh(bubble)

        def hide():
            time.sleep(1.4)
            if token != bubble_state["generation"]:
                return
            bubble.opacity = 0
            bubble.offset = ft.Offset(0, -0.2)
            refresh(bubble)
            time.sleep(0.22)
            if token == bubble_state["generation"]:
                bubble.visible = False
                refresh(bubble)

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

    async def open_portal(url: str):
        """Abre un portal externo sin reemplazar la pestaña de la app."""
        try:
            await url_launcher.launch_url(
                url, web_only_window_name="_blank"
            )
        except Exception:
            pass
    try:
        page.services.extend([url_launcher, clipboard])
    except Exception:
        pass

    # Estado reactivo
    selected_code = ft.Text(value="", visible=False)

    # --- Panel Izquierdo: Catálogo ---
    # Buscador flotante con icono y foco acentuado
    def make_search_box() -> ft.TextField:
        return ft.TextField(
            hint_text="Buscar serie, código o categoría…",
            text_size=14,
            filled=False,
            border=ft.InputBorder.NONE,
            content_padding=ft.Padding.symmetric(horizontal=0, vertical=12),
            hint_style=ft.TextStyle(size=14, color=MUTED),
            expand=True,
        )

    search_box = make_search_box()
    search_row = ft.Row(
        [
            search_box,
            ft.Icon(ft.Icons.SEARCH, size=18, color=MUTED),
            ft.IconButton(
                ft.Icons.CLEAR,
                icon_size=18,
                icon_color=MUTED,
                tooltip="Limpiar búsqueda",
                on_click=lambda e: clear_search(),
            ),
        ],
        spacing=0,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    search_bar = ft.Container(
        content=search_row,
        bgcolor=SURFACE_2,
        border=ft.Border.all(1, BORDER),
        border_radius=14,
        padding=ft.Padding.symmetric(horizontal=14, vertical=0),
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
                height=44,
                padding=ft.Padding.symmetric(horizontal=16, vertical=0),
                alignment=ft.Alignment.CENTER,
                border_radius=22,
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
        compact = (page.width or page.window.width or 1180) < 600
        row_spacing = 8 if compact else 10
        card_padding = ft.Padding.symmetric(
            horizontal=10 if compact else 12,
            vertical=8 if compact else 10,
        )
        name_size = 12 if compact else 13

        for idx, (_, row) in enumerate(rows_to_show.iterrows()):
            code_raw = str(row[KNOWN_CODE_COL])
            code_val = code_raw.upper()
            name_val = str(row[KNOWN_NAME_COL]).upper()
            # Bind row values now so each handler keeps its own series
            row_values = {
                "Institución": str(row.get("Institución", "")),
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
                width=40,
                height=40,
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
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            bgcolor=ACCENT_SOFT,
                            border=ft.Border.all(1, ACCENT_BORDER),
                            border_radius=8,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                        ),
                        ft.Container(
                            content=ft.Text(
                                name_val,
                                size=name_size,
                                color=TEXT,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
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
                    spacing=row_spacing,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=card_padding,
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
            read_only=False,
            tooltip="Escribe el periodo (2024-1) o usa el calendario",
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
            width=40,
            height=40,
            on_click=open_picker,
        )
        clear_btn = ft.IconButton(
            icon=ft.Icons.CLEAR,
            icon_size=16,
            icon_color=MUTED,
            tooltip="Borrar fecha",
            width=40,
            height=40,
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
        relabel = {}
        if str(values.get("Institución", "")).upper() == "MEF":
            relabel = {
                "Categoría": "Rubro",
                "Grupo": "Nivel de gobierno",
                "Fuente": "Fuente de financiamiento",
                "Área publica": "Programa",
                "Inicio": "Periodo inicial",
                "Fin": "Periodo final",
            }
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
            text = str(val).strip()
            if not text:
                continue
            shown = relabel.get(label, label)
            info_details.controls.append(
                ft.Row(
                    [
                        ft.Container(content=ft.Text(shown, size=12, color=MUTED), width=150),
                        ft.Container(content=ft.Text(text, size=12, color=TEXT), expand=True),
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
            width=40,
            height=40,
            on_click=lambda e: page.show_dialog(picker),
        )
        clear_btn = ft.IconButton(
            icon=ft.Icons.CLEAR,
            icon_size=16,
            icon_color=MUTED,
            tooltip=f"Borrar {label.lower()}",
            width=40,
            height=40,
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
        institution = institution_state["value"]
        if not institution:
            # «Todas»: solo búsqueda por palabras clave, sin filtros de fuente.
            return {}
        if institution == "bcrp":
            filters = {"institucion": "bcrp", "frecuencia": freq_state["value"]}
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
        # Filtros propios de cada institución (MEF, INEI, ...).
        filters = {"institucion": institution}
        filters.update(
            {
                key: widget.value
                for key, widget in controls_for(institution).items()
            }
        )
        return filters

    def search_current(query: str, limit: int | None = 300):
        """Busca en la institución activa; delega en su adaptador nativo."""
        filters = gather_filters()
        institution = institution_state["value"]
        if institution:
            try:
                return get_adapter(institution).search(
                    query, filters=filters, limit=limit
                )
            except ValueError:
                pass
        return search_catalog(query, filters=filters, limit=limit)

    def clear_search():
        nonlocal search_box
        search_box = make_search_box()
        search_box.on_change = on_search_change
        search_row.controls[0] = search_box
        apply_filters(None)
        page.update()

    # Aplica filtros de los desplegables + búsqueda de texto (SQLite FTS5)
    def apply_filters(e):
        if not metadata_state["ready"]:
            return
        query = search_box.value.strip()
        try:
            df = search_current(query, 300)
        except Exception as ex:
            notify(f"Error de búsqueda: {ex}")
            return
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

        info = series_info(code) or {}
        inst_id = info.get("_institution_id", "")
        institucion = info.get("Institución", "")
        frequency = info.get("Frecuencia")
        source = get_source(inst_id)
        fixed = bool(source and source.fixed_period)
        if inst_id.startswith("gobpe:"):
            try:
                memo = json.loads(info.get("Memo") or "{}")
            except ValueError:
                memo = {}
            if memo.get("platform") not in gobpe.TABULAR:
                url = memo.get("url", "")
                if url and not silent:
                    page.run_task(open_portal, url)
                    notify(f"Portal externo: {url}", ft.Colors.BLUE)
                return None

        if fixed:
            if inst_id == "inei":
                start = info.get("Fecha de inicio") or "2018-01-01"
                end = info.get("Fecha de fin") or "2026-12-31"
            else:
                start, end = "archivo", "unico"
        else:
            start = start_input.value.strip()
            end = end_input.value.strip()
            if not start or not end:
                if not silent:
                    notify("Elige las fechas de inicio y fin", ft.Colors.AMBER)
                return None

        fmt = (format_dd.value or "CSV").lower()
        if source and source.formats:
            fmt = source.formats[0]
        if fmt not in EXPORT_FORMATS.values():
            if not silent:
                notify(f"Formato no soportado: {fmt}", ft.Colors.AMBER)
            return None

        safe_code = re.sub(r"[^\w\-_.]", "_", code.upper())

        # XLS: BCRP entrega un .xls binario genuino sólo por su endpoint
        if fmt == "xls" and inst_id == "bcrp":
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

        if inst_id and inst_id != "bcrp":
            try:
                df_result = get_adapter(inst_id).fetch([code], start, end)
            except Exception as ex:
                if not silent:
                    notify(f"Error {institucion}: {ex}")
                return None
            if df_result.empty:
                if not silent:
                    notify("No hay datos para el rango consultado", ft.Colors.AMBER)
                return None
        elif frequency:
            try:
                rows = fetch_series([code], start, end, frequency).get(code.upper(), [])
            except Exception as ex:
                if not silent:
                    notify(f"Error API: {ex}")
                return None
            if not rows:
                if not silent:
                    notify("No hay datos para el rango consultado", ft.Colors.AMBER)
                return None
            df_result = pd.DataFrame(
                {
                    "fecha": [row["fecha"] for row in rows],
                    code.upper(): [row["valor"] for row in rows],
                }
            )
        else:  # serie fuera del catálogo: ruta antigua
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
        institution = institution_state["value"]
        source = get_source(institution)
        fixed = bool(source and source.fixed_period)
        if not fixed and (
            not start_input.value.strip() or not end_input.value.strip()
        ):
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

        if fixed:
            start, end = "archivo", "unico"
            if institution == "inei":
                start, end = "2018-01-01", "2026-12-31"
        else:
            start = start_input.value.strip()
            end = end_input.value.strip()
        fmt = source.formats[0] if source and source.formats else (
            format_dd.value or "CSV"
        ).lower()

        def worker():
            saved = failed = opened = done = 0
            try:
                if fmt == "xls":
                    for code in codes:
                        done += 1
                        progress_text.value = f"Descargando serie {done} de {total}…"
                        progress_bar.value = done / total if total > 1 else None
                        refresh(progress_bar, progress_text)
                        if do_download(code, silent=True):
                            saved += 1
                        else:
                            failed += 1
                else:
                    groups: dict[str, list[str]] = {}
                    for code in codes:
                        info = series_info(code) or {}
                        inst = info.get("_institution_id") or ""
                        if inst and inst != "bcrp":
                            key = inst
                        else:
                            key = info.get("Frecuencia") or ""
                        groups.setdefault(key, []).append(code)

                    for gindex, (key, group) in enumerate(groups.items(), start=1):
                        progress_text.value = (
                            f"Lote {gindex} de {len(groups)}: "
                            f"{len(group)} serie(s)…"
                        )
                        refresh(progress_text)
                        frame = None
                        if key == "inei_tematico" or key.startswith("gobpe:"):
                            frame = None  # un archivo por descarga
                        elif key and key != "bcrp":
                            try:
                                frame = get_adapter(key).fetch(group, start, end)
                            except Exception:
                                frame = None
                        elif key:
                            try:
                                frame = download_many(group, start, end, key)
                            except Exception:
                                frame = None

                        if frame is None:  # respaldo serie por serie
                            for code in group:
                                done += 1
                                progress_bar.value = (
                                    done / total if total > 1 else None
                                )
                                refresh(progress_bar)
                                info = series_info(code) or {}
                                if str(
                                    info.get("_institution_id", "")
                                ).startswith("gobpe:"):
                                    try:
                                        memo = json.loads(info.get("Memo") or "{}")
                                    except ValueError:
                                        memo = {}
                                    if memo.get("platform") not in gobpe.TABULAR:
                                        url = memo.get("url", "")
                                        if url:
                                            page.run_task(open_portal, url)
                                            opened += 1
                                            continue
                                if do_download(code, silent=True):
                                    saved += 1
                                else:
                                    failed += 1
                            continue

                        for code in group:
                            column = code.strip().upper()
                            done += 1
                            progress_bar.value = done / total if total > 1 else None
                            refresh(progress_bar)
                            if column not in frame.columns:
                                failed += 1
                                continue
                            subset = frame[["fecha", column]].dropna(
                                subset=[column]
                            )
                            if subset.empty:
                                failed += 1
                                continue
                            try:
                                export_series(subset, code, start, end, fmt)
                                saved += 1
                            except Exception:
                                failed += 1
            finally:
                download_state["running"] = False
                download_btn.disabled = False
                progress_box.visible = False
                refresh(download_btn, progress_box)
                if total == 1:
                    if opened:
                        msg, color = "Portal externo abierto", ft.Colors.BLUE
                    else:
                        msg = (
                            "Serie descargada" if saved
                            else "No se pudo descargar la serie"
                        )
                        color = ft.Colors.GREEN if saved else ft.Colors.AMBER
                else:
                    msg = f"Descargadas {saved} series"
                    if opened:
                        msg += f" ({opened} portales abiertos)"
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
    def make_adv_dd(label, column, options=None):
        # The catalogue may still be loading when the UI is built.
        if options is None:
            values = (
                sorted(df_metadata[column].dropna().astype(str).unique())
                if column in df_metadata.columns
                else []
            )
            options = [(value, value) for value in values]
        return ft.Dropdown(
            label=label,
            value="",
            dense=True,
            filled=True,
            fill_color=SURFACE,
            text_size=12,
            label_style=ft.TextStyle(size=11, color=MUTED),
            options=[ft.dropdown.Option(key="", text="Todas")]
            + [ft.dropdown.Option(key=key, text=text) for key, text in options],
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

    institution_state = {
        "value": "",
        "options": [("", "Todas")] + list(institution_options()),
    }
    institution_text = ft.Text("Todas", size=13, color=TEXT)
    institution_field = ft.Container(
        width=260,
        height=48,
        padding=ft.Padding.symmetric(horizontal=12, vertical=5),
        bgcolor=SURFACE_2,
        border=ft.Border.all(1, BORDER),
        border_radius=12,
        on_click=lambda e: open_institution_menu(e),
        tooltip="Elegir institución",
        content=ft.Column(
            [
                ft.Text("Institución", size=9, color=MUTED),
                ft.Row(
                    [
                        institution_text,
                        ft.Container(expand=True),
                        ft.Icon(
                            ft.Icons.ARROW_DROP_DOWN, size=18, color=MUTED
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=0,
            tight=True,
        ),
    )
    adv_area = make_adv_dd("Área que publica", "Área que publica")
    adv_fuente = make_adv_dd("Fuente", "Fuente")
    adv_categoria = make_adv_dd("Categoría de serie", "Categoría de serie")
    adv_grupo = make_adv_dd("Grupo de serie", "Grupo de serie")

    # Filtros propios del Portal de Transparencia (MEF).
    MEF_DIMENSIONS = portals.spec_for("mef").dimensions
    mef_controls = {
        dimension.key: make_adv_dd(dimension.label, dimension.key)
        for dimension in MEF_DIMENSIONS
    }

    # Filtros propios de INEI (población distrital).
    INEI_DIMENSIONS = portals.spec_for("inei").dimensions
    inei_controls = {
        dimension.key: make_adv_dd(dimension.label, dimension.key)
        for dimension in INEI_DIMENSIONS
    }

    # Filtros propios del índice temático del INEI.
    INEI_TEMATICO_DIMENSIONS = portals.spec_for("inei_tematico").dimensions
    inei_tematico_controls = {
        dimension.key: make_adv_dd(dimension.label, dimension.key)
        for dimension in INEI_TEMATICO_DIMENSIONS
    }

    # Filtros propios de los portales de Gob.pe.
    GOBPE_DIMENSIONS = portals.PORTAL_DIMENSIONS
    gobpe_controls = {
        dimension.key: make_adv_dd(dimension.label, dimension.key)
        for dimension in GOBPE_DIMENSIONS
    }

    def institution_controls() -> dict[str, dict]:
        return {
            "mef": mef_controls,
            "inei": inei_controls,
            "inei_tematico": inei_tematico_controls,
            "gobpe": gobpe_controls,
        }

    def controls_for(institution: str) -> dict:
        if institution.startswith("gobpe:"):
            return gobpe_controls
        return institution_controls().get(institution, {})

    def clear_filters(e):
        for dd in (adv_area, adv_fuente, adv_categoria, adv_grupo):
            dd.value = ""
        for dd in mef_controls.values():
            dd.value = ""
        for dd in inei_controls.values():
            dd.value = ""
        for dd in inei_tematico_controls.values():
            dd.value = ""
        for dd in gobpe_controls.values():
            dd.value = ""
        for dc in (filtro_creacion_desde, filtro_creacion_hasta, filtro_actual_desde, filtro_actual_hasta):
            dc.controls[0].value = ""
        apply_filters(None)

    def download_listing(e):
        """Exporta el listado filtrado (metadatos) en el formato elegido."""
        query = search_box.value.strip()
        try:
            df = search_current(query, None)
        except Exception as ex:
            notify(f"Error al filtrar: {ex}")
            return
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
        visible=True,
        content=ft.Column(
            [
                adv_grid,
                ft.Text("Rango de creación", size=11, color=MUTED),
                ft.Row([filtro_creacion_desde, filtro_creacion_hasta], spacing=10),
                ft.Text("Rango de actualización", size=11, color=MUTED),
                ft.Row([filtro_actual_desde, filtro_actual_hasta], spacing=10),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SEARCH, size=14, color=MUTED),
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

    # --- Selección maestra (sólo con filtros activos) ---
    master_checkbox = ft.Checkbox(
        value=False,
        disabled=True,
        width=40,
        height=40,
        visual_density=ft.VisualDensity.COMPACT,
        fill_color=ACCENT,
        check_color=ON_ACCENT,
        shape=ft.RoundedRectangleBorder(radius=5),
        tooltip="Seleccionar todos los resultados filtrados",
    )
    selection_text = ft.Text("", size=11, color=MUTED)

    def has_active_filters():
        """True when search or the active institution's filters are set."""
        if (search_box.value or "").strip():
            return True
        institution = institution_state["value"]
        if not institution:
            return False
        if institution == "bcrp":
            if freq_state["value"] != "Todos":
                return True
            if any((dd.value or "").strip() for dd in (adv_area, adv_fuente, adv_categoria, adv_grupo)):
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
        controls = controls_for(institution)
        return any((dd.value or "").strip() for dd in controls.values())

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
        if key == "escape":
            if history_state.get("open"):
                close_history()
                return
            if dialog_state["about"] or dialog_state["sites"]:
                close_dialog()
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
    def sites_data() -> list[tuple[str, str]]:
        """Fuentes base + un sitio por institución descubierta en Gob.pe."""
        seen: set[str] = set()
        rows: list[tuple[str, str]] = []
        for name, url in branding.DATA_SITES:
            if url not in seen:
                seen.add(url)
                rows.append((name, url))
        for site in gobpe.sites():
            if site["url"] not in seen:
                seen.add(site["url"])
                rows.append((site["name"], site["url"]))
        return rows

    dialog_state = {"about": False, "sites": False}

    def close_dialog():
        """Cierra el diálogo superior y actualiza el estado."""
        if dialog_state["sites"]:
            dialog_state["sites"] = False
        elif dialog_state["about"]:
            dialog_state["about"] = False
        page.pop_dialog()
        page.update()

    def show_sites(e=None):
        """Lista desplegable de portales con enlace oculto en el nombre."""
        dialog_state["sites"] = True
        entries = sites_data()
        mobile = (page.width or 0) < 600
        listing = ft.ListView(spacing=2, expand=True)

        def render(query: str = ""):
            needle = query.strip().lower()
            listing.controls.clear()
            for name, url in entries:
                if needle and needle not in name.lower():
                    continue
                link = ft.TextButton(
                    content=ft.Text(
                        name,
                        size=12,
                        color=ACCENT,
                        text_align=ft.TextAlign.LEFT,
                    ),
                    tooltip=url,
                    on_click=lambda ev, target=url: page.run_task(
                        open_portal, target
                    ),
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(
                            horizontal=6, vertical=2
                        ),
                        overlay_color=ft.Colors.with_opacity(0.08, ACCENT),
                    ),
                )
                listing.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [link],
                            alignment=ft.MainAxisAlignment.START,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.symmetric(vertical=2),
                        border=ft.Border.only(
                            bottom=ft.BorderSide(1, BORDER)
                        ),
                    )
                )

        search = ft.TextField(
            hint_text="Filtrar institución…",
            dense=True,
            filled=True,
            fill_color=SURFACE_2,
            text_size=12,
            border_radius=10,
            on_change=lambda ev: render(ev.control.value),
        )
        render("")
        content = ft.Column(
            [
                search,
                ft.Text(
                    f"{len(entries)} portales de datos",
                    size=11,
                    color=MUTED,
                ),
                ft.Container(listing, height=360 if not mobile else 300),
            ],
            spacing=8,
            tight=True,
        )
        if mobile:
            page.show_dialog(
                ft.BottomSheet(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    "Sitios de datos",
                                    size=16,
                                    weight=ft.FontWeight.W_700,
                                    color=TEXT,
                                ),
                                content,
                                ft.TextButton(
                                    "Cerrar",
                                    on_click=lambda ev: close_dialog(),
                                ),
                            ],
                            spacing=8,
                            tight=True,
                        ),
                        padding=16,
                    ),
                )
            )
            return
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=SURFACE,
                shape=ft.RoundedRectangleBorder(radius=16),
                title=ft.Row(
                    [
                        ft.Icon(ft.Icons.PUBLIC, color=ACCENT, size=20),
                        ft.Text(
                            "Sitios de datos",
                            size=18,
                            weight=ft.FontWeight.W_700,
                            color=TEXT,
                        ),
                    ],
                    spacing=8,
                ),
                content=ft.Container(width=560, content=content),
                actions=[
                    ft.Button(
                        "Cerrar",
                        on_click=lambda ev: page.pop_dialog(),
                        style=ft.ButtonStyle(
                            bgcolor=ACCENT,
                            color=ON_ACCENT,
                            shape=ft.RoundedRectangleBorder(radius=10),
                        ),
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def copy_contact(e):
        """Copy the author email and show the 'Copied!' micro-bubble."""
        try:
            await clipboard.set("EnriqueCastagneda@protonmail.com")
        except Exception:
            pass
        _record_notification("Correo copiado al portapapeles", ft.Colors.GREEN)
        update_bell()
        show_copied_bubble()

    def build_about_content(mobile=False):
        bubble = make_copied_bubble()
        bubble_state["control"] = bubble
        email_btn = ft.TextButton(
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
        items = [
            ft.Image(
                src=branding.logo_for(theme_controller.current),
                width=158,
                height=34,
                fit=ft.BoxFit.CONTAIN,
            ),
            ft.Text(
                f"{APP_NAME} — {APP_TAGLINE}",
                size=16,
                weight=ft.FontWeight.W_700,
                color=TEXT,
            ),
            ft.Text(f"Versión {APP_VERSION}", size=12, color=MUTED),
            ft.Divider(height=16, thickness=1, color=BORDER),
            ft.Text(
                f"{branding.ACRONYM_ES} (ES)",
                size=12,
                weight=ft.FontWeight.W_600,
                color=TEXT,
            ),
            ft.Text(
                f"{branding.ACRONYM_EN} (EN)",
                size=12,
                weight=ft.FontWeight.W_600,
                color=TEXT,
            ),
            ft.Text(
                "Plataforma de acceso, integración, exploración y consulta "
                "de estadísticas y datos abiertos. Reduce las barreras de "
                "acceso a la información pública para investigación, "
                "análisis, planificación, docencia y toma de decisiones.",
                size=12,
                color=TEXT,
            ),
            ft.Text(
                "Principios: acceso abierto, transparencia, reproducibilidad "
                "y reconocimiento de las fuentes originales. Los datos "
                "pertenecen a sus instituciones productoras.",
                size=12,
                color=TEXT,
            ),
            ft.Text(
                "Fuentes integradas: BCRP, MEF, INEI y portales "
                "estadísticos de Gob.pe.",
                size=11,
                color=MUTED,
            ),
            ft.Divider(height=12, thickness=1, color=BORDER),
            ft.Text(
                f"Repositorio: {branding.REPOSITORY_URL}",
                size=11,
                color=MUTED,
                selectable=True,
            ),
            ft.Text(
                f"Licencia del software: {branding.LICENSE_NAME}",
                size=11,
                color=MUTED,
            ),
            ft.Text(
                "La marca ANDES y su identidad gráfica se rigen por "
                "TRADEMARKS.md, independiente de la licencia del código.",
                size=11,
                color=MUTED,
            ),
            ft.Divider(height=12, thickness=1, color=BORDER),
            ft.Text(
                "By Enrique Castañeda",
                size=12,
                weight=ft.FontWeight.W_600,
                color=TEXT,
            ),
            ft.Stack([email_btn, bubble], clip_behavior=ft.ClipBehavior.NONE),
            ft.Text(
                "Stack: Python · Flet 1.0.5 · pandas · requests",
                size=11,
                color=MUTED,
            ),
        ]
        if mobile:
            items.append(
                ft.Row(
                    [
                        ft.TextButton(
                            "Sitios",
                            icon=ft.Icons.PUBLIC,
                            on_click=show_sites,
                            style=ft.ButtonStyle(color=ACCENT),
                        ),
                        ft.TextButton(
                            "Cerrar",
                            on_click=lambda e: page.pop_dialog(),
                            style=ft.ButtonStyle(color=MUTED),
                        ),
                    ],
                    spacing=4,
                )
            )
        return ft.Column(items, spacing=8)

    def show_about(e):
        mobile = (page.width or 0) < 600
        dialog_state["about"] = True

        def dismissed(ev=None):
            dialog_state["about"] = False
            dialog_state["sites"] = False
            bubble_state["control"] = None

        content = build_about_content(mobile)
        if mobile:
            sheet = ft.BottomSheet(
                content=ft.Container(
                    content=content,
                    padding=ft.Padding.all(16),
                    width=(page.width or 390) * 0.92,
                ),
                bgcolor=SURFACE,
                on_dismiss=dismissed,
                show_drag_handle=True,
                use_safe_area=True,
                scrollable=True,
            )
            page.show_dialog(sheet)
            return
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=ACCENT, size=20),
                    ft.Text("Acerca de ANDES", size=18, weight=ft.FontWeight.W_700, color=TEXT),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(width=400, content=content),
            actions=[
                ft.TextButton(
                    "Sitios",
                    icon=ft.Icons.PUBLIC,
                    on_click=show_sites,
                    style=ft.ButtonStyle(color=TEXT),
                ),
                ft.Button(
                    "Cerrar",
                    on_click=lambda ev: close_dialog(),
                    style=ft.ButtonStyle(
                        bgcolor=ACCENT,
                        color=ON_ACCENT,
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=dismissed,
        )
        page.show_dialog(dialog)

    def toggle_theme(e):
        mode = theme_controller.toggle()
        e.control.icon = (
            ft.Icons.LIGHT_MODE if mode == ft.ThemeMode.LIGHT else ft.Icons.DARK_MODE
        )
        brand_logo.src = branding.logo_for(mode)
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
                "Acerca de ANDES",
                icon=ft.Icons.INFO_OUTLINE,
                on_click=show_about,
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

    count_number = ft.Text("…", size=11, color=MUTED, no_wrap=True)
    count_text = ft.Row(
        [
            count_number,
            ft.Text("series", size=11, color=MUTED, no_wrap=True),
        ],
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    params_hint = ft.Text(
        "Periodos BCRP: 2024-1 · 2024-01-15", size=11, color=MUTED
    )

    frequency_box = ft.Container(
        content=frequency_selector,
        padding=ft.Padding.symmetric(horizontal=2, vertical=2),
    )

    mef_grid = ft.ResponsiveRow(
        list(mef_controls.values()),
        spacing=10,
        run_spacing=10,
    )
    for ctrl in mef_grid.controls:
        ctrl.col = {"xs": 12, "sm": 6}

    mef_section = ft.Column(
        [
            ft.Text("Filtros del Portal de Transparencia (MEF)", size=11, color=MUTED),
            mef_grid,
            ft.Row(
                [
                    ft.Icon(ft.Icons.SEARCH, size=14, color=MUTED),
                    ft.TextButton("Limpiar", on_click=clear_filters, style=ft.ButtonStyle(color=MUTED)),
                ],
                spacing=4,
            ),
        ],
        spacing=10,
        visible=False,
    )

    inei_grid = ft.ResponsiveRow(
        list(inei_controls.values()),
        spacing=10,
        run_spacing=10,
    )
    for ctrl in inei_grid.controls:
        ctrl.col = {"xs": 12, "sm": 6}

    inei_section = ft.Column(
        [
            ft.Text("Filtros de INEI (población distrital)", size=11, color=MUTED),
            inei_grid,
            ft.Row(
                [
                    ft.Icon(ft.Icons.SEARCH, size=14, color=MUTED),
                    ft.TextButton("Limpiar", on_click=clear_filters, style=ft.ButtonStyle(color=MUTED)),
                ],
                spacing=4,
            ),
        ],
        spacing=10,
        visible=False,
    )

    inei_tematico_grid = ft.ResponsiveRow(
        list(inei_tematico_controls.values()),
        spacing=10,
        run_spacing=10,
    )
    for ctrl in inei_tematico_grid.controls:
        ctrl.col = {"xs": 12, "sm": 6}

    inei_tematico_section = ft.Column(
        [
            ft.Text("Filtros de INEI (índice temático)", size=11, color=MUTED),
            inei_tematico_grid,
            ft.Row(
                [
                    ft.Icon(ft.Icons.SEARCH, size=14, color=MUTED),
                    ft.TextButton("Limpiar", on_click=clear_filters, style=ft.ButtonStyle(color=MUTED)),
                ],
                spacing=4,
            ),
        ],
        spacing=10,
        visible=False,
    )

    gobpe_grid = ft.ResponsiveRow(
        list(gobpe_controls.values()),
        spacing=10,
        run_spacing=10,
    )
    for ctrl in gobpe_grid.controls:
        ctrl.col = {"xs": 12, "sm": 6}

    gobpe_section = ft.Column(
        [
            ft.Text("Filtros de portales de Gob.pe", size=11, color=MUTED),
            gobpe_grid,
            ft.Row(
                [
                    ft.Icon(ft.Icons.SEARCH, size=14, color=MUTED),
                    ft.TextButton("Limpiar", on_click=clear_filters, style=ft.ButtonStyle(color=MUTED)),
                ],
                spacing=4,
            ),
        ],
        spacing=10,
        visible=False,
    )

    bcrp_section = ft.Column(
        [frequency_box, advanced_panel],
        spacing=10,
        visible=False,
    )

    filters_ui = {"open": False}
    filters_host = ft.Column(
        [
            bcrp_section,
            mef_section,
            inei_section,
            inei_tematico_section,
            gobpe_section,
        ],
        spacing=10,
        visible=False,
    )
    filters_toggle = ft.IconButton(
        icon=ft.Icons.TUNE,
        icon_size=20,
        icon_color=MUTED,
        tooltip="Mostrar filtros",
        disabled=True,
        width=44,
        height=44,
        style=ft.ButtonStyle(
            bgcolor=SURFACE_2,
            shape=ft.RoundedRectangleBorder(radius=12),
            side=ft.BorderSide(1, BORDER),
        ),
    )

    def update_filter_toggle():
        active = bool(institution_state["value"])
        filters_host.visible = active and filters_ui["open"]
        filters_toggle.disabled = not active
        filters_toggle.icon = (
            ft.Icons.FILTER_ALT_OFF if filters_ui["open"] else ft.Icons.TUNE
        )
        filters_toggle.icon_color = ACCENT if filters_ui["open"] else MUTED

    def toggle_filters(e=None):
        filters_ui["open"] = not filters_ui["open"]
        update_filter_toggle()
        page.update()

    filters_toggle.on_click = toggle_filters

    def set_date_enabled(enabled: bool):
        """Bloquea o habilita por completo los campos de fecha."""
        for control in (start_control, end_control):
            for child in control.controls:
                child.disabled = not enabled

    def set_format_locked(source_id: str):
        """Fija el formato adecuado y desactiva el selector si es único."""
        source = get_source(source_id)
        allowed = source.formats if source else ()
        if allowed:
            format_dd.value = allowed[0].upper()
            format_dd.disabled = True
        else:
            format_dd.disabled = False

    def reload_dimension_options(source_id: str):
        """Repuebla los filtros de una institución tras indexar en vivo."""
        if source_id.startswith("gobpe:"):
            dimensions = GOBPE_DIMENSIONS
            controls = gobpe_controls
        else:
            dimensions = {
                "mef": MEF_DIMENSIONS,
                "inei": INEI_DIMENSIONS,
                "inei_tematico": INEI_TEMATICO_DIMENSIONS,
            }.get(source_id, ())
            controls = institution_controls().get(source_id, {})
        try:
            for dimension in dimensions:
                dropdown = controls.get(dimension.key)
                if dropdown is None:
                    continue
                field = portals.catalog_field(dimension.key)
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")] + [
                    ft.dropdown.Option(key=value, text=value)
                    for value in institution_filter_options(source_id, field)
                ]
                refresh(dropdown)
        except Exception:
            return

    def on_institution_change(e):
        institution = institution_state["value"]
        source = get_source(institution)
        fixed = bool(source and source.fixed_period)
        bcrp_section.visible = institution == "bcrp"
        mef_section.visible = institution == "mef"
        inei_section.visible = institution == "inei"
        inei_tematico_section.visible = institution == "inei_tematico"
        gobpe_section.visible = institution.startswith("gobpe:")
        if institution != "bcrp":
            set_frequency("Todos", repaint=False)
        filters_ui["open"] = False
        update_filter_toggle()
        for dropdown in (adv_area, adv_fuente, adv_categoria, adv_grupo):
            dropdown.value = ""
        for controls in institution_controls().values():
            for dropdown in controls.values():
                dropdown.value = ""
        for control in (
            filtro_creacion_desde,
            filtro_creacion_hasta,
            filtro_actual_desde,
            filtro_actual_hasta,
        ):
            control.controls[0].value = ""
        search_box.value = ""
        selected_codes.clear()
        selected_code.value = ""
        update_master_state()
        start_input.value = ""
        end_input.value = ""
        set_date_enabled(not fixed)
        set_format_locked(institution)
        if institution == "mef":
            start_input.tooltip = "Periodo MEF: 2026-01"
            end_input.tooltip = "Periodo MEF: 2026-12"
            params_hint.value = "Periodos MEF: año-mes (2026-01)"
        elif institution == "bcrp":
            start_input.tooltip = "Periodo BCRP: 2024-1 o 2024-01-15"
            end_input.tooltip = "Periodo BCRP: 2024-12"
            params_hint.value = "Periodos BCRP: 2024-1 · 2024-01-15"
        elif institution == "inei":
            params_hint.value = "INEI: archivo único 2018-2026 (sin filtro de fechas)"
        elif institution == "inei_tematico":
            params_hint.value = "INEI Temático: archivo único (sin filtro de fechas)"
        elif institution.startswith("gobpe:"):
            params_hint.value = "Portal institucional: enlace único (sin fechas)"
        else:
            start_input.tooltip = "Elige una institución"
            end_input.tooltip = "Elige una institución"
            params_hint.value = "Elige una institución para habilitar la descarga"
        refresh(
            start_input, end_input, params_hint, format_dd,
            start_control, end_control,
        )
        apply_filters(None)
        reload_dimension_options(institution)
        page.update()



    def select_institution(key: str, label: str):
        institution_state["value"] = key
        institution_text.value = label
        page.pop_dialog()
        on_institution_change(None)

    def open_institution_menu(e=None):
        """Selector con globo de nombre completo por institución."""
        options = institution_state["options"]
        mobile = (page.width or 0) < 600
        listing = ft.ListView(spacing=2, expand=True)

        def render(query: str = ""):
            needle = query.strip().lower()
            listing.controls.clear()
            for key, label in options:
                if needle and needle not in label.lower():
                    continue
                source = get_source(key) if key else None
                full = source.name if source else "Todas las instituciones"
                tip = full if full and full != label else None
                listing.controls.append(
                    ft.TextButton(
                        content=ft.Row(
                            [
                                ft.Text(label, size=12, color=TEXT),
                                ft.Container(expand=True),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        tooltip=tip,
                        width=320,
                        on_click=lambda ev, k=key, name=label: (
                            select_institution(k, name)
                        ),
                        style=ft.ButtonStyle(
                            padding=ft.Padding.symmetric(
                                horizontal=8, vertical=2
                            ),
                            overlay_color=ft.Colors.with_opacity(0.08, ACCENT),
                        ),
                    )
                )

        search = ft.TextField(
            hint_text="Buscar institución…",
            dense=True,
            filled=True,
            fill_color=SURFACE_2,
            text_size=12,
            border_radius=10,
            on_change=lambda ev: render(ev.control.value),
        )
        render("")
        content = ft.Column(
            [
                search,
                ft.Text(
                    f"{len(options) - 1} instituciones",
                    size=11,
                    color=MUTED,
                ),
                ft.Container(listing, height=380 if not mobile else 320),
            ],
            spacing=8,
            tight=True,
        )
        if mobile:
            page.show_dialog(
                ft.BottomSheet(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    "Institución",
                                    size=16,
                                    weight=ft.FontWeight.W_700,
                                    color=TEXT,
                                ),
                                content,
                            ],
                            spacing=8,
                            tight=True,
                        ),
                        padding=16,
                    ),
                )
            )
            return
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=SURFACE,
                shape=ft.RoundedRectangleBorder(radius=16),
                title=ft.Row(
                    [
                        ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=ACCENT, size=20),
                        ft.Text(
                            "Institución",
                            size=18,
                            weight=ft.FontWeight.W_700,
                            color=TEXT,
                        ),
                    ],
                    spacing=8,
                ),
                content=ft.Container(width=350, content=content),
                actions=[
                    ft.TextButton(
                        "Cerrar",
                        on_click=lambda ev: close_dialog(),
                        style=ft.ButtonStyle(color=MUTED),
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    is_mobile = (page.width or page.window.width or 1180) < 600
    panel_height = 520 if is_mobile else max(560, (page.height or page.window.height or 760) - 40)
    panel_padding = 12 if is_mobile else 18
    page.scroll = ft.ScrollMode.AUTO if is_mobile else None

    # Layout principal: dos superficies elevadas (Bento)
    left_panel_column = ft.Column(
            [
                ft.Row(
                    [
                        brand_logo,
                        brand_tagline,
                        count_text,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("Explora por institución o palabra clave", size=12, color=MUTED),
                search_bar,
                ft.Row(
                    [institution_field, filters_toggle],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                filters_host,
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
        height=panel_height,
        padding=panel_padding,
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=RADIUS,
        col={"xs": 12, "sm": 12, "md": 7, "lg": 8},
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
                params_hint,
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
        height=620 if is_mobile else panel_height,
        padding=panel_padding,
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=RADIUS,
        col={"xs": 12, "sm": 12, "md": 5, "lg": 4},
    )

    page.add(
        ft.ResponsiveRow(
            [left_panel, right_panel],
            spacing=16 if not is_mobile else 12,
            run_spacing=16 if not is_mobile else 12,
        )
    )

    def on_resize(e):
        mobile = (page.width or 0) < 600
        brand_tagline.visible = (page.width or 0) >= 480
        available = (page.height or page.window.height or 760) - 40
        left_panel.height = 520 if mobile else max(560, available)
        right_panel.height = 620 if mobile else max(560, available)
        page.scroll = ft.ScrollMode.AUTO if mobile else None
        width = int(max(240, min(360, (page.width or 1180) * 0.9)))
        toast_column.width = width
        toast_container.width = width
        page.update()

    page.on_resize = on_resize
    ui_state["mounted"] = True

    def load_catalog():
        """Indexa el catálogo en segundo plano y pinta la primera página."""
        nonlocal df_metadata
        total = 0
        try:
            total = catalog_count()
            institution_state["options"] = [("", "Todas")] + list(
                catalog_institutions()
            )
            for dropdown, field in (
                (adv_area, "area"),
                (adv_fuente, "source"),
                (adv_categoria, "category"),
                (adv_grupo, "group_name"),
            ):
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")] + [
                    ft.dropdown.Option(key=value, text=value)
                    for value in catalog_values(field, "bcrp")
                ]
            for dimension in MEF_DIMENSIONS:
                dropdown = mef_controls[dimension.key]
                field = portals.catalog_field(dimension.key)
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")] + [
                    ft.dropdown.Option(key=value, text=value)
                    for value in institution_filter_options("mef", field)
                ]
            for dimension in INEI_DIMENSIONS:
                dropdown = inei_controls[dimension.key]
                field = portals.catalog_field(dimension.key)
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")] + [
                    ft.dropdown.Option(key=value, text=value)
                    for value in institution_filter_options("inei", field)
                ]
            for dimension in INEI_TEMATICO_DIMENSIONS:
                dropdown = inei_tematico_controls[dimension.key]
                field = portals.catalog_field(dimension.key)
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")] + [
                    ft.dropdown.Option(key=value, text=value)
                    for value in institution_filter_options("inei_tematico", field)
                ]
            for dimension in GOBPE_DIMENSIONS:
                dropdown = gobpe_controls[dimension.key]
                field = portals.catalog_field(dimension.key)
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")] + [
                    ft.dropdown.Option(key=value, text=value)
                    for value in institution_filter_options("gobpe", field)
                ]
            df_metadata = search_catalog("", limit=300)
        except Exception as ex:
            notify(f"Catálogo rápido no disponible: {ex}", ft.Colors.AMBER)
            try:
                legacy = load_metadata()
            except Exception as inner:
                notify(f"Error al cargar metadatos: {inner}")
                return
            total = len(legacy)
            df_metadata = legacy.head(300)
            institution_state["options"] = [("", "Todas")] + list(
                institution_options()
            )
            for dropdown, column in (
                (adv_area, "Área que publica"),
                (adv_fuente, "Fuente"),
                (adv_categoria, "Categoría de serie"),
                (adv_grupo, "Grupo de serie"),
            ):
                values = sorted(legacy[column].dropna().astype(str).unique())
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")] + [
                    ft.dropdown.Option(key=value, text=value) for value in values
                ]
            for dropdown in mef_controls.values():
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")]
            for dropdown in inei_controls.values():
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")]
            for dropdown in inei_tematico_controls.values():
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")]
            for dropdown in gobpe_controls.values():
                dropdown.options = [ft.dropdown.Option(key="", text="Todos")]

        metadata_state["ready"] = True
        count_number.value = f"{total:,}"
        build_listbox(df_metadata)
        refresh(series_list_view, count_text)

    page.run_thread(load_catalog)



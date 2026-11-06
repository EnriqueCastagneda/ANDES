"""Prueba de humo de la GUI con un ``Page`` falso y catálogo de fixture."""

from __future__ import annotations

from andes.core import catalog
from andes.gui import views

CSV = (
    "Código de serie;Categoría de serie;Grupo de serie;Nombre de serie;"
    "Descripción de la serie;Metodología de la serie;Unidad de medida;Escala;"
    "Geografía (País, Región de Perú);Fuente;Frecuencia;Fecha de creación;"
    "Grupo de publicación;Área que publica;Fecha de actualización;"
    "Fecha de inicio;Fecha de fin;Memo\n"
    "PD04638PD;Tipo de cambio;TC;Tipo de cambio - Venta;;;;;;;Diaria;;;"
    ";;;1997-01-02;2026-10-22;\n"
    "PN01250PM;Precios;Inflación;Inflación USA;;;;;;;Mensual;;;"
    ";;;Ene-1992;Dic-2025;\n"
)


class FakeWindow:
    width = 1180
    height = 760
    min_width = 980
    min_height = 640


class FakePage:
    """Suficiente API de ``ft.Page`` para construir la vista sin servidor."""

    def __init__(self) -> None:
        self.width = 1180
        self.height = 760
        self.window = FakeWindow()
        self.overlay: list = []
        self.services: list = []
        self.controls: list = []
        self.dialogs: list = []
        self.theme = None
        self.dark_theme = None
        self.theme_mode = None
        self.bgcolor = None
        self.padding = None
        self.scroll = None
        self.vertical_alignment = None
        self.title = ""
        self.on_resize = None
        self.on_keyboard_event = None
        self.updates = 0

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        self.updates += 1

    def run_thread(self, fn, *args, **kwargs):
        fn(*args, **kwargs)

    def run_task(self, coro, *args, **kwargs):
        coro.close()

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()


def _controls(control, seen=None):
    seen = seen or set()
    if id(control) in seen:
        return
    seen.add(id(control))
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _controls(content, seen)
    children = getattr(control, "controls", None)
    if isinstance(children, list):
        for child in children:
            yield from _controls(child, seen)


def _texts(control, seen=None):
    seen = seen or set()
    if id(control) in seen:
        return
    seen.add(id(control))
    value = (
        getattr(control, "text", None)
        or getattr(control, "value", None)
        or getattr(control, "label", None)
    )
    if isinstance(value, str):
        yield value
    content = getattr(control, "content", None)
    if content is not None:
        yield from _texts(content, seen)
    children = getattr(control, "controls", None)
    if isinstance(children, list):
        for child in children:
            yield from _texts(child, seen)


def test_gui_builds_list_from_catalog(tmp_path, monkeypatch):
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(CSV, encoding="latin-1")
    monkeypatch.setattr(catalog, "METADATA_PATH", str(csv_path))
    monkeypatch.setattr(catalog, "CATALOG_PATH", str(tmp_path / "catalog.sqlite3"))

    page = FakePage()
    views.main(page)

    assert page.controls, "la vista no agregó controles"
    texts = list(_texts(page.controls[0]))
    assert "2" in texts and "series" in texts
    assert any("PD04638PD" in text for text in texts)
    assert any("INFLACIÓN USA" in text for text in texts)
    assert any("Institución" in text for text in texts)


def test_institution_selector_outside_filters(tmp_path, monkeypatch):
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(CSV, encoding="latin-1")
    monkeypatch.setattr(catalog, "METADATA_PATH", str(csv_path))
    monkeypatch.setattr(catalog, "CATALOG_PATH", str(tmp_path / "catalog.sqlite3"))

    page = FakePage()
    views.main(page)

    selectors = [
        control
        for control in _controls(page.controls[0])
        if type(control).__name__ == "Container"
        and control.width == 260
        and control.on_click is not None
    ]
    assert len(selectors) == 1
    selector = selectors[0]
    texts = [
        control
        for control in _controls(selector)
        if type(control).__name__ == "Text"
    ]
    assert any(text.value == "Institución" for text in texts)
    assert any(text.value == "Todas" for text in texts)

    # Por defecto («Todas») los filtros de institución están ocultos.
    hidden = [
        control
        for control in _controls(page.controls[0])
        if type(control).__name__ == "Column" and not control.visible
    ]
    assert hidden

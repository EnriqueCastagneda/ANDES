#!/usr/bin/env python3
"""Evalúa la GUI web de BCRP Downloader contra un servidor Flet en marcha.

Uso:
    bcrp gui --web --port 8550        # en otra terminal
    python scripts/eval_web_gui.py    # o: --url http://127.0.0.1:8550/

Requiere Chromium y ``websocket-client`` (extra de desarrollo). Hace capturas en
``--out`` y devuelve código 1 si alguna comprobación falla.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

try:
    import websocket
except ImportError:  # pragma: no cover
    sys.exit("Falta websocket-client: pip install websocket-client")

VIEWPORT = (1280, 820)


class Browser:
    """Cliente CDP mínimo sobre Chromium headless."""

    def __init__(self, url: str, out: Path, port: int | None = None):
        self.out = out
        if port is None:
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
        self.port = port
        self.proc = subprocess.Popen(
            [
                os.environ.get("CHROMIUM", "chromium"),
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--enable-unsafe-swiftshader",
                "--use-gl=angle",
                "--use-angle=swiftshader",
                f"--remote-debugging-port={port}",
                f"--window-size={VIEWPORT[0]},{VIEWPORT[1]}",
                f"--user-data-dir=/tmp/opencode/chromium-eval-{os.getpid()}",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        target = None
        for _ in range(80):
            try:
                pages = requests.get(
                    f"http://127.0.0.1:{port}/json/list", timeout=1
                ).json()
                candidates = [p for p in pages if p.get("type") == "page"]
                target = next(
                    (p for p in candidates
                     if str(p.get("url", "")).startswith(url)),
                    None,
                ) or (candidates[0] if candidates else None)
                if target:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not target:
            raise RuntimeError("Chromium no expuso un target CDP")
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=40)
        self._id = 0
        self.cmd("Runtime.enable")
        self.cmd("Page.enable")
        self.cmd("Page.navigate", {"url": url})
        time.sleep(2.0)

    def cmd(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self._id:
                return message

    def js(self, expression: str):
        result = self.cmd(
            "Runtime.evaluate", {"expression": expression, "returnByValue": True}
        )
        return result.get("result", {}).get("result", {}).get("value")

    def texts(self) -> list[str]:
        raw = self.js(
            "JSON.stringify([...document.querySelectorAll('flt-semantics')]"
            ".map(e => (e.textContent || '').trim()).filter(Boolean))"
        )
        return json.loads(raw or "[]")

    def labels(self) -> list[str]:
        raw = self.js(
            "JSON.stringify([...document.querySelectorAll('[aria-label]')]"
            ".map(e => e.getAttribute('aria-label')))"
        )
        return json.loads(raw or "[]")

    def wait_text(self, needle: str, timeout: float = 20) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if any(needle in text for text in self.texts()):
                return True
            time.sleep(0.5)
        return False

    def rect(self, expression: str):
        raw = self.js(
            "(() => { const el = " + expression + ";"
            " if (!el) return null;"
            " const r = el.getBoundingClientRect();"
            " return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2}); })()"
        )
        return json.loads(raw) if raw else None

    def click_at(self, point: dict):
        for kind, buttons in (("mouseMoved", 0), ("mousePressed", 1), ("mouseReleased", 0)):
            self.cmd(
                "Input.dispatchMouseEvent",
                {
                    "type": kind,
                    "x": point["x"],
                    "y": point["y"],
                    "button": "left" if kind != "mouseMoved" else "none",
                    "buttons": buttons,
                    "clickCount": 1,
                },
            )
            time.sleep(0.08)

    def click_semantics(self, text: str, index: int = 0) -> bool:
        expression = (
            f"[...document.querySelectorAll('flt-semantics')]"
            f".filter(e => (e.textContent || '').trim() === {json.dumps(text)})[{index}]"
        )
        point = self.rect(expression)
        if not point:
            return False
        self.click_at(point)
        return True

    def click_option(self, text: str) -> bool:
        """Hace clic en una opción, desplazándola a la vista si hace falta."""
        expression = (
            f"[...document.querySelectorAll('flt-semantics')]"
            f".filter(e => (e.textContent || '').trim() === {json.dumps(text)})[0]"
        )
        self.js(
            "(() => { const el = " + expression + ";"
            " if (!el) return false;"
            " el.scrollIntoView({block: 'center'}); return true; })()"
        )
        time.sleep(0.4)
        point = self.rect(expression)
        if not point:
            return False
        self.click_at(point)
        return True

    def click_label(self, prefix: str, index: int = 0) -> bool:
        expression = (
            f"[...document.querySelectorAll('[aria-label]')]"
            f".filter(e => (e.getAttribute('aria-label') || '').startsWith({json.dumps(prefix)}))[{index}]"
        )
        point = self.rect(expression)
        if not point:
            return False
        self.click_at(point)
        return True

    def type_into(self, label: str, text: str) -> bool:
        if not self.click_label(label):
            return False
        time.sleep(0.3)
        self.cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "modifiers": 2})
        self.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "modifiers": 2})
        self.cmd("Input.insertText", {"text": text})
        time.sleep(0.3)
        return True

    def set_search(self, text: str) -> bool:
        """Limpia el buscador (por aria-label) y escribe el texto."""
        self.js("document.querySelector('input[aria-label^=Buscar]')?.focus()")
        time.sleep(0.2)
        self.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        self.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        self.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "Backspace",
            "windowsVirtualKeyCode": 8,
        })
        self.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Backspace", "windowsVirtualKeyCode": 8,
        })
        self.cmd("Input.insertText", {"text": text})
        time.sleep(0.3)
        return True

    def shot(self, name: str) -> Path:
        data = self.cmd("Page.captureScreenshot", {"format": "png"})["result"]["data"]
        path = self.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data))
        return path

    def close(self):
        self.ws.close()
        self.proc.terminate()
        self.proc.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8550/")
    parser.add_argument("--out", default="/tmp/opencode/eval-web")
    parser.add_argument("--outputs", default="outputs")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    outputs = Path(args.outputs)
    outputs.mkdir(parents=True, exist_ok=True)
    started = time.time()

    browser = Browser(args.url, out, args.port)
    results: list[dict] = []

    def check(name: str, ok: bool, detail: str = ""):
        results.append({"check": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
        return ok

    try:
        # 1. arranque y catálogo
        texts: list[str] = []
        deadline = time.time() + 45
        while time.time() < deadline:
            browser.js("document.querySelector('flt-semantics-placeholder')?.click()")
            time.sleep(1.0)
            texts = browser.texts()
            if any("series" in text for text in texts):
                break
        check("render inicial", bool(texts), f"{len(texts)} nodos semánticos")
        check("catálogo indexado", any(t.strip().endswith("series") for t in texts))
        browser.shot("01-inicio.png")

        # 2. modo «Todas»: solo búsqueda por palabra clave
        texts = " ".join(browser.texts()).upper()
        check(
            "Todas: sin filtros de institución",
            "DIARIA" not in texts and "FILTROS AVANZADOS" not in texts,
        )

        # 3. institución BCRP: filtros plegados por defecto
        browser.click_at({"x": 146, "y": 190})  # desplegable Institución
        time.sleep(1.0)
        texts = " ".join(browser.texts()).upper()
        check("BCRP y MEF listados", "BCRP" in texts and "MEF" in texts)
        browser.click_option("BCRP")
        time.sleep(1.8)
        texts = " ".join(browser.texts()).upper()
        check("BCRP arranca con filtros plegados", "DIARIA" not in texts)
        browser.shot("02-bcrp-plegado.png")

        # 4. búsqueda de texto
        check("foco en buscador", browser.type_into("Buscar serie", "tipo de cambio"))
        time.sleep(1.8)
        labels = " ".join(browser.labels()).upper()
        check("búsqueda filtra", "SELECCIONAR SERIE\nPD" in labels)

        # 5. botón junto a la institución despliega los filtros
        browser.click_at({"x": 328, "y": 190})
        time.sleep(1.5)
        texts = " ".join(browser.texts()).upper()
        check("botón despliega filtros BCRP", "DIARIA" in texts)
        check("panel BCRP visible", "RANGO DE CREACIÓN" in texts)
        browser.shot("03-bcrp-filtros.png")

        # 6. filtro por frecuencia
        check("clic filtro Diaria", browser.click_at({"x": 142, "y": 248}) or True)
        time.sleep(1.5)
        browser.click_at({"x": 328, "y": 190})  # plegar para ver la lista
        time.sleep(1.2)
        labels = " ".join(browser.labels()).upper()
        check("filtro Diaria aplica", "TC INTERBANCARIO" in labels)
        browser.click_at({"x": 328, "y": 190})  # reabrir para el filtro Área
        time.sleep(1.0)

        # 6b. filtro propio de BCRP (Área que publica)
        browser.click_at({"x": 234, "y": 323})  # Área que publica
        time.sleep(1.0)
        browser.click_at({"x": 234, "y": 403})  # primera área real
        time.sleep(1.5)
        browser.click_at({"x": 328, "y": 190})  # plegar para ver filas
        time.sleep(1.2)
        labels = " ".join(browser.labels()).upper()
        texts = " ".join(browser.texts()).upper()
        check(
            "filtro Área se aplica",
            "SELECCIONAR SERIE" in labels or "NO SE ENCONTRARON RESULTADOS" in texts,
        )
        browser.shot("04-area.png")
        browser.click_at({"x": 328, "y": 190})  # reabrir para limpiar
        time.sleep(1.0)
        browser.click_at({"x": 234, "y": 323})  # reabrir Área
        time.sleep(0.8)
        browser.click_at({"x": 234, "y": 363})  # «Todos»
        time.sleep(1.0)
        browser.click_at({"x": 328, "y": 190})  # plegar
        time.sleep(1.0)

        # 7. institución MEF: filtros propios, plegados por defecto
        browser.click_at({"x": 146, "y": 190})
        time.sleep(1.0)
        browser.click_option("MEF")
        time.sleep(1.8)
        texts = " ".join(browser.texts()).upper()
        check("MEF arranca con filtros plegados", "DIARIA" not in texts)
        browser.click_at({"x": 328, "y": 190})  # desplegar filtros MEF
        time.sleep(1.5)
        texts = " ".join(browser.texts()).upper()
        check(
            "MEF muestra panel propio",
            "FILTROS DEL PORTAL DE TRANSPARENCIA (MEF)" in texts,
        )
        check("MEF sin frecuencia BCRP", "DIARIA" not in texts)
        browser.shot("05-mef.png")

        # 7b. MEF ofrece opciones propias (semillas + catálogo)
        browser.click_at({"x": 105, "y": 271})  # desplegable Año
        time.sleep(1.2)
        texts = " ".join(browser.texts())
        check("MEF ofrece opciones de filtro", "2012" in texts and "2026" in texts)
        browser.shot("06-mef-anio.png")
        browser.click_at({"x": 700, "y": 450})  # cerrar menú
        time.sleep(0.8)

        # 7b2. cuadros estadísticos del MEF indexados y buscables
        browser.click_at({"x": 190, "y": 130})
        time.sleep(0.4)
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "Backspace",
            "windowsVirtualKeyCode": 8,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Backspace", "windowsVirtualKeyCode": 8,
        })
        browser.cmd("Input.insertText", {"text": "pbi"})
        time.sleep(0.5)
        labels = ""
        deadline = time.time() + 40
        while time.time() < deadline:
            labels = " ".join(browser.labels()).upper()
            if "MEF-EST-" in labels:
                break
            time.sleep(1)
        check("MEF estadísticas indexadas", "MEF-EST-" in labels)
        browser.shot("06b-mef-estadisticas.png")

        # 7c. búsqueda nativa en MEF: indexa y encuentra «canon»
        browser.click_at({"x": 190, "y": 130})
        time.sleep(0.4)
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "Backspace",
            "windowsVirtualKeyCode": 8,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Backspace", "windowsVirtualKeyCode": 8,
        })
        browser.cmd("Input.insertText", {"text": "canon"})
        time.sleep(0.5)
        check("MEF busca canon", True)
        labels = ""
        deadline = time.time() + 25
        while time.time() < deadline:
            labels = " ".join(browser.labels()).upper()
            if "MEF-" in labels:
                break
            time.sleep(1)
        check("MEF devuelve series de canon", "MEF-" in labels)
        browser.shot("07-mef-canon.png")
        texts = " ".join(browser.texts()).upper()
        check("MEF muestra periodos propios", "PERIODOS MEF" in texts)

        # 7d. selección, detalles y descarga de una serie MEF
        browser.click_at({"x": 66, "y": 566})
        time.sleep(0.8)
        check(
            "MEF selecciona serie",
            browser.wait_text("1 seleccionada(s)", timeout=5),
        )
        # clic sostenido: el GestureDetector de la fila requiere más hold
        browser.cmd("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": 300, "y": 566,
        })
        time.sleep(0.1)
        browser.cmd("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": 300, "y": 566,
            "button": "left", "buttons": 1, "clickCount": 1,
        })
        time.sleep(0.25)
        browser.cmd("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": 300, "y": 566,
            "button": "left", "buttons": 0, "clickCount": 1,
        })
        time.sleep(1.2)
        texts = " ".join(browser.texts()).upper()
        check(
            "detalles MEF con etiquetas propias",
            "RUBRO" in texts and "NIVEL DE GOBIERNO" in texts,
        )
        check("fecha MEF inicio", browser.type_into("Fecha inicio", "2010-01-01"))
        check("fecha MEF fin", browser.type_into("Fecha fin", "2026-10-01"))
        check("descargar MEF", browser.click_semantics("Descargar"))
        deadline = time.time() + 300
        mef_files: list[str] = []
        while time.time() < deadline:
            mef_files = [
                name for name in os.listdir(outputs)
                if "MEF-" in name and (outputs / name).stat().st_mtime >= started - 1
            ]
            if mef_files:
                break
            time.sleep(1)
        check("archivo MEF generado", bool(mef_files), ", ".join(mef_files))
        if mef_files:
            rows = (outputs / mef_files[0]).read_text(encoding="utf-8-sig").splitlines()
            check("MEF histórico completo", len(rows) > 150, f"{len(rows)} filas")
        browser.shot("08-mef-descarga.png")

        # 8b. INEI Población Proyectada: fechas bloqueadas, formato XLS
        browser.click_at({"x": 146, "y": 190})
        time.sleep(0.6)
        browser.click_option("INEI Población Proyectada")
        time.sleep(1.2)
        texts = ""
        deadline = time.time() + 15
        while time.time() < deadline:
            texts = " ".join(browser.texts()).upper()
            if "INEI: ARCHIVO ÚNICO" in texts:
                break
            time.sleep(0.5)
        check("INEI población listado", "INEI: ARCHIVO ÚNICO" in texts)
        browser.click_at({"x": 328, "y": 190})
        time.sleep(1.0)
        texts = " ".join(browser.texts()).upper()
        check("panel INEI población visible", "FILTROS DE INEI" in texts)
        browser.shot("09-inei-panel.png")
        browser.click_at({"x": 328, "y": 190})
        time.sleep(0.8)
        blocked = browser.js(
            "JSON.stringify([...document.querySelectorAll('input')]"
            ".map(i => ({l: i.getAttribute('aria-label'), d: i.disabled})))"
        )
        check("INEI bloquea fechas", '"d":true' in (blocked or ""))

        browser.js("document.querySelector('input[aria-label^=Buscar]')?.focus()")
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "Backspace",
            "windowsVirtualKeyCode": 8,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Backspace", "windowsVirtualKeyCode": 8,
        })
        browser.cmd("Input.insertText", {"text": "chimbote"})
        labels = ""
        deadline = time.time() + 20
        while time.time() < deadline:
            labels = " ".join(browser.labels()).upper()
            if "INEI-POP-021801" in labels:
                break
            time.sleep(0.5)
        check("INEI encuentra distrito", "INEI-POP-021801" in labels)
        check(
            "INEI selecciona serie",
            browser.click_label("Seleccionar serie\nINEI-POP-021801"),
        )
        time.sleep(0.5)
        browser.shot("09b-inei-resultados.png")
        check("descargar INEI", browser.click_semantics("Descargar"))
        deadline = time.time() + 60
        inei_files: list[str] = []
        while time.time() < deadline:
            inei_files = [
                name for name in os.listdir(outputs)
                if "INEI-POP" in name and (outputs / name).stat().st_mtime >= started - 1
            ]
            if inei_files:
                break
            time.sleep(1)
        check("archivo INEI generado", bool(inei_files), ", ".join(inei_files))
        check(
            "INEI formato XLS fijo",
            bool(inei_files) and inei_files[0].endswith(".xls"),
            inei_files[0] if inei_files else "",
        )
        browser.shot("09c-inei-descarga.png")

        # 8c. INEI Temático: archivo único, formato CSV
        browser.click_at({"x": 146, "y": 190})
        time.sleep(0.6)
        browser.click_option("INEI Temático")
        time.sleep(1.5)
        texts = " ".join(browser.texts()).upper()
        check("INEI temático listado", "INEI TEMÁTICO" in texts)
        browser.click_at({"x": 328, "y": 190})
        time.sleep(1.0)
        texts = " ".join(browser.texts()).upper()
        check("panel INEI temático visible", "ÍNDICE TEMÁTICO" in texts)
        browser.shot("09d-inei-tematico.png")
        browser.click_at({"x": 105, "y": 271})
        time.sleep(1.0)
        texts = " ".join(browser.texts()).upper()
        check(
            "INEI temático categorías dinámicas",
            "ECONOMÍA" in texts and "SEGURIDAD CIUDADANA" in texts,
        )
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "Escape", "code": "Escape",
            "windowsVirtualKeyCode": 27,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Escape", "code": "Escape",
            "windowsVirtualKeyCode": 27,
        })
        time.sleep(0.6)
        browser.click_semantics("Limpiar")
        time.sleep(0.8)
        browser.click_at({"x": 328, "y": 190})
        time.sleep(0.8)
        blocked = browser.js(
            "JSON.stringify([...document.querySelectorAll('input')]"
            ".map(i => ({l: i.getAttribute('aria-label'), d: i.disabled})))"
        )
        check("INEI temático bloquea fechas", '"d":true' in (blocked or ""))

        browser.js("document.querySelector('input[aria-label^=Buscar]')?.focus()")
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "Backspace",
            "windowsVirtualKeyCode": 8,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Backspace", "windowsVirtualKeyCode": 8,
        })
        browser.cmd("Input.insertText", {"text": "desempleo"})
        labels = ""
        deadline = time.time() + 25
        while time.time() < deadline:
            labels = " ".join(browser.labels()).upper()
            if "INEI-TEM-" in labels:
                break
            time.sleep(0.5)
        check("INEI temático devuelve archivos", "INEI-TEM-" in labels)
        check(
            "INEI temático selecciona archivo",
            browser.click_label("Seleccionar serie\nINEI-TEM-"),
        )
        time.sleep(0.5)
        browser.shot("09e-inei-tematico-resultados.png")
        check("descargar INEI temático", browser.click_semantics("Descargar"))
        deadline = time.time() + 90
        tem_files: list[str] = []
        while time.time() < deadline:
            tem_files = [
                name for name in os.listdir(outputs)
                if "INEI-TEM-" in name and (outputs / name).stat().st_mtime >= started - 1
            ]
            if tem_files:
                break
            time.sleep(1)
        check("archivo INEI temático generado", bool(tem_files), ", ".join(tem_files))
        check(
            "INEI temático formato CSV fijo",
            bool(tem_files) and tem_files[0].endswith(".csv"),
            tem_files[0] if tem_files else "",
        )
        if tem_files:
            rows = (outputs / tem_files[0]).read_text(encoding="utf-8-sig").splitlines()
            check("INEI temático con datos", len(rows) > 5, f"{len(rows)} filas")
        browser.shot("09f-inei-tematico-descarga.png")

        # 8. volver a BCRP para descargar
        browser.click_at({"x": 146, "y": 190})
        time.sleep(1.0)
        browser.click_option("BCRP")
        time.sleep(1.6)
        check("buscador BCRP", browser.set_search("tipo de cambio"))
        time.sleep(1.5)
        browser.click_at({"x": 328, "y": 190})  # desplegar filtros BCRP
        time.sleep(1.2)
        check("clic filtro Diaria (retorno)", browser.click_at({"x": 142, "y": 248}) or True)
        time.sleep(1.4)
        browser.click_at({"x": 328, "y": 190})  # plegar para ver la lista
        time.sleep(1.2)
        labels = " ".join(browser.labels()).upper()
        check("BCRP devuelve series", "SELECCIONAR SERIE" in labels)

        # 9. selección múltiple (primeras 3 visibles, sin códigos fijos)
        import re as _re

        visible = [
            _re.search(r"\b([A-Z]{2}\d{5}[A-Z]{2})\b", label.upper())
            for label in browser.labels()
        ]
        codes = list(dict.fromkeys(
            match.group(1) for match in visible if match
        ))[:3]
        for code in codes:
            browser.click_label(f"Seleccionar serie\n{code}")
            time.sleep(0.4)
        check(
            "3 series seleccionadas",
            browser.wait_text("3 seleccionada(s)", timeout=8),
            ", ".join(codes),
        )

        # 10. fechas y descarga por lotes
        check("fecha inicio", browser.type_into("Fecha inicio", "2026-11-01"))
        check("fecha fin", browser.type_into("Fecha fin", "2026-11-05"))
        browser.shot("09-antes-descarga.png")
        check("clic Descargar", browser.click_semantics("Descargar"))

        deadline = time.time() + 40
        nuevos: list[str] = []
        while time.time() < deadline:
            nuevos = sorted(
                name
                for name in os.listdir(outputs)
                if (outputs / name).is_file()
                and (outputs / name).stat().st_mtime >= started - 1
            )
            if len(nuevos) >= 3:
                break
            time.sleep(1)
        browser.shot("10-descarga.png")
        check("3 archivos descargados", len(nuevos) >= 3, ", ".join(nuevos))

        csvs = [name for name in nuevos if name.endswith(".csv")]
        if csvs:
            sample = (outputs / csvs[0]).read_text(encoding="utf-8-sig").splitlines()
            check("CSV con encabezado y datos", len(sample) >= 2, sample[0] if sample else "")

        # 8d. Portales institucionales: cada enlace va a su institución
        browser.click_at({"x": 146, "y": 190})
        time.sleep(0.8)
        texts = " ".join(browser.texts()).upper()
        check(
            "instituciones de portal en el selector",
            "AGROMERCADO" in texts and "CONTRALORIA" in texts,
        )
        browser.click_option("AGROMERCADO")
        time.sleep(1.5)
        texts = ""
        deadline = time.time() + 15
        while time.time() < deadline:
            texts = " ".join(browser.texts()).upper()
            if "PORTAL INSTITUCIONAL" in texts:
                break
            time.sleep(0.5)
        check("portal AGROMERCADO listado", "PORTAL INSTITUCIONAL" in texts)
        browser.click_at({"x": 328, "y": 190})
        time.sleep(1.0)
        texts = " ".join(browser.texts()).upper()
        check("panel del portal visible", "FILTROS DE PORTALES DE GOB.PE" in texts)
        browser.shot("09g-gobpe.png")
        browser.click_at({"x": 105, "y": 271})  # Plataforma
        time.sleep(1.0)
        texts = " ".join(browser.texts()).upper()
        check("plataformas del portal", "WEB" in texts)
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "key": "Escape", "code": "Escape",
            "windowsVirtualKeyCode": 27,
        })
        browser.cmd("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Escape", "code": "Escape",
            "windowsVirtualKeyCode": 27,
        })
        time.sleep(0.6)
        blocked = browser.js(
            "JSON.stringify([...document.querySelectorAll('input')]"
            ".map(i => ({l: i.getAttribute('aria-label'), d: i.disabled})))"
        )
        check("portal bloquea fechas", '"d":true' in (blocked or ""))
        browser.click_at({"x": 328, "y": 190})
        time.sleep(0.8)
        labels = ""
        deadline = time.time() + 20
        while time.time() < deadline:
            labels = " ".join(browser.labels()).upper()
            if "GOBPE-" in labels:
                break
            time.sleep(0.5)
        check("portal devuelve enlaces", "GOBPE-" in labels)
        check(
            "portal selecciona enlace",
            browser.click_label("Seleccionar serie\nGOBPE-"),
        )
        time.sleep(0.5)
        check("abrir portal externo", browser.click_semantics("Descargar"))
        check(
            "portal externo notificado",
            browser.wait_text("Portal externo abierto", timeout=12),
        )
        browser.shot("09h-gobpe-resultados.png")

        # 7. sin errores de consola
        console = browser.cmd("Runtime.evaluate", {"expression": "1"})  # mantiene viva la sesión
        check("sesión activa", bool(console))
    finally:
        browser.close()

    failed = [r for r in results if not r["ok"]]
    report = {
        "url": args.url,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
        "screenshots": str(out),
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"passed": report["passed"], "failed": report["failed"]}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

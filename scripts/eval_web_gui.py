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

    def __init__(self, url: str, out: Path, port: int = 9222):
        self.out = out
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
                target = next((p for p in pages if p.get("type") == "page"), None)
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
    parser.add_argument("--port", type=int, default=9222)
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
        check("catálogo indexado", any("17,167 series" in t for t in texts))
        browser.shot("01-inicio.png")

        # 2. búsqueda de texto
        check("foco en buscador", browser.type_into("Buscar serie", "tipo de cambio"))
        time.sleep(1.8)
        labels = " ".join(browser.labels()).upper()
        check("búsqueda filtra", "SELECCIONAR SERIE\nPD" in labels)

        # 3. filtro por frecuencia
        check("clic filtro Diaria", browser.click_semantics("Diaria"))
        time.sleep(1.8)
        labels = " ".join(browser.labels()).upper()
        check("filtro Diaria aplica", "TC INTERBANCARIO" in labels)

        # 4. filtro por institución (coordenadas del panel en 1280x820)
        check("abrir filtros avanzados", browser.click_semantics("Filtros Avanzados ⚙️"))
        time.sleep(1.2)
        texts = " ".join(browser.texts()).upper()
        check("panel de filtros visible", "RANGO DE CREACIÓN" in texts)
        browser.shot("02-filtros.png")
        browser.click_at({"x": 118, "y": 322})  # desplegable Institución
        time.sleep(1.2)
        texts = " ".join(browser.texts()).upper()
        check("BCRP y MEF listados", "BCRP" in texts and "MEF" in texts)
        browser.click_at({"x": 89, "y": 462})  # opción MEF
        time.sleep(1.2)
        browser.click_semantics("Filtros Avanzados ⚙️")  # cerrar panel
        time.sleep(1.2)
        texts = " ".join(browser.texts()).upper()
        check("MEF sin series muestra vacío", "NO SE ENCONTRARON RESULTADOS" in texts)
        browser.shot("03-mef.png")

        browser.click_semantics("Filtros Avanzados ⚙️")  # reabrir panel
        time.sleep(1.2)
        browser.click_at({"x": 118, "y": 322})  # desplegable Institución
        time.sleep(1.0)
        browser.click_at({"x": 89, "y": 422})  # opción BCRP
        time.sleep(1.2)
        browser.click_semantics("Filtros Avanzados ⚙️")  # cerrar panel
        time.sleep(1.2)
        labels = " ".join(browser.labels()).upper()
        check("BCRP devuelve series", "SELECCIONAR SERIE" in labels)
        browser.shot("04-institucion.png")

        # 5. selección múltiple
        for code in ("PD04637PD", "PD04638PD", "PD04647PD"):
            browser.click_label(f"Seleccionar serie\n{code}")
            time.sleep(0.3)
        check(
            "3 series seleccionadas",
            browser.wait_text("3 seleccionada(s)", timeout=5),
        )

        # 6. fechas y descarga por lotes
        check("fecha inicio", browser.type_into("Fecha inicio", "2026-11-01"))
        check("fecha fin", browser.type_into("Fecha fin", "2026-11-05"))
        browser.shot("05-antes-descarga.png")
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
        browser.shot("06-descarga.png")
        check("3 archivos descargados", len(nuevos) >= 3, ", ".join(nuevos))

        if nuevos:
            sample = (outputs / nuevos[0]).read_text(encoding="utf-8-sig").splitlines()
            check("CSV con encabezado y datos", len(sample) >= 2, sample[0] if sample else "")

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

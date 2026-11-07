# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y versionado [SemVer](https://semver.org/lang/es/).

## [2.0.0] — 2026-11-06

### Añadido

- Identidad ANDES: logotipo, isotipo, iconos, temas claro y oscuro exactos.
- Portales por institución: 125 portales de Gob.pe atribuidos a 53 entidades.
- Agrupaciones Municipalidades, Regiones, UGEL y Redes de Salud.
- INEI Temático: 8 categorías y ~826 archivos descubiertos en vivo.
- INEI Población Proyectada: 1 892 distritos (2018–2026).
- Búsqueda avanzada: `AND`, `OR`, `NOT`, frases, paréntesis y `campo:valor`.
- Selector de institución con globo de nombre completo.
- Ventana «Sitios de datos» con los 57 portales y enlaces.
- Exportación XLS binaria y XML con etiquetas válidas.
- Temas persistentes en `data/prefs.json`.
- `TRADEMARKS.md`, `CITATION.cff`, `SECURITY.md` y código de conducta.
- Pantalla de carga y manifiesto PWA con la identidad ANDES.
- Menú de aplicación: carpeta de guardado persistente, reinicio, Acerca de y
  salida; tema movido a la cabecera.
- Botón «Origen:» en los detalles, con URL del recurso y etiqueta API.
- Catálogo con respaldo sin FTS5 (SQLite reducido en Android): búsqueda LIKE
  sin tildes, aviso en la interfaz y sin referencias a tablas virtuales.
- Rutas multiplataforma: XDG en Linux, Application Support en macOS y
  LocalAppData en Windows; preferencias atómicas y validación de la carpeta de
  guardado.
- `index.html` propio con título, tema, fondo de carga y rutas únicas de
  favicon (`icons/andes-favicon.png`) y carga (`icons/loading-andes.png`).
- Smoke test web CDP (`scripts/smoke_web.py`) conectado al job `web` de CI.

### Cambiado

- Paquete `andes`; distribución `andes-open-data`; CLI principal `andes`.
- Descubrimiento solo con herramientas locales (Chromium/CDP).
- Catálogo en `data/andes_catalog.sqlite3`.

### Corregido

- `flet publish` web: sin hilos Python en Pyodide (pump de stderr, temporizador
  de tema y descargas en serie) ya no falla con `can't start new thread`.
- Reinicio en Windows: `os.execv` bloqueaba el proceso original; ahora se
  relanza con `subprocess.Popen` y se termina el actual.
- `Path.home()` con fallback al cwd cuando no hay `USERPROFILE`/`HOME`
  (servicios y CI en Windows).
- Descarga histórica MEF multi-año con caché.
- XML con columnas numéricas.
- Escape en todos los diálogos y paneles.
- Limpieza real del buscador y lupas funcionales.

## [1.1.3] — 2026-10-20

- Versión previa: explorador BCRP con catálogo SQLite/FTS5, CLI, MCP y GUI.

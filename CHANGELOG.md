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
- `index.html` propio con título, tema, fondo de carga y favicon versionado.

### Cambiado

- Paquete `andes`; distribución `andes-open-data`; CLI principal `andes`.
- Descubrimiento solo con herramientas locales (Chromium/CDP).
- Catálogo en `data/andes_catalog.sqlite3`.

### Corregido

- Descarga histórica MEF multi-año con caché.
- XML con columnas numéricas.
- Escape en todos los diálogos y paneles.
- Limpieza real del buscador y lupas funcionales.

## [1.1.3] — 2026-10-20

- Versión previa: explorador BCRP con catálogo SQLite/FTS5, CLI, MCP y GUI.

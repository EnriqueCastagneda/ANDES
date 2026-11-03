# BCRP Flet App

Herramienta de escritorio minimalista y monolítica para extraer, consultar y descargar series estadísticas del Banco Central de Reserva del Perú (BCRP).

## Características

- **Catálogo de metadatos local**: descarga e indexa el archivo `data/metadata_bcrp.csv` (17.000+ series).
- **Búsqueda reactiva**: filtra el catálogo por código, nombre o categoría con Pandas.
- **Descarga automatizada**: consulta la API oficial de series temporales y guarda el CSV en `outputs/`.
- **Interfaz moderna**: interfaz Flet adaptable al modo claro/oscuro del sistema.

## Uso

```bash
cd bcrp_flet_app
python3 app.py
```

### Flujo básico

1. Inicia la aplicación → descarga automáticamente los metadatos locales.
2. Escribe en la barra de búsqueda para filtrar la lista de series.
3. Selecciona una serie en el catálogo para ver sus metadatos completos.
4. Define rango de fechas y presiona "Descargar Serie Seleccionada".
5. El archivo CSV se guarda en la carpeta `outputs/`.

## Estructura

```text
bcrp_flet_app/
├── data/           # Caché local de metadatos
├── outputs/         # CSVs descargados
├── app.py          # Script principal (Flet + Pandas + requests)
├── requirements.txt
└── README.md
```

## URLs

- Catálogo de metadatos: `https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata`
- API de series temporales: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{código}/json/{inicio}/{fin}/esp`

## Datos

- Metadatos: 17.167 series / 18 campos por línea.
- Codificación CSV de salida: UTF-8 con BOM (`utf-8-sig`) para compatibilidad Excel.

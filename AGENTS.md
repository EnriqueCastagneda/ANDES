# AGENTS.md - Agent Configuration: BCRP Flet App Builder

## Context and Role
You are a software engineering assistant expert in Python, monolithic architectures, and modern GUI development with **Flet**, plus data analysis with **Pandas**. You are collaborating on the development of a minimalist desktop application to extract, query, and download statistical series and metadata from the official API of the Banco Central de Reserva del Perú (BCRP).

## Technology Stack and Code Directives
- **Language:** Python 3.10+
- **GUI Framework:** `flet` (Flutter-based, modern, clean, responsive, minimalist interface)
- **Data Processing:** `pandas` (fast filtering, indexing, and manipulation of metadata and time series DataFrames)
- **HTTP Consumption:** `requests` (requests to the BCRP API and metadata download)
- **Architecture Philosophy:** KISS (Keep It Simple, Stupid) and clean monolithic approach.
- **Mathematical/Statistical Notation:** Use formal notation or standard symbols when required (e.g., RMarkdown/LaTeX $\infty$, $E(X)$, etc., for statistical variables if applicable).

## Directory Structure
```text
bcrp_flet_app/
│
├── data/
│   └── metadata_bcrp.csv       # Local cache of official BCRP metadata
├── outputs/
│   └── (CSV files exported by the user)
├── app.py                      # Main monolithic script (Flet UI + API logic)
├── requirements.txt            # Project dependencies
├── README.md                   # Usage documentation
├── AGENTS.md                   # Agent guidelines and context
├── SESSION.md                  # Session log
├── MEMORY.md                   # Memory file
└── CONTEXT.md                  # Project specification and context
```

## Workflow Process
1. **Initialization:** On startup, the system checks for the local metadata file. If it does not exist, it makes an HTTP GET request to download it from the official BCRP endpoint.
2. **Indexing:** `Pandas` reads and normalizes the catalog columns to allow high-speed vectorized queries.
3. **Query and Filtering:** The user types in the Flet search bar; the series list updates reactively in real time.
4. **Metadata Inspection:** Clicking on any series in the catalog displays all its attributes in the right panel (frequency, start/end dates, publishing area, etc.).
5. **Download and Export:** Setting start and end date parameters, the user executes the download, connecting directly to the BCRP API and generating a CSV file in `outputs/`.

## Key URLs
- Metadata catalog: `https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata`
- Time series API: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}/esp`

## Important Notes
- The metadata CSV uses semicolon (`;`) delimiter and Latin-1 encoding.
- The API returns JSON with `config` and `periods` keys; each period has `name` and `values`.
- Exported CSVs use UTF-8 with BOM (`utf-8-sig`) for Excel compatibility.
- The app uses `ft.run(main)` (Flet 1.0.x API), not the deprecated `ft.app()`.
# CONTEXT.md - Project Context and Vision: BCRP Flet App

## 1. Executive Summary
The **BCRP Flet App** is a lightweight, minimalist desktop tool designed to optimize access, search, and automated extraction of statistical series and economic indicators published by the Banco Central de Reserva del Perú (BCRP).

The main problem this application solves is the decoupling between the short codes of BCRP's statistical API and their human-readable descriptions and metadata. By locally and automatically integrating the official metadata catalog, the application allows users to filter and query any series instantly without tedious manual web searches.

---

## 2. Project Objectives
*   **Centralization and Autonomy:** Download and store the official BCRP metadata catalog locally in a structured format for fluid offline operation.
*   **Reactive Real-Time Search:** Provide an intelligent search bar based on `Pandas` capable of indexing and filtering thousands of series by code, name, category, or frequency instantly.
*   **Minimalist and Modern User Interface:** Offer a clean, fluid, multi-platform experience via **Flet**, adapting natively to the system's light and dark modes.
*   **Direct and Automated Extraction:** Connect to the official BCRP REST API, transform JSON responses into clean tabular structures, and automatically export them to the outputs folder (`outputs/`) as `.csv` files with standard UTF-8 encoding.

---

## 3. Architecture and Design Principles
*   **Monolithic Architecture:** The entire application lifecycle (local file management, data processing with Pandas, and Flet UI rendering) is modularly concentrated in a single main script (`app.py`), facilitating portability, maintenance, and fast execution.
*   **KISS Philosophy (Keep It Simple, Stupid):** Avoid over-engineering, microservices, or unnecessary dependencies, betting on native components and highly stable libraries in the Python ecosystem (`flet`, `pandas`, `requests`).
*   **Standardized Directory Structure:**
    *   `data/`: Stores the local metadata cache (`metadata_bcrp.csv`).
    *   `outputs/`: Destination folder for exported CSV files with downloaded series.
    *   `app.py`: Monolithic application core.
    *   `requirements.txt`: Project dependency manifest.
    *   `AGENTS.md`: Technical guidelines and context for development agents and AI.
    *   `CONTEXT.md`: Formal project specification and context document.

---

## 4. Functional Workflow
1.  **Initialization:** On startup, the system checks for the local metadata file. If it does not exist, it makes an HTTP GET request to download it from the official BCRP endpoint.
2.  **Indexing:** `Pandas` reads and normalizes the catalog columns to allow high-speed vectorized queries.
3.  **Query and Filtering:** The user types in the Flet search bar; the series list updates reactively in real time.
4.  **Metadata Inspection:** Clicking on any series in the catalog displays all its attributes in the right panel (frequency, start/end dates, publishing area, etc.).
5.  **Download and Export:** Setting start and end date parameters, the user executes the download, connecting directly to the BCRP API and generating a CSV file in `outputs/`.

---

## 5. Technical Specifications

### Metadata Format
- **Source:** `https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata`
- **Delimiter:** Semicolon (`;`)
- **Encoding:** Latin-1
- **Size:** ~6.9 MB (17,167 series × 18 columns)
- **Key Columns:** `Código de serie`, `Nombre de serie`, `Categoría de serie`, `Grupo de serie`, `Frecuencia`, `Fuente`, `Área que publica`

### API Format
- **Base URL:** `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}/esp`
- **Response:** JSON with `config` and `periods` keys
- **Period structure:** `{"name": "Ene.2020", "values": ["231956.42271984"]}`
- **Date Format:** `YYYY-M` or `YYYY-Q` (e.g., `2020-1`, `2015-Q1`)

### Output Format
- **Filename:** `bcrp_serie_{CODE}_{START}_to_{END}.csv`
- **Encoding:** UTF-8 with BOM (`utf-8-sig`) for Excel compatibility
- **Columns:** `fecha`, `{CODE}`

### UI Design Principles
- **Layout:** Two-panel split (60/40) - left catalog, right parameters and metadata
- **Typography:** Single grotesk font family, clean hierarchy (24px title, 14px body, 12px meta)
- **Color Usage:** Minimal - color only on data and primary action
- **Surfaces:** Flat, no shadows on resting elements, 1px borders for separation
- **Interactions:** Subtle hover effects, immediate snackbars with semantic colors

---

## 6. Dependencies
- `flet>=0.20.0` (actual: 1.0.5)
- `pandas>=2.0.0`
- `requests>=2.31.0`

## 7. Environment
- **Python:** 3.14.6
- **Platform:** Linux
- **Working Directory:** `/home/enrique/Descargas/bcrp_flet_app/`
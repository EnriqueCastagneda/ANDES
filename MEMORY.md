# MEMORY.md - Memory File

## Project Memory
- **Project:** BCRP Flet App
- **Location:** `/home/enrique/Descargas/bcrp_flet_app/`
- **Stack:** Python 3.14, Flet 1.0.5, Pandas, Requests
- **Status:** Active development

## Key Decisions
- **Architecture:** Monolithic single-file design (KISS principle)
- **Metadata Storage:** Local CSV cache in `data/metadata_bcrp.csv`
- **Output Format:** UTF-8 with BOM (`utf-8-sig`) for Excel compatibility
- **Search Strategy:** Pandas vectorized filtering with `apply()` on string columns
- **UI Layout:** Two-panel split (60/40) with left catalog and right parameters

## Patterns and Conventions
- **Code Style:** Clean, minimal, no comments in hot paths
- **Error Handling:** Snackbars with semantic colors (green/amber/red)
- **State Management:** Reactive state via Flet controls
- **File Naming:** `bcrp_serie_{CODE}_{START}_to_{END}.csv`

## Known Issues and Solutions
- **Flet 1.0.x API:** Use `ft.run(main)` instead of deprecated `ft.app()`
- **Metadata CSV:** Semicolon-delimited with Latin-1 encoding
- **API URL Format:** `{code}/json/{start}/{end}/esp` (lowercase code, slash-separated dates)
- **Date Format:** `YYYY-M` or `YYYY-Q` (e.g., `2020-1`, `2015-Q1`)

## Dependencies
- `flet>=0.20.0` (actual: 1.0.5)
- `pandas>=2.0.0`
- `requests>=2.31.0`

## Environment Notes
- Python 3.14.6
- Flet desktop binary requires `libgio-2.0.so.0` with `g_source_set_static_name` symbol
- Metadata file size: ~6.9MB (17,167 series × 18 columns)

## Recent Changes
- 2026-11-03: Created project structure and initial implementation
- 2026-11-03: Verified metadata loading, API connection, and CSV export
- 2026-11-03: Redesigned interface following modern design principles
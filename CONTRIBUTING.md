# Guía de contribución

Gracias por querer mejorar BCRP Data Extractor.

## Flujo de trabajo

1. Haz un *fork* del repositorio.
2. Crea una rama descriptiva:
   ```bash
   git checkout -b feat/mi-mejora
   ```
3. Instala las dependencias y ejecuta las pruebas:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python -m pytest -q
   ```
4. Realiza cambios pequeños y enfocados.
5. Verifica que las pruebas siguen pasando.
6. Haz *commit* siguiendo [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat: añadir exportación a parquet
   fix: corregir filtro por frecuencia
   docs: actualizar README
   ```
7. Abre un *pull request* describiendo el problema y la solución.

## Estilo de código

- Python 3.10+ y formato consistente con el archivo existente.
- Mantén la arquitectura monolítica de `app.py` (KISS).
- No añadas dependencias sin justificarlo.
- Para la interfaz usa las APIs de Flet 1.0.x (`ft.Colors`, `ft.Padding`,
  `ft.Icons`, `ft.run`, etc.).

## Pruebas

- Añade pruebas para la lógica nueva cuando sea posible.
- Las pruebas de red deben omitirse (`skip`) si la API no está disponible.

## Licencia de las contribuciones

Al enviar un *pull request* aceptas que tu contribución se publique bajo la
**GNU General Public License v3.0**, la misma licencia del proyecto.

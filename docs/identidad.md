# Identidad visual de ANDES

**ANDES — Open Data Platform**  
Archivo Nacional de Datos Estadísticos y Sociales  
Andean Network for Data, Evidence and Statistics

## Concepto

ANDES conecta datos, territorios y conocimiento para comprender la diversidad
del Perú. El isotipo reinterpreta el colibrí de Nasca —observación, movimiento y
conocimiento— e integra una flecha de descarga de geometría escalonada andina:
la plataforma observa, reúne y entrega datos abiertos.

La identidad es sobria, geométrica, contemporánea y apta para una plataforma
científica. No usa degradados, sombras decorativas ni símbolos patrióticos
convencionales.

## Colores obligatorios

| Tema | Uso | Color |
| --- | --- | --- |
| Oscuro | Fondo | `#1b293d` |
| Oscuro | Texto y destaque | `#d8b56d` |
| Claro | Fondo | `#f1eadc` |
| Claro | Texto y destaque | `#2a3f48` |

Variaciones derivadas (superficies, bordes, estados) viven en
`bcrp_downloader/core/branding.py` como parte del `ColorScheme` de Flet.
No se sustituyen los cuatro colores base.

Paleta categórica para gráficos: `branding.CHART_COLORS` (8 tonos aptos para
ambos temas). No se usa el color como único portador de información.

## Logotipo y variantes

- `assets/andes_mark_gold.png`: isotipo dorado para fondos oscuros.
- `assets/andes_mark_teal.png`: isotipo azul verdoso para fondos claros.
- `assets/andes_mark_light.png`: monocromático claro.
- `assets/andes_mark_dark.png`: monocromático oscuro.
- `assets/andes_mark_gold.svg` y `andes_mark_teal.svg`: fuentes vectoriales.

Composición horizontal: isotipo + «ANDES» + «Open Data Platform». El nombre
tiene mayor jerarquía que el descriptor.

## Tipografía

Se usa la tipografía del sistema de Flet (Roboto). Jerarquía:

- Nombre ANDES: 18–22 px, peso 700.
- Descriptor: 11 px, color atenuado.
- Títulos de panel: 18 px, peso 700.
- Cuerpo: 12–13 px.
- Metadatos: 11 px.

## Temas

`bcrp_downloader/gui/theme.py` aplica `branding.theme_light()` y
`branding.theme_dark()` a `page.theme` y `page.dark_theme`. El modo se alterna
con el botón del pie, se guarda en `data/prefs.json` y, sin preferencia manual,
sigue la hora local (claro 06:00–17:59).

## Accesibilidad

- Contraste alto entre fondo y texto en ambos temas.
- Controles con tooltip y etiquetas accesibles.
- Selector de institución con globo de nombre completo al pasar el puntero
  sobre cada sigla; el globo se desvanece solo.
- Navegación por teclado en la lista de series.
- Diseño de una columna en móvil y adaptación de paneles en tablet.

## Uso de marca

La identidad gráfica se rige por [`TRADEMARKS.md`](../TRADEMARKS.md). La licencia
GPLv3 del código no concede derechos sobre la marca.

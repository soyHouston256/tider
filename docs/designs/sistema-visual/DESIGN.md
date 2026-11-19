---
version: alpha
name: TiderOps
description: "Consola de investigación de incidentes para SRE. Lienzo neutro azulado (#f3f5f9 claro, #0b0f17 oscuro) con tarjetas blancas de borde fino, tinta casi negra (#0f1524) y un único acento cobalto (#1b4fd6) reservado para la acción primaria, la selección y los enlaces. Los colores de estado (ok, warning, critical, info) solo comunican estado y siempre van con palabra o icono. IBM Plex Sans para la interfaz e IBM Plex Mono para todo lo que viene del sistema observado (identificadores, entorno, archivos). Densidad de herramienta de trabajo, no de página de marketing: sin fotografías, sin degradados, sin efectos."

colors:
  primary: "#1b4fd6"
  on-primary: "#ffffff"
  bg: "#f3f5f9"
  surface: "#ffffff"
  surface-sunken: "#e8ecf2"
  surface-hover: "#eef1f6"
  border: "#d7dce6"
  border-strong: "#727d96"
  ink: "#0f1524"
  ink-muted: "#434c60"
  ink-subtle: "#586277"
  brand: "#1b4fd6"
  brand-hover: "#153fb0"
  brand-soft: "#e6edfd"
  on-solid: "#ffffff"
  focus: "#1b4fd6"
  info: "#6941c6"
  info-soft: "#f0ebfc"
  ok: "#0f766e"
  ok-soft: "#e0f2f0"
  warning: "#8a5300"
  warning-soft: "#fcf1dc"
  critical: "#b3261e"
  critical-soft: "#fdecea"

typography:
  display:
    fontFamily: IBM Plex Sans
    fontSize: 28px
    fontWeight: 600
    lineHeight: 36px
    letterSpacing: -0.01em
  title:
    fontFamily: IBM Plex Sans
    fontSize: 18px
    fontWeight: 600
    lineHeight: 26px
  heading:
    fontFamily: IBM Plex Sans
    fontSize: 15px
    fontWeight: 600
    lineHeight: 22px
  body:
    fontFamily: IBM Plex Sans
    fontSize: 14px
    fontWeight: 400
    lineHeight: 22px
  body-strong:
    fontFamily: IBM Plex Sans
    fontSize: 14px
    fontWeight: 600
    lineHeight: 22px
  small:
    fontFamily: IBM Plex Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 20px
  caption:
    fontFamily: IBM Plex Sans
    fontSize: 12px
    fontWeight: 500
    lineHeight: 16px
  overline:
    fontFamily: IBM Plex Sans
    fontSize: 12px
    fontWeight: 600
    lineHeight: 16px
    letterSpacing: 0.06em
  mono:
    fontFamily: IBM Plex Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 20px
  mono-small:
    fontFamily: IBM Plex Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 18px

rounded:
  sm: 4px
  md: 8px
  lg: 12px
  full: 999px

spacing:
  space-1: 4px
  space-2: 8px
  space-3: 12px
  space-4: 16px
  space-5: 24px
  space-6: 32px
  space-7: 48px

components:
  button-primary:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.on-solid}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
    padding: 0 14px
    height: 36px
  button-primary-hover:
    backgroundColor: "{colors.brand-hover}"
    textColor: "{colors.on-solid}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
  button-disabled:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-subtle}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: 0 12px
    height: 36px
  segmented-selected:
    backgroundColor: "{colors.brand-soft}"
    textColor: "{colors.brand}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.small}"
    rounded: "{rounded.full}"
    padding: 0 12px
    height: 28px
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: 24px
  composer-bar:
    backgroundColor: "{colors.surface-sunken}"
    textColor: "{colors.ink}"
    typography: "{typography.small}"
    padding: 16px 24px
  nav-item-active:
    backgroundColor: "{colors.brand-soft}"
    textColor: "{colors.brand}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
  badge-ok:
    backgroundColor: "{colors.ok-soft}"
    textColor: "{colors.ok}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
  badge-info:
    backgroundColor: "{colors.info-soft}"
    textColor: "{colors.info}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
  map-node:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    height: 40px
    width: 190px
  page:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
  help-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.small}"
  nav-item-hover:
    backgroundColor: "{colors.surface-hover}"
    textColor: "{colors.ink}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
  divider:
    backgroundColor: "{colors.border}"
    height: 1px
  control-outline:
    backgroundColor: "{colors.border-strong}"
    width: 1px
  focus-ring:
    backgroundColor: "{colors.focus}"
    width: 2px
  badge-warning:
    backgroundColor: "{colors.warning-soft}"
    textColor: "{colors.warning}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
  badge-critical:
    backgroundColor: "{colors.critical-soft}"
    textColor: "{colors.critical}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
  button-primary-cta:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
---

# TiderOps

Fuente de verdad del código: `src/tider/console/static/css/tokens.css` (v2 · Cobalto) y
`components.css`. Este archivo los describe para personas y agentes; si difieren, manda el CSS.

## Overview

TiderOps es una consola interna para investigar incidentes en Kubernetes. Quien la usa está bajo
presión y necesita ver tres cosas en orden: qué describe (el síntoma), dónde buscar (alcance,
ventana, fuente) y qué dice la evidencia. La interfaz es sobria y densa como una herramienta de
trabajo: una barra lateral fija, una cabecera de página y tarjetas blancas sobre un lienzo neutro.

Pantallas: **Investigar** (compositor + arquitectura documentada + recorrido + resultado),
**Context Lake** (documentos), **Catálogo** (revisión humana de servicios y relaciones) e
**Historial**.

## Colors

### Brand & Accent
- `brand` #1b4fd6 (oscuro #7aa5ff): acción primaria, ítem activo, opción elegida, enlaces, foco.
- `brand-soft` #e6edfd (oscuro #152447): fondo de lo seleccionado. Nunca en paneles informativos.
- El cobalto no significa "sano". Un nodo incluido en el catálogo lleva punto cobalto, no verde.

### Surface
- `bg` lienzo; `surface` tarjetas, barra lateral, campos, nodos; `surface-sunken` pozos (barra de
  parámetros del compositor, zona de arrastre, bloques de log); `surface-hover` hover de filas.
- `border` decorativo (tarjetas, divisores); `border-strong` contorno de controles y aristas del
  mapa (3:1 sobre surface y bg).

### Text
- `ink` texto principal; `ink-muted` secundario y ayuda; `ink-subtle` metadatos, contadores y
  rótulos de columna. Es el gris más claro permitido para texto.

### Semantic
- `ok`, `warning`, `critical`, `info` y sus `-soft`. Solo comunican estado y siempre van con
  palabra o icono. `info` (violeta) marca el origen de la evidencia ("Logs reales").

### Tema oscuro
Se activa con `prefers-color-scheme: dark` o `data-theme="dark"`. Valores en `tokens.css`:
bg #0b0f17, surface #131824, surface-sunken #080b11, border #252d3d, border-strong #5f6b85,
ink #e8ecf4, ink-muted #a8b1c4, brand #7aa5ff, on-solid #080b11.

## Typography

### Font Family
IBM Plex Sans (400/500/600) e IBM Plex Mono (400/500), servidas desde `static/fonts/` (SIL OFL)
porque la CSP de la consola solo permite recursos propios.

### Hierarchy
display 28/36 (un título por pantalla) → title 18/26 (tarjetas) → heading 15/22 → body 14/22 →
small 13/20 (ayuda) → caption 12/16 (insignias). 12px es el mínimo.

### Principles
- Mono para todo lo que viene del sistema observado: incidente (`INC-0004`), entorno
  (`tider-ops / chaosforge-lab / boutique`), modelo, nombres de archivo e identificadores.
- Los nombres de servicio en el mapa van en Sans 14/500 para leerse de un vistazo.
- `overline` en mayúsculas solo para rótulos de sección y columnas del mapa, máximo tres palabras.
- Cifras con `tabular-nums`. Titulares con `text-wrap: balance`.

## Layout

### Spacing System
Escala de 4px: 4, 8, 12, 16, 24, 32, 48. Tarjetas con padding de 24; separación entre tarjetas 16.

### Grid & Container
Barra lateral fija de 232px; contenido alineado a la izquierda con máximo de 1280px en todas las
pantallas. Investigar es una sola columna: compositor, línea de entorno, arquitectura, recorrido,
resultado.

### Whitespace Philosophy
Pocas cajas y fuertes. Una tarjeta por bloque de trabajo; dentro, filas con divisores en lugar de
tarjetas anidadas.

## Elevation & Depth
Los bordes separan; la sombra solo despega. `shadow-card` (0 1px 2px) en tarjetas en reposo y
`shadow-pop` (0 8px 24px) en menús desplegables. Sin brillos ni desenfoques.

## Shapes

### Border Radius Scale
4 insignias · 8 botones, campos, nodos e ítems de navegación · 12 tarjetas · 999 chips y puntos.

## Components

### Compositor (Investigar)
Tarjeta con dos zonas. Arriba, "¿Qué está ocurriendo?" (title), área de texto y chips "Prueba
con:" que rellenan el síntoma. Abajo, barra `surface-sunken` con Alcance (segmentado General /
Enfocado en un servicio), ¿Cuándo ocurrió?, Evidencia, Incidente (mono) y el botón primario
"Analizar incidente →" alineado a la derecha. Los campos condicionales (servicio, escenario, horas)
aparecen debajo solo cuando aplican, con una única línea de ayuda.

### Buttons
Primario cobalto, 36px de alto. Deshabilitado: superficie con texto `ink-subtle`. Enlaces de
acción secundaria como texto cobalto ("Revisar catálogo ↗").

### Navigation
Ítems de 36px: gris en reposo, `brand-soft` + `brand` en el activo, contador mono a la derecha
(documentos del Context Lake, servicios del catálogo confirmado).

### Mapa de arquitectura
Columnas por nivel (ENTRADA, NIVEL 1…), nodos de 190×40 con punto de estado y nombre a la
izquierda. Aristas ortogonales con esquinas de 8px que viajan por los pasillos entre columnas y
filas; nunca cruzan un nodo. Estados del pipeline: falla `critical`, sano `ok`, sin datos
`border-strong`. Hover o foco en un nodo resalta sus aristas en cobalto.

### Inputs & Forms
36px, borde `border-strong`, foco con anillo `focus` de 2px a 2px. Placeholders con ejemplo y
terminados en "…". Campos no de autenticación con `autocomplete="off"`.

### Acciones destructivas
"Retirar" un documento pide confirmación en el mismo botón ("Confirmar retiro", en `critical`);
se cancela al salir del botón.

## Do's and Don'ts

### Do
- Un solo acento cromático (cobalto) para acción, selección y foco.
- Estado siempre con palabra o icono, además del color.
- Datos del sistema en mono y con `translate="no"`.
- Respetar `prefers-reduced-motion` y mantener el foco visible en todos los controles.

### Don't
- No usar verde para "incluido" o "confirmado" salvo en la insignia de estado; el verde es salud.
- No anidar tarjetas dentro de tarjetas; usar filas con divisores.
- No añadir fotografías, degradados, efectos ni etiquetas decorativas: es una consola, no una
  página de marketing.
- No numerar secciones (01, 02…) ni repetir el título de página dentro de la tarjeta.
- No cargar recursos de terceros (la CSP lo bloquea).

## Responsive Behavior

### Breakpoints

| Nombre | Ancho | Cambios |
|---|---|---|
| Escritorio | ≥1100px | Barra lateral 232px |
| Portátil | 721–1099px | Barra lateral 200px; botón Analizar a todo el ancho bajo 900px |
| Móvil | ≤720px | Barra lateral arriba como fila de navegación; campos del compositor apilados; segmentado al 100% |

### Touch Targets
Controles de 36px; chips de 28px con separación de 8px.

## Iteration Guide
1. Cambiar valores en `tokens.css`, nunca colores literales en `app.css`.
2. Revisar con `npx @google/design.md lint` este archivo y con la skill `web-design-guidelines` el HTML.
3. Comprobar claro, oscuro y 390px antes de cerrar un cambio.

## Known Gaps
- Los valores vigentes son los de `tokens.css` (v2 Cobalto); el `tokens.json` de la v1 (verde) se retiró del repositorio.
- Las clases `to-*` de `components.css` están cargadas pero la consola aún usa sus propios
  selectores; migrar pantalla por pantalla.

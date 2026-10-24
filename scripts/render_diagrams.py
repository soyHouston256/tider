"""Render the architecture catalog with Mermaid CLI and build its offline gallery.

The renderer is a documentation tool; it is not a runtime dependency of TiderOps.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "docs" / "diagrams"

OVERVIEW = """La implementación se organiza alrededor de un motor LangGraph compartido.
La consola web recibe la solicitud; FastAPI la valida; AnalysisService obtiene
las señales y administra el historial; LabEngine prepara y ejecuta el grafo.
Investigador, juez y reportero trabajan dentro del mismo proceso Python.
La política calcula la propuesta y la interfaz explica los eventos registrados."""

DETAIL = """## Cómo se hizo la implementación

1. **Unificar el proyecto.** La consola se incorporó al paquete `src/tider`, con
   dependencias declaradas en `pyproject.toml` y resueltas en `uv.lock`. Sus archivos
   web, escenarios y contexto se incluyen en la distribución instalable.
2. **Separar responsabilidades.** HTTP está en `console/api.py`; el caso de uso en
   `service.py`; la evidencia en `providers/`; la adaptación al grafo en `analysis.py`.
   Los contratos `EvidenceSource` y `DiagnosticEngine` permiten sustituir conectores
   en pruebas sin cambiar el caso de uso.
3. **Conservar un solo flujo de agentes.** `graph.py` conecta las etapas; `agents/`
   contiene su trabajo; `workflow/nodes.py` implementa decisión, ejecución y
   verificación; `decision/` conserva la política y sus umbrales.
4. **Aislar el estado.** Cada aplicación posee su historial acotado y protegido por
   un bloqueo. Cada análisis recibe herramientas, contexto y proveedor de
   razonamiento propios. El historial desaparece al reiniciar el proceso.
5. **Explicar la ejecución.** Los agentes registran eventos en `audit` y
   `explanation.py` los transforma en pasos con resultado, motivo y referencias
   a las señales. La explicación procede del flujo ejecutado.

Los motivos y alternativas de estas decisiones están en
[Decisiones de diseño](../decisions.md). Los diagramas 11 y 12 ubican los módulos
y muestran la reorganización.

## Dos entradas y dos elecciones independientes

| Aspecto | Consola de laboratorio | Entrada operativa del motor |
|---|---|---|
| Inicio | `python -m tider.console` | `tider.api:app` |
| Entrada | Formulario y API de análisis | Webhook autenticado de Alertmanager |
| Evidencia | Señales mock o logs de GCP | Registro de herramientas operativas |
| Contexto | InMemoryStore por análisis | Memoria o PgVectorStore configurado |
| Ejecución | Grafo compilado en observación | Adaptadores sujetos a política, dry-run y configuración |
| Historial de consola | Hasta 50 análisis por defecto | No utiliza el historial de la consola |

Dentro de la consola, **fuente** y **razonamiento** son elecciones independientes:
`EVIDENCE_MODE=mock|gcp` elige de dónde salen las señales; `LLM_PROVIDER=none|anthropic`
elige cómo se producen las respuestas del investigador, juez y reportero.
El modo local calcula una hipótesis con reglas sobre las señales y alimenta
`ScriptedLLM`; luego ejecuta el grafo completo. Las reglas no reciben la etiqueta
del escenario. Anthropic utiliza el adaptador externo cuando se configura.

La consulta GCP implementada devuelve logs. El enmascarado filtra patrones de
credenciales y correo; no representa una clasificación exhaustiva de datos
personales. Las vistas de despliegue describen configuración y código, no una
comprobación del estado de los servicios cloud.

## Ejemplo: Redis no disponible

1. El operador selecciona `redis_down` y envía el formulario.
2. El proveedor mock genera cuatro señales con la ventana solicitada. El servicio
   les asigna `S01` a `S04`.
3. El baseline encuentra errores de conexión a Redis y propone `redis-cart` con
   confianza heurística de `0,7`. Es la regla definida en el código.
4. El investigador lee las herramientas de logs, métricas y trazas; el juez evalúa
   la hipótesis y aplica los controles deterministas de evidencia.
5. El baseline propone revisión humana. La política conserva la ruta `escalate` y
   `preview_node` registra la propuesta, con `executed=false`.
6. El reporte y los pasos quedan en `Analysis`; el servicio añade duración, fecha e
   identificador, y guarda una copia en el historial.

Con `missing_telemetry`, no llegan señales. El juez deja la confianza en cero y
solicita evidencia. El grafo permite una segunda ronda; después entrega
`insufficient_evidence`. Esta respuesta también es un análisis completado.

## Reglas que explican una decisión

| Acción | Confianza mínima | Condiciones adicionales |
|---|---:|---|
| `rollout-restart` | 0,75 | Deployment permitido y relacionado con la hipótesis |
| `rollout-undo` | 0,85 | Rollout de hasta 120 minutos y al menos dos revisiones |
| `scale` | 0,75 | Sin HPA; aumento de réplicas, con máximo de cinco |
| PR de manifiestos | 0,70 | Categoría de cambio permitida |
| PR de aplicación | 0,80 | Categoría de cambio permitida |

Además se exige respaldo del juez y namespace permitido. Para runbooks se excluyen
deployments protegidos y se aplican los límites de `Safety`: 30 minutos entre
acciones sobre el mismo destino y tres acciones por hora. En la entrada operativa
estos controles viven en el proceso; la consola crea sus dependencias por análisis
y termina siempre en una propuesta. La ruta PR del motor genera un artefacto local
para revisión; no abre por sí sola un pull request remoto.

## Cómo leer las vistas

- **C4:** contexto → contenedores → componentes → código. Un contenedor C4 es una
  aplicación o almacén lógico; el contenedor Docker aparece en la vista de despliegue.
- **Vistas C4:** siluetas azul oscuro para personas, azul para sistemas y
  contenedores, azul claro para componentes y gris para sistemas externos.
- **Verde en las otras vistas:** elementos implementados dentro de la aplicación o sus etapas.
- **Gris:** colaboradores, contexto o elementos externos, según la etiqueta.
- **Ámbar:** decisiones o notas de control.
- **Flechas continuas:** relación principal; la etiqueta indica su significado.
- **Flechas discontinuas:** integración opcional, referencia o frontera indicada.

Las vistas C4 usan figuras editables nativas de draw.io y una leyenda por página.
El nivel de código conserva sus clases UML. Cada diagrama declara su alcance; los
agentes no son servicios desplegados por separado. El nivel 4 desarrolla el
componente `AnalysisService`, mientras la vista de datos muestra sus contratos.

## Catálogo de diagramas
"""

FOOTER = """## Editar en draw.io

**[TiderOps_Arquitectura.drawio](TiderOps_Arquitectura.drawio)** contiene las 13 vistas
en páginas separadas. Abrirlo con la aplicación draw.io; cada figura, texto y
conector se puede editar. Las pestañas están numeradas del 01 al 13. Cada página
incluye su explicación y referencias al código.

Este archivo es el entregable editable. Las cuatro vistas previas C4 se exportan
desde él con `scripts/render_diagrams.py --sync-c4 --skip-render`. Una edición manual
en draw.io requiere repetir esa exportación para actualizar la galería.

La conversión inicial usa el importador nativo de draw.io Desktop 32.4.1. El script
`scripts/export_drawio.py` permite repetirla desde las fuentes conservadas y se
detiene si el archivo de destino ya existe. Para crear otra copia sin sobrescribir
las ediciones manuales, indicar `--output` con una ruta nueva:

```bash
.venv/bin/python scripts/export_drawio.py --output /tmp/TiderOps_Arquitectura.drawio
```

## Fuentes y vistas previas

Los archivos `source/*.mmd.txt` son las fuentes editables de Mermaid.
`catalog.json` mantiene las explicaciones y enlaces; `svg/` e `index.html` son las
salidas para leer, compartir o insertar en documentos. Cada SVG se puede ampliar
sin perder calidad. La galería funciona sin conexión a Internet.

El sufijo `.mmd.txt` mantiene los diagramas de desarrollo fuera del lector de
topología operativa, que incorpora archivos `.mmd` y `.mermaid`. Esta guía lleva
el tipo `guide` y no añade aristas al contexto del motor.

Instalar Mermaid CLI en una carpeta temporal y regenerar desde la raíz del proyecto:

```bash
npm install --prefix /tmp/tider-diagram-tools --no-audit --no-fund @mermaid-js/mermaid-cli@11.12.0
.venv/bin/python scripts/render_diagrams.py --mmdc /tmp/tider-diagram-tools/node_modules/.bin/mmdc
```

Si se utiliza un Chrome ya instalado, añadir `--chrome` con la ruta de su ejecutable.
Para actualizar sólo la guía y la galería a partir de SVG existentes, usar
`--skip-render`. El script valida rutas, catálogo y XML de todos los SVG antes de
generar la documentación. No instala dependencias dentro del proyecto.

## Referencias de la notación

El [modelo C4](https://c4model.com/diagrams) define las cuatro escalas principales.
La [vista de contenedores](https://c4model.com/diagrams/container) separa aplicaciones
y almacenes; la [vista de código](https://c4model.com/diagrams/code) desarrolla un
componente. El render utiliza [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli).
Las relaciones y decisiones de este catálogo se contrastaron con los archivos
del proyecto enlazados en cada vista.
"""

STYLE = """
:root{--ink:#173c54;--teal:#226c5a;--muted:#516675;--line:#d7e1e6;--paper:#f3f6f8}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:22px}
body{margin:0;color:var(--ink);background:var(--paper);font:16px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif}
a{color:var(--teal);text-underline-offset:3px}button{font:inherit;cursor:pointer}
aside{position:fixed;inset:0 auto 0 0;width:258px;background:#132f43;color:#fff;overflow:auto;padding:30px 20px}
.brand{font-size:25px;font-weight:750;letter-spacing:-1px}.eyebrow{text-transform:uppercase;font-size:11px;letter-spacing:2px;font-weight:700}
aside .eyebrow{color:#a7d7c7;margin-bottom:10px}aside p{color:#bccbd4;font-size:13px}
nav a{display:flex;gap:10px;color:#cdd9e0;text-decoration:none;padding:10px 8px;border-radius:6px;font-size:13px;line-height:1.35;margin:3px 0}
nav a span{color:#a7d7c7;font-variant-numeric:tabular-nums}nav a:hover,nav a.active{background:#26495e;color:#fff}
main{margin-left:258px;padding:48px 38px 70px;max-width:1600px}
header{max-width:1000px;margin-bottom:28px}h1{font-size:clamp(32px,3.5vw,51px);line-height:1.12;letter-spacing:-1.7px;margin:12px 0 20px}
.intro{font-size:18px;max-width:870px;color:var(--muted)}.meta{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0}
.pill{background:#e1eee9;color:#225744;font-size:12px;padding:5px 12px;border-radius:30px;font-weight:650}
.overview{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:28px}
.overview article{padding:20px;background:white;border:1px solid var(--line);border-radius:10px}.overview h2{font-size:16px;margin:0 0 8px}.overview p{font-size:14px;margin:0;color:var(--muted)}
.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:15px 0 22px}
.filter{border:1px solid #c6d5dc;background:white;border-radius:6px;padding:7px 13px;color:var(--ink)}.filter[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:white}
.diagram{background:white;border:1px solid var(--line);border-radius:12px;margin-bottom:32px;overflow:hidden;scroll-margin-top:22px}
.section-head{padding:26px 28px 20px;border-bottom:1px solid #e5ecf0}.category{font-size:12px;letter-spacing:1.4px;text-transform:uppercase;color:var(--teal);font-weight:700}
h2{font-size:25px;line-height:1.25;letter-spacing:-.5px;margin:10px 0}.question{color:var(--muted);margin:8px 0 0}
.image-wrap{padding:28px 18px 20px;background:white;display:flex;justify-content:center}
.diagram img{display:block;width:100%;height:auto;max-height:620px;object-fit:contain}
.actions{display:flex;gap:16px;flex-wrap:wrap;align-items:center;padding:0 28px 22px;border-bottom:1px solid var(--line);font-size:13px}
.open{border:1px solid var(--teal);background:var(--teal);color:white;padding:8px 15px;border-radius:6px}
.details{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:32px;padding:24px 28px 28px}
.details h3{font-size:14px;text-transform:uppercase;letter-spacing:1px;margin:0 0 10px}.details p,.details li{font-size:14px;color:#415b6a}.details p{margin-top:0}.details ol{padding-left:20px}.details li{margin-bottom:9px}
.refs{border-left:1px solid var(--line);padding-left:25px}.refs ul{padding-left:18px}.code-links{display:grid;gap:6px}.code-links a{font:12px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}
.legend{color:var(--muted);font-size:13px;margin-bottom:26px;border-top:1px solid var(--line);padding-top:18px}
footer{font-size:13px;color:var(--muted);padding:8px 0}footer a{margin-right:15px}
dialog{width:96vw;height:94vh;max-width:none;max-height:none;border:1px solid var(--line);border-radius:12px;padding:0;color:var(--ink)}dialog::backdrop{background:#102c40cf}
.modal-head{padding:12px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}.modal-head strong{font-size:16px}.modal-tools{display:flex;gap:8px}.modal-tools button{padding:6px 12px;border:1px solid var(--line);border-radius:5px;background:white;color:var(--ink)}
.canvas{height:calc(100% - 73px);overflow:auto;padding:20px;display:block}.canvas img{width:100%;max-width:none;display:block;height:auto;margin:auto}
[hidden]{display:none!important}@media(max-width:1100px){main{padding:32px 24px}.overview{grid-template-columns:1fr}.details{grid-template-columns:1fr}.refs{padding-left:0;border-left:0;border-top:1px solid var(--line);padding-top:20px}}
@media(max-width:760px){aside{position:static;width:100%;padding:22px}aside nav{display:none}aside p{margin-bottom:0}main{margin-left:0;padding:28px 16px}.section-head,.details{padding:22px}.actions{padding:0 22px 20px}h2{font-size:22px}.image-wrap{padding:20px 8px}.modal-head{padding:10px}.canvas{height:calc(100% - 110px)}}
@media print{aside,.toolbar,.actions,.overview,dialog{display:none!important}main{margin:0;padding:0;max-width:none}.diagram{break-before:page;border:0;overflow:visible}.details{display:block}.refs{border:0;padding:0}.diagram img{max-height:650px}body{background:white}.section-head{padding:10px 0}.image-wrap{padding:10px}a{color:inherit}}
"""

SCRIPT = """
const modal = document.querySelector('dialog');
const picture = document.getElementById('large-image');
let zoom = 100;
document.querySelectorAll('.open').forEach(button => button.addEventListener('click', () => {
  const section = button.closest('.diagram');
  const image = section.querySelector('img');
  picture.src = image.getAttribute('src'); picture.alt = image.alt;
  document.getElementById('modal-title').textContent = image.alt;
  zoom = 100; picture.style.width = '100%'; modal.showModal();
}));
document.getElementById('close').addEventListener('click', () => modal.close());
document.querySelectorAll('[data-zoom]').forEach(button => button.addEventListener('click', () => {
  zoom = button.dataset.zoom === 'fit' ? 100 : Math.max(50, Math.min(400, zoom + Number(button.dataset.zoom)));
  picture.style.width = zoom + '%';
}));
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  document.querySelectorAll('.diagram').forEach(section => { section.hidden = button.dataset.category !== 'Todos' && section.dataset.category !== button.dataset.category; });
}));
document.querySelectorAll('nav a').forEach(link => link.addEventListener('click', () => {
  document.querySelector('.filter[data-category="Todos"]').click();
}));
const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      document.querySelectorAll('nav a').forEach(link => link.classList.toggle('active', link.getAttribute('href') === '#' + entry.target.id));
    }
  });
}, {rootMargin:'-10% 0px -65% 0px'});
document.querySelectorAll('.diagram').forEach(section => observer.observe(section));
"""


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def validate(catalog: dict) -> None:
    ids = [item["id"] for item in catalog["diagrams"]]
    if len(ids) != len(set(ids)):
        raise ValueError("El catálogo contiene IDs duplicados.")
    for item in catalog["diagrams"]:
        if not (ROOT / "source" / f"{item['id']}.mmd.txt").is_file():
            raise ValueError(f"Falta la fuente de {item['id']}")
        for relative in item["files"]:
            if not (PROJECT / relative).is_file():
                raise ValueError(f"Referencia inexistente: {relative}")


def sync_c4_previews(catalog: dict, drawio: str) -> None:
    """Export C4 previews from the same editable figures delivered to the user."""
    atlas = ET.parse(ROOT / "TiderOps_Arquitectura.drawio").getroot()
    with tempfile.TemporaryDirectory(prefix="tider-c4-previews-") as directory:
        for item in catalog["diagrams"]:
            if item["category"] != "C4":
                continue
            page = atlas.find(f"diagram[@id='{item['id']}']")
            if page is None:
                raise ValueError(f"Falta la página C4: {item['id']}")
            page = ET.fromstring(ET.tostring(page))
            root = page.find("mxGraphModel/root")
            for cell in list(root):
                if cell.get("id", "").startswith("atlas-"):
                    root.remove(cell)
            document = ET.Element("mxfile")
            document.append(page)
            source = Path(directory) / f"{item['id']}.drawio"
            ET.ElementTree(document).write(source, encoding="utf-8", xml_declaration=True)
            destination = ROOT / "svg" / f"{item['id']}.svg"
            subprocess.run(
                [
                    drawio,
                    "--disable-update",
                    "--export",
                    "--format",
                    "svg",
                    "--border",
                    "20",
                    "--output",
                    str(destination),
                    str(source),
                ],
                check=True,
                timeout=90,
            )


def render(catalog: dict, mmdc: str, chrome: str | None) -> None:
    (ROOT / "svg").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tider-mermaid-") as temp:
        browser_config = Path(temp) / "puppeteer.json"
        if chrome:
            browser_config.write_text(json.dumps({"executablePath": chrome}), encoding="utf-8")
        for item in catalog["diagrams"]:
            if item["category"] == "C4":
                continue  # Native figures are exported from the editable atlas.
            name = item["id"]
            source = ROOT / "source" / f"{name}.mmd.txt"
            destination = ROOT / "svg" / f"{name}.svg"
            config = ROOT / "mermaid-config.json"
            if destination.exists() and destination.stat().st_mtime > max(
                source.stat().st_mtime, config.stat().st_mtime
            ):
                ET.parse(destination)
                continue
            command = [
                mmdc,
                "-i",
                str(source),
                "-o",
                str(destination),
                "-c",
                str(config),
                "-b",
                "white",
                "-w",
                "1800",
            ]
            if chrome:
                command += ["-p", str(browser_config)]
            subprocess.run(command, check=True, timeout=120, cwd=PROJECT)
            print(f"SVG: {name}", flush=True)


def build_markdown(catalog: dict) -> None:
    parts = [
        '---\ntype: guide\ntitle: "Atlas de arquitectura de TiderOps"\n'
        f"updated: {catalog['reviewed']}\n---\n",
        "# Atlas de arquitectura de TiderOps\n",
        "**[Abrir atlas editable en draw.io](TiderOps_Arquitectura.drawio)** · 13 páginas. "
        "[Galería de vistas previas](index.html).\n",
        OVERVIEW + "\n",
        DETAIL,
    ]
    parts.append("| Vista | Pregunta |\n|---|---|")
    for item in catalog["diagrams"]:
        parts.append(f"| [{item['title']}](#{item['id']}) | {item['question']} |")
    for item in catalog["diagrams"]:
        name = item["id"]
        parts.extend(
            [
                f'\n<a id="{name}"></a>\n\n### {item["title"]}\n',
                f"**{item['question']}**\n\n{item['summary']}\n",
                f"![{item['title']}](svg/{name}.svg)\n",
                f"[SVG ampliable](svg/{name}.svg) · [Fuente Mermaid](source/{name}.mmd.txt)\n",
                "\n".join(f"{i}. {point}" for i, point in enumerate(item["reading"], 1)),
                "\n**Decisiones relacionadas:** " + " ".join(item["decisions"]) + "\n",
                "**Código:** "
                + ", ".join(f"[{path}](../../{quote(path)})" for path in item["files"])
                + ".\n",
            ]
        )
    parts.append(FOOTER)
    (ROOT / "README.md").write_text("\n".join(parts), encoding="utf-8")


def build_html(catalog: dict) -> None:
    nav, sections = [], []
    for index, item in enumerate(catalog["diagrams"], 1):
        name, title = item["id"], esc(item["title"])
        nav.append(f'<a href="#{name}"><span>{index:02}</span>{title}</a>')
        reading = "".join(f"<li>{esc(point)}</li>" for point in item["reading"])
        decisions = "".join(f"<li>{esc(point)}</li>" for point in item["decisions"])
        code = "".join(f'<a href="../../{quote(path)}">{esc(path)}</a>' for path in item["files"])
        sections.append(f'''<section class="diagram" id="{name}" data-category="{esc(item["category"])}">
<div class="section-head"><div class="category">{index:02} / {esc(item["category"])}</div>
<h2>{title}</h2><p class="question">{esc(item["question"])}</p></div>
<div class="image-wrap"><img src="svg/{name}.svg" alt="{title}" loading="lazy"></div>
<div class="actions"><button class="open" aria-label="Ampliar {title}">Ampliar diagrama ↗</button>
<a href="svg/{name}.svg" target="_blank" rel="noopener">Abrir SVG</a>
<a href="svg/{name}.svg" download>Descargar SVG</a><a href="source/{name}.mmd.txt" download>Fuente Mermaid</a></div>
<div class="details"><div><h3>Cómo funciona</h3><p>{esc(item["summary"])}</p><ol>{reading}</ol></div>
<div class="refs"><h3>Por qué se implementó así</h3><ul>{decisions}</ul><h3>Dónde está el código</h3><div class="code-links">{code}</div></div></div></section>''')
    categories = ["Todos", *dict.fromkeys(item["category"] for item in catalog["diagrams"])]
    filters = "".join(
        f'<button class="filter" data-category="{esc(c)}" aria-pressed="{str(c == "Todos").lower()}">{esc(c)}</button>'
        for c in categories
    )
    output = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TiderOps · Atlas de arquitectura</title><style>{STYLE}</style></head><body>
<aside><div class="eyebrow">Documentación técnica</div><div class="brand">TiderOps</div><p>Atlas de arquitectura<br>Del sistema a sus decisiones.</p><nav aria-label="Diagramas">{"".join(nav)}</nav></aside>
<main><header><div class="eyebrow">Implementación · v{esc(catalog["version"])}</div><h1>Cómo está construido<br>TiderOps.</h1><p class="intro">{esc(OVERVIEW)}</p>
<div class="meta"><span class="pill">13 diagramas</span><span class="pill">4 niveles C4</span><span class="pill">Código revisado · {esc(catalog["reviewed"])}</span></div>
<p><a href="TiderOps_Arquitectura.drawio" download><strong>Descargar atlas editable en draw.io · 13 páginas →</strong></a></p>
<a href="README.md">Leer la guía completa y el ejemplo de Redis →</a></header>
<div class="overview"><article><h2>01 · Estructura</h2><p>Empieza por C4: sistema, aplicaciones, componentes y un caso de uso en código.</p></article><article><h2>02 · Comportamiento</h2><p>Sigue una solicitud, las rondas del grafo y las reglas que producen cada decisión.</p></article><article><h2>03 · Implementación</h2><p>Relaciona datos, despliegue y módulos con los archivos concretos que los implementan.</p></article></div>
<div class="toolbar" aria-label="Filtrar diagramas">{filters}</div>
<div class="legend">C4: personas azul oscuro, sistemas y contenedores azules, componentes azul claro y externos grises.
Otras vistas: verde para elementos internos, gris para contexto y ámbar para controles.
Cada flecha indica su relación; las discontinuas señalan opciones o referencias según la vista.
Los agentes se ejecutan dentro del proceso Python.</div>
{"".join(sections)}
<footer><p>Fuentes: código enlazado en cada vista y <a href="../decisions.md">decisiones de diseño</a>.</p>
<a href="https://c4model.com/diagrams">Notación C4</a><a href="https://github.com/mermaid-js/mermaid-cli">Mermaid CLI</a><a href="README.md#editar-y-regenerar">Editar y regenerar</a></footer></main>
<dialog aria-labelledby="modal-title"><div class="modal-head"><strong id="modal-title"></strong><div class="modal-tools"><button data-zoom="-25" aria-label="Reducir">−</button><button data-zoom="fit">Ajustar</button><button data-zoom="25" aria-label="Aumentar">+</button><button id="close">Cerrar ✕</button></div></div><div class="canvas"><img id="large-image" alt=""></div></dialog>
<script>{SCRIPT}</script></body></html>"""
    (ROOT / "index.html").write_text(output, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mmdc", default="mmdc")
    parser.add_argument("--chrome", help="Optional installed Chrome executable")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--sync-c4", action="store_true", help="Export C4 previews from the draw.io atlas")
    parser.add_argument(
        "--drawio", default=shutil.which("drawio") or "/Applications/draw.io.app/Contents/MacOS/draw.io"
    )
    args = parser.parse_args()
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    validate(catalog)
    if args.sync_c4 or not args.skip_render:
        sync_c4_previews(catalog, args.drawio)
    if not args.skip_render:
        render(catalog, args.mmdc, args.chrome)
    for item in catalog["diagrams"]:
        svg = ET.parse(ROOT / "svg" / f"{item['id']}.svg").getroot()
        if svg.tag != "{http://www.w3.org/2000/svg}svg" or not svg.get("viewBox"):
            raise ValueError(f"SVG inválido: {item['id']}")
    build_markdown(catalog)
    build_html(catalog)
    print(f"{len(catalog['diagrams'])} diagramas y sus referencias validados. Galería: {ROOT / 'index.html'}")


if __name__ == "__main__":
    main()

"""Create the editable draw.io atlas using draw.io's native Mermaid importer.

Existing .drawio files are preserved unless --replace is explicitly requested.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs" / "diagrams"
OUTPUT = ROOT / "TiderOps_Arquitectura.drawio"
PAGE_NAMES = [
    "C4 Contexto",
    "C4 Contenedores",
    "C4 Componentes",
    "C4 Código",
    "Secuencia de análisis",
    "Flujo de agentes",
    "Política de decisión",
    "Modelo de datos",
    "Flujo de evidencia",
    "Despliegue",
    "Dependencias",
    "Decisiones de diseño",
    "Estados del análisis",
]


def add_text(root, identifier, value, x, y, width, height, style):
    cell = ET.SubElement(root, "mxCell", id=identifier, value=value, style=style, vertex="1", parent="1")
    ET.SubElement(
        cell,
        "mxGeometry",
        x=str(x),
        y=str(y),
        width=str(width),
        height=str(height),
        attrib={"as": "geometry"},
    )


def describe(model, item):
    """Add editable title and reading notes outside the imported diagram."""
    root = model.find("root")
    right, bottom = 0.0, 0.0
    for cell in root.iter("mxCell"):
        if cell.get("parent") != "1":
            continue
        geometry = cell.find("mxGeometry")
        if geometry is None:
            continue
        if cell.get("vertex") == "1":
            x, y = float(geometry.get("x", 0)), float(geometry.get("y", 0))
            right = max(right, x + float(geometry.get("width", 0)))
            bottom = max(bottom, y + float(geometry.get("height", 0)))
            geometry.set("y", str(y + 120))
        elif cell.get("edge") == "1":
            for point in geometry.findall("Array/mxPoint") + [
                p for p in geometry.findall("mxPoint") if p.get("as") != "offset"
            ]:
                right = max(right, float(point.get("x", 0)))
                bottom = max(bottom, float(point.get("y", 0)))
                point.set("y", str(float(point.get("y", 0)) + 120))
    width = max(1100, right + 540)
    text_style = "text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;verticalAlign=top;spacing=0;fontFamily=Arial;"
    add_text(
        root,
        "atlas-title",
        html.escape(item["title"]),
        24,
        20,
        width - 48,
        45,
        text_style + "fontSize=28;fontStyle=1;fontColor=#173C54;",
    )
    add_text(
        root,
        "atlas-question",
        html.escape(item["question"]),
        24,
        72,
        width - 48,
        38,
        text_style + "fontSize=16;fontColor=#516675;",
    )
    sections = [
        ("Qué muestra", [item["summary"]]),
        ("Cómo leerlo", item["reading"]),
        ("Decisiones de implementación", item["decisions"]),
        ("Código de referencia", item["files"]),
    ]
    chunks = []
    lines = 0
    for title, paragraphs in sections:
        chunks.append(f"<b>{title}</b>")
        lines += 2
        for paragraph in paragraphs:
            chunks.append(html.escape(paragraph))
            lines += max(1, len(textwrap.wrap(paragraph, 52))) + 1
    note_height = lines * 20 + 40
    value = '<div style="line-height:1.4;overflow-wrap:anywhere">' + "<br><br>".join(chunks) + "</div>"
    add_text(
        root,
        "atlas-notes",
        value,
        right + 60,
        140,
        440,
        note_height,
        "rounded=1;arcSize=8;html=1;whiteSpace=wrap;align=left;verticalAlign=top;spacing=18;"
        "fontFamily=Arial;fontSize=14;fontColor=#173C54;fillColor=#F3F6F8;strokeColor=#D7E1E6;",
    )
    model.set("page", "0")
    model.set("pageWidth", str(round(width)))
    model.set("pageHeight", str(round(max(bottom + 180, note_height + 180))))
    model.set("background", "#ffffff")


def refine_container_connections(model):
    """Separate the request/response paths produced by the native importer."""
    for obj in model.findall("root/UserObject"):
        key = obj.get("mermaidId", "")
        cell = obj.find("mxCell")
        geometry = cell.find("mxGeometry")
        if key in ("e:ui->api#0", "e:api->ui#0"):
            request = key == "e:ui->api#0"
            style = re.sub(r"(?:exit|entry)[XY]=[^;]*;", "", cell.get("style", ""))
            style += (
                "exitX=0.25;exitY=1;entryX=0.25;entryY=0;"
                if request
                else "exitX=0.8;exitY=0;entryX=0.8;entryY=1;"
            )
            cell.set("style", style)
            points = geometry.find("Array")
            if points is not None:
                geometry.remove(points)
            points = ET.SubElement(geometry, "Array", {"as": "points"})
            ET.SubElement(points, "mxPoint", x="270" if request else "510", y="175")
            obj.set("label", "HTTP/JSON<br>POST y GET" if request else "HTTP<br>Sirve HTML, CSS, JS")
        elif key in ("e:api->cloud#0", "e:api->model#0"):
            cloud = key == "e:api->cloud#0"
            obj.set("label", "EVIDENCE_MODE=gcp<br>HTTPS" if cloud else "LLM_PROVIDER=anthropic<br>HTTPS")
            geometry.set("x", "0.4" if cloud else "0.65")


def validate(model):
    root = model.find("root")
    ids = {element.get("id") for element in root.iter() if element.get("id")}
    cells = list(root.iter("mxCell"))
    if len(ids) != sum(bool(element.get("id")) for element in root.iter()):
        raise ValueError("IDs duplicados dentro de una página.")
    vertices, edges = 0, 0
    for cell in cells:
        vertices += cell.get("vertex") == "1"
        edges += cell.get("edge") == "1"
        if "shape=image" in cell.get("style", "") or "image=data:" in cell.get("style", ""):
            raise ValueError("Se encontró una imagen en lugar de figuras editables.")
        for key in ("source", "target", "parent"):
            if cell.get(key) and cell.get(key) not in ids:
                raise ValueError(f"Referencia inválida: {key}={cell.get(key)}")
    if not vertices or not edges:
        raise ValueError("La página debe contener figuras y conectores editables.")
    return vertices, edges


def style_c4(model, page_id):
    """Apply native C4 figures without changing identities or relationships."""
    if not page_id.startswith(("01-c4-", "02-c4-", "03-c4-", "04-c4-")):
        return
    if model.get("c4Style") == "classic-v1":
        return
    root = model.find("root")
    level = int(page_id[:2])
    objects = {obj.get("mermaidId"): obj for obj in root.findall("UserObject")}
    palette = {
        "person": ("#08427B", "#052E56", "#FFFFFF"),
        "system": ("#1168BD", "#0B4884", "#FFFFFF"),
        "container": ("#438DD5", "#2166A8", "#FFFFFF"),
        "component": ("#85BBF0", "#4F8FCB", "#173C54"),
        "external": ("#6B7280", "#4B5563", "#FFFFFF"),
    }
    boundaries = {"n:sys", "n:backend"}
    people = {"n:op", "n:team"} if level == 1 else {"n:user"} if level == 2 else set()
    internal = {
        1: {"n:tider"},
        2: {"n:ui", "n:api", "n:resources"},
        3: {key for key in objects if key.startswith("n:")} - {"n:backend", "n:ui", "n:cloud", "n:llm"},
    }
    # Increase vertical gaps for person silhouettes and explicit type labels.
    if level < 4:
        for cell in root.iter("mxCell"):
            if cell.get("id", "").startswith("atlas-"):
                continue
            geometry = cell.find("mxGeometry")
            if geometry is None:
                continue
            if cell.get("vertex") == "1":
                y = float(geometry.get("y", 0))
                geometry.set("y", str(170 + (y - 128) * 1.4 if cell.get("parent") == "1" else y * 1.4))
            for point in geometry.findall("Array/mxPoint"):
                y = float(point.get("y", 0))
                point.set("y", str(170 + (y - 128) * 1.4 if cell.get("parent") == "1" else y * 1.4))
    for key, obj in objects.items():
        cell = obj.find("mxCell")
        geometry = cell.find("mxGeometry")
        if cell.get("edge") == "1":
            style = cell.get("style", "")
            style = re.sub(r"(?:strokeColor|fontColor|labelBackgroundColor)=[^;]*;", "", style)
            cell.set("style", style + "strokeColor=#526170;fontColor=#334155;labelBackgroundColor=#FFFFFF;")
            continue
        if level == 4:
            style = cell.get("style", "").replace("#dceee9", "#E8F2FC").replace("#347d67", "#438DD5")
            cell.set("style", style)
            continue
        if key in boundaries:
            geometry.set("height", str(float(geometry.get("height")) * 1.4))
            cell.set(
                "style",
                "html=1;whiteSpace=wrap;verticalAlign=top;align=left;spacing=12;"
                "dashed=1;dashPattern=8 4;strokeWidth=2;fillColor=none;strokeColor=#64748B;"
                "fontColor=#334155;fontFamily=Arial;fontSize=18;fontStyle=1;",
            )
            continue
        if key == "n:memory":
            cell.set(
                "style",
                "shape=note;html=1;whiteSpace=wrap;size=15;spacing=12;"
                "fillColor=#F8FAFC;strokeColor=#94A3B8;fontColor=#334155;fontFamily=Arial;fontSize=14;",
            )
            geometry.set("height", "120")
            obj.set("label", obj.get("label").replace("\n", "<br>"))
            continue
        role = (
            "person"
            if key in people
            else (
                {1: "system", 2: "container", 3: "component"}[level] if key in internal[level] else "external"
            )
        )
        if level == 3 and key == "n:ui":
            role = "container"
        fill, stroke, font = palette[role]
        shape = "shape=mxgraph.c4.person2;" if role == "person" else "rounded=1;arcSize=8;"
        if key == "n:resources":
            shape = "shape=cylinder3;size=15;boundedLbl=1;"
        if key == "n:ui":
            shape = "shape=mxgraph.c4.webBrowserContainer2;strokeColor2=#2166A8;spacingTop=22;"
        cell.set(
            "style",
            shape + f"html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
            f"fontColor={font};fontFamily=Arial;fontSize=14;align=center;spacing=10;strokeWidth=1.5;",
        )
        geometry.set("height", "190" if role == "person" else "130")
        if role == "person" and float(geometry.get("width")) < 200:
            old_width = float(geometry.get("width"))
            geometry.set("x", str(float(geometry.get("x")) - (200 - old_width) / 2))
            geometry.set("width", "200")
        lines = obj.get("label", "").replace("<br/>", "\n").replace("<br>", "\n").splitlines()
        if level == 3 and role == "component":
            lines.insert(1, "[Componente: Python]")
        if key == "n:tider":
            lines[1] = "[Sistema de software]"
        if key == "n:ui" and level == 3:
            lines = ["Consola web", "[Contenedor: HTML, CSS y JavaScript]", "Cliente del backend"]
        obj.set("label", f"<b>{html.escape(lines[0])}</b><br>" + "<br>".join(map(html.escape, lines[1:])))
        obj.set("c4Type", role)
    if level == 2:
        person = objects["n:user"].find("mxCell/mxGeometry")
        person.set("y", str(float(person.get("y")) - 35))
        for target, x, y in (("cloud", 1297.5, 720), ("model", 1585.5, 805)):
            edge = objects[f"e:api->{target}#0"].find("mxCell")
            edge.set(
                "style",
                "edgeStyle=orthogonalEdgeStyle;rounded=1;dashed=1;html=1;endArrow=block;"
                "exitX=1;exitY=" + ("0.35" if target == "cloud" else "0.8") + ";entryX=0.5;entryY=0;"
                "strokeColor=#526170;fontColor=#334155;fontSize=16;labelBackgroundColor=#FFFFFF;",
            )
            geometry = edge.find("mxGeometry")
            geometry.clear()
            geometry.attrib.update(relative="1", x="-0.25", y="-18", **{"as": "geometry"})
            points = ET.SubElement(geometry, "Array", {"as": "points"})
            ET.SubElement(points, "mxPoint", x=str(x), y=str(y))
    # Keep UML member compartments readable while matching the C4 palette.
    if level == 4:
        for cell in root.findall("mxCell"):
            cell.set(
                "style", cell.get("style", "").replace("#dceee9", "#E8F2FC").replace("#347d67", "#438DD5")
            )
    bottom = max(
        float(c.find("mxGeometry").get("y", 0)) + float(c.find("mxGeometry").get("height", 0))
        for c in root.iter("mxCell")
        if c.get("vertex") == "1" and c.get("parent") == "1" and not c.get("id", "").startswith("atlas-")
    )
    legend_y = bottom + 55
    legend = (
        "<b>Leyenda · C4</b><br>"
        "Persona: silueta azul oscuro · Sistema: azul · Contenedor: azul medio · Componente: azul claro.<br>"
        "Gris: sistema externo · Cilindro: archivos empaquetados · Nota: detalle interno.<br>"
        "Límite discontinuo: sistema o contenedor · Flecha continua: relación principal "
        "· Flecha discontinua: integración opcional."
        if level < 4
        else "<b>Leyenda · C4, nivel de código</b><br>"
        "Clases UML: nombre, atributos y operaciones · «Protocol»: contrato de Python.<br>"
        "Flecha: dependencia entre clases · Azul claro: código del caso de uso."
    )
    notes = root.find("mxCell[@id='atlas-notes']/mxGeometry")
    legend_width = min(740, float(notes.get("x")) - 48) if notes is not None else 740
    add_text(
        root,
        "c4-legend",
        legend,
        24,
        legend_y,
        legend_width,
        150,
        "rounded=1;arcSize=8;html=1;whiteSpace=wrap;align=left;verticalAlign=top;spacing=14;"
        "fontFamily=Arial;fontSize=14;fontColor=#334155;fillColor=#F8FAFC;strokeColor=#CBD5E1;",
    )
    model.set("pageHeight", str(max(float(model.get("pageHeight", 0)), legend_y + 180)))
    model.set("c4Style", "classic-v1")


def assemble(folder, catalog, destination):
    atlas = ET.Element("mxfile", host="draw.io", compressed="false")
    for index, item in enumerate(catalog["diagrams"], 1):
        imported = ET.parse(folder / f"{item['id']}.xml").getroot()
        model = imported.find("diagram/mxGraphModel")
        if model is None:
            raise ValueError(f"Sin modelo editable: {item['id']}")
        if item["id"] == "02-c4-containers":
            refine_container_connections(model)
        describe(model, item)
        style_c4(model, item["id"])
        vertices, edges = validate(model)
        page = ET.SubElement(atlas, "diagram", id=item["id"], name=f"{index:02} · {PAGE_NAMES[index - 1]}")
        page.append(model)
        print(f"{index:02}: {vertices} figuras/textos y {edges} conectores editables")
    ET.indent(atlas, space="  ")
    destination.write_bytes(ET.tostring(atlas, encoding="utf-8", xml_declaration=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drawio", default=shutil.which("drawio") or "/Applications/draw.io.app/Contents/MacOS/draw.io"
    )
    parser.add_argument("--xml-dir", type=Path, help="Reuse native, uncompressed draw.io exports")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--replace", action="store_true", help="Replace the output, including manual changes")
    args = parser.parse_args()
    if args.output.exists() and not args.replace:
        parser.error("El archivo ya existe. Usa otro --output o --replace para reemplazarlo explícitamente.")
    catalog = json.loads((ROOT / "catalog.json").read_text())
    if args.xml_dir:
        assemble(args.xml_dir, catalog, args.output)
    else:
        with tempfile.TemporaryDirectory(prefix="tider-drawio-") as directory:
            source = Path(directory) / "source"
            exported = Path(directory) / "xml"
            source.mkdir()
            exported.mkdir()
            config = json.loads((ROOT / "mermaid-config.json").read_text())
            for item in catalog["diagrams"]:
                code = (ROOT / "source" / f"{item['id']}.mmd.txt").read_text()
                (source / f"{item['id']}.mmd").write_text("%%{init: " + json.dumps(config) + "}%%\n" + code)
            subprocess.run(
                [
                    args.drawio,
                    "--disable-update",
                    "--export",
                    "--format",
                    "xml",
                    "--uncompressed",
                    "--mermaid-image",
                    "false",
                    "--timeout",
                    "45",
                    "--output",
                    str(exported),
                    str(source),
                ],
                check=True,
                timeout=660,
            )
            assemble(exported, catalog, args.output)
    print(f"Archivo draw.io: {args.output}")


if __name__ == "__main__":
    main()

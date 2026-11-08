"""Build the technical handover DOCX from the reviewed Markdown source."""
from pathlib import Path
from datetime import datetime, timezone

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "handover" / "2026-11-08" / "TECHNICAL_HANDOVER.md"
OUTPUT = ROOT / "docs" / "deliverables" / "Postcards Техническое описание и передача.docx"


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def configure(doc):
    section = doc.sections[0]
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.7)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(1.8)

    styles = doc.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(10.5)
    styles["Normal"].font.color.rgb = RGBColor(0, 0, 0)
    styles["Normal"].paragraph_format.space_after = Pt(5)
    styles["Normal"].paragraph_format.line_spacing = 1.08
    for name, size in (("Title", 22), ("Heading 1", 15), ("Heading 2", 12)):
        styles[name].font.name = "Arial"
        styles[name].font.size = Pt(size)
        styles[name].font.bold = True
        styles[name].font.color.rgb = RGBColor(0, 0, 0)
        styles[name].paragraph_format.keep_with_next = True
        styles[name].paragraph_format.space_before = Pt(10)
        styles[name].paragraph_format.space_after = Pt(4)

    header = section.header.paragraphs[0]
    header.text = "Postcards / Архивный блок Inheritance · техническая передача"
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for run in header.runs:
        run.font.name = "Arial"
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(90, 90, 90)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("8 ноября 2026 · ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    for run in footer.runs:
        run.font.name = "Arial"
        run.font.size = Pt(8)


def add_code(doc, lines):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    cell = table.cell(0, 0)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    set_cell_shading(cell, "F2F2F2")
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run("\n".join(lines))
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)


def add_inline_runs(paragraph, text):
    parts = text.split("`")
    for index, part in enumerate(parts):
        run = paragraph.add_run(part)
        run.font.name = "Consolas" if index % 2 else "Arial"
        if index % 2:
            run.font.size = Pt(9.5)


def build():
    doc = Document()
    configure(doc)
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    in_code = False
    code = []
    first_heading = True

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                add_code(doc, code)
                code = []
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if not line:
            continue
        if line.startswith("# "):
            p = doc.add_paragraph(style="Title")
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.add_run(line[2:])
            first_heading = False
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=1)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=2)
        elif line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            add_inline_runs(p, line[2:])
        elif len(line) > 3 and line[0].isdigit() and ". " in line[:4]:
            p = doc.add_paragraph(style="List Number")
            add_inline_runs(p, line.split(". ", 1)[1])
        else:
            p = doc.add_paragraph()
            add_inline_runs(p, line)

    doc.core_properties.title = "Postcards — техническое описание и передача"
    doc.core_properties.subject = "Сборка, развертывание, резервирование, ограничения и условия передачи"
    doc.core_properties.author = "Григорий Орлов"
    doc.core_properties.modified = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import pymupdf as fitz
from .layout_geometry import LINE_HEIGHT, align_template_text, body_line_height


class TextOverflowError(ValueError):
    pass


def prepare_textbox(page, rect, text, fontname, fontsize, lineheight=LINE_HEIGHT, **kwargs):
    """Wrap once, and measure complete CSS line boxes at the requested size."""
    shape = page.new_shape()
    roomy = fitz.Rect(rect.x0, rect.y0, rect.x1,
                      rect.y0 + max(rect.height, (len(text) + 2) * fontsize * lineheight))
    shape.insert_textbox(roomy, text, fontname=fontname, fontsize=fontsize,
                         lineheight=lineheight, **kwargs)
    rows = len(re.findall(r'1 0 0 1 [^ ]+ [^ ]+ Tm', shape.text_cont))
    if text.endswith('\n'):
        rows += 1
    return shape, rect.height - rows * fontsize * lineheight


def _finish_textbox(shape, font_path, fontsize, justified, lineheight=LINE_HEIGHT):
    """Use explicit CID glyph advances and absolute baseline spacing.

    PDF word spacing (Tw) is ignored for multibyte Identity-H fonts. PyMuPDF's
    textbox also multiplies baseline advances by the font ascender, unlike CSS.
    Keep its wrapping, but encode the intended positions explicitly.
    """
    content = shape.text_cont
    positions = list(re.finditer(r'1 0 0 1 ([^ ]+) ([^ ]+) Tm', content))
    if positions:
        font = fitz.Font(fontfile=str(font_path))
        leading = max(0, (lineheight - (font.ascender - font.descender)) * fontsize / 2)
        first_y = float(positions[0].group(2)) - leading
        line = iter(range(len(positions)))
        content = re.sub(r'1 0 0 1 ([^ ]+) ([^ ]+) Tm',
            lambda match: f'1 0 0 1 {match.group(1)} {first_y - next(line) * fontsize * lineheight:.6f} Tm', content)
    if justified:
        space = f'{fitz.Font(fontfile=str(font_path)).has_glyph(32):04x}'

        def explicit_spacing(match):
            spacing, attributes, encoded = float(match.group(1)), match.group(2), match.group(3)
            if spacing <= 0:
                return match.group(0)
            chunks, current = [], ''
            for offset in range(0, len(encoded), 4):
                glyph = encoded[offset:offset + 4]
                current += glyph
                if glyph.lower() == space:
                    chunks.append(f'<{current}> {-spacing * 1000 / fontsize:.6f}')
                    current = ''
            if current:
                chunks.append(f'<{current}>')
            return '0 Tw ' + attributes + '[' + ' '.join(chunks) + ']TJ'

        content = re.sub(r'([-+0-9.eE]+) Tw ([^\n]*?)\[<([0-9a-fA-F]+)>\]TJ', explicit_spacing, content)
    shape.text_cont = content
    shape.commit(overlay=True)


FONT_CANDIDATES = {
    "Times New Roman": {
        "regular": (Path("C:/Windows/Fonts/times.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")),
        "bold": (Path("C:/Windows/Fonts/timesbd.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf")),
        "italic": (Path("C:/Windows/Fonts/timesi.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf")),
        "bolditalic": (Path("C:/Windows/Fonts/timesbi.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf")),
    },
    "Arial": {
        "regular": (Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
        "bold": (Path("C:/Windows/Fonts/arialbd.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        "italic": (Path("C:/Windows/Fonts/ariali.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf")),
        "bolditalic": (Path("C:/Windows/Fonts/arialbi.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf")),
    },
    "Georgia": {
        "regular": (Path("C:/Windows/Fonts/georgia.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")),
        "bold": (Path("C:/Windows/Fonts/georgiab.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf")),
        "italic": (Path("C:/Windows/Fonts/georgiai.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf")),
        "bolditalic": (Path("C:/Windows/Fonts/georgiaz.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf")),
    },
    "Courier New": {
        "regular": (Path("C:/Windows/Fonts/cour.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")),
        "bold": (Path("C:/Windows/Fonts/courbd.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")),
        "italic": (Path("C:/Windows/Fonts/couri.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf")),
        "bolditalic": (Path("C:/Windows/Fonts/courbi.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf")),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _font_path(family="Arial", bold=False, italic=False) -> Path | None:
    explicit = os.environ.get("STUDIO_FONT_FILE")
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    variant = "bolditalic" if bold and italic else "bold" if bold else "italic" if italic else "regular"
    if family == "Times New Roman":
        name = {"regular": "times.ttf", "bold": "timesbd.ttf", "italic": "timesi.ttf", "bolditalic": "timesbi.ttf"}[variant]
        bundled = Path(__file__).resolve().parents[1] / "fonts" / name
        if bundled.is_file():
            return bundled
    candidates = FONT_CANDIDATES.get(family, FONT_CANDIDATES["Arial"]).get(variant, ())
    return next((path for path in candidates if path.is_file()), None)


def _color(value: str, default=(0.07, 0.07, 0.07)):
    value = str(value or "").lstrip("#")
    if len(value) != 6:
        return default
    try:
        return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))
    except ValueError:
        return default


def render_document(template: Path, content: dict, assets_root: Path, output: Path) -> None:
    if not template.is_file():
        raise FileNotFoundError(f"PDF-шаблон не найден: {template}")
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(template)
    pages = align_template_text(content.get("pages") or {})
    maximum_page = max((int(number) for number in pages), default=len(doc))
    if maximum_page > len(doc):
        width, height = doc[0].rect.width, doc[0].rect.height
        while len(doc) < maximum_page:
            doc.new_page(width=width, height=height)
    for page_number, raw_items in pages.items():
        index = int(page_number) - 1
        if not 0 <= index < len(doc):
            continue
        page = doc[index]
        bounds = page.rect
        ordered_items = sorted(raw_items, key=lambda value: value.get("type") != "page-background")
        if any(item.get("type") == "page-background" for item in ordered_items):
            width, height = bounds.width, bounds.height
            doc.new_page(pno=index, width=width, height=height)
            doc.delete_page(index + 1)
            page = doc[index]
            bounds = page.rect
        for item in ordered_items:
            x = float(item.get("x", 0)) * bounds.width
            y = float(item.get("y", 0)) * bounds.height
            w = float(item.get("w", 0.2)) * bounds.width
            h = float(item.get("h", 0.1)) * bounds.height
            rect = fitz.Rect(x, y, x + w, y + h)
            kind = item.get("type")
            if kind == "page-background":
                page.draw_rect(bounds, color=None, fill=_color(item.get("color"), (1, 1, 1)), overlay=True)
            elif kind == "cover":
                page.draw_rect(rect, color=None, fill=_color(item.get("color"), (1, 1, 1)), overlay=True)
            elif kind == "image":
                if item.get("missing"):
                    page.draw_rect(rect, color=_color("#a8a8a8"), fill=(0, 0, 0), width=.5,
                                   dashes="[6 6] 0", overlay=True)
                    continue
                source = str(item.get("src") or "")
                marker = "/assets/"
                relative = source.split(marker, 1)[-1] if marker in source else source
                image_path = (assets_root / relative).resolve()
                if assets_root.resolve() in image_path.parents and image_path.is_file():
                    page.insert_image(rect, filename=str(image_path), keep_proportion=item.get("fit") != "cover", overlay=True)
            elif kind == "text":
                background = item.get("background")
                if background and background != "transparent":
                    page.draw_rect(rect, color=None, fill=_color(background, (1, 1, 1)), overlay=True)
                align = {"left": 0, "center": 1, "right": 2, "justify": 3}.get(item.get("align"), 0)
                requested_size = max(6, min(240, float(item.get("fontSize", 28))))
                kwargs = {"color": _color(item.get("color")), "align": align, "overlay": True}
                family = item.get("fontFamily", "Arial")
                font_path = _font_path(family, bool(item.get("bold")), bool(item.get("italic")))
                if not font_path:
                    raise RuntimeError(f"Не найден шрифт с поддержкой кириллицы: {family}")
                variant = f"{family}-{bool(item.get('bold'))}-{bool(item.get('italic'))}".replace(" ", "-")
                page.insert_font(fontname=variant, fontfile=str(font_path))
                kwargs.update(fontname=variant)
                text = str(item.get("text") or "")
                if text:
                    shape_kwargs = {key: value for key, value in kwargs.items() if key not in {'overlay', 'fontname'}}
                    lineheight = body_line_height(requested_size, rect.height) if item.get('role') == 'body' else LINE_HEIGHT
                    shape, spare_height = prepare_textbox(page, rect, text, variant, requested_size, lineheight=lineheight, **shape_kwargs)
                    if spare_height < -.0001:
                        doc.close()
                        label = 'атрибуция' if item.get('role') == 'caption' else 'основной текст'
                        hint = ('Сократите атрибуцию или увеличьте её поле в настройках макета.'
                                if item.get('role') == 'caption' else
                                'Сократите текст перед скачиванием и публикацией.')
                        raise TextOverflowError(f"Страница {page_number}, {label}, поле "
                                                f"{item.get('cardIndex', item['id'])}: текст не помещается. {hint}")
                    _finish_textbox(shape, font_path, requested_size, align == 3, lineheight=lineheight)
            elif kind == "shape":
                stroke = _color(item.get("stroke"))
                fill_value = item.get("fill")
                fill = None if not fill_value or fill_value == "transparent" else _color(fill_value, (1, 1, 1))
                width = max(0.25, min(20, float(item.get("strokeWidth", 2))))
                dashes = {
                    "illustrator-dashed": "[6 6] 0",
                    "fine-dashed": "[3 3] 0",
                    "dashed": "[6 4] 0",
                    "long-dashed": "[10 5] 0",
                    "extra-long-dashed": "[16 6] 0",
                    "dotted": "[1 3] 0",
                    "dense-dotted": "[1 2] 0",
                    "dash-dot": "[8 3 1 3] 0",
                    "dash-dot-dot": "[8 3 1 3 1 3] 0",
                }.get(item.get("strokeStyle"))
                shape = item.get("shape")
                if shape == "ellipse":
                    page.draw_oval(rect, color=stroke, fill=fill, width=width, dashes=dashes, overlay=True)
                elif shape == "line":
                    middle = (rect.y0 + rect.y1) / 2
                    page.draw_line((rect.x0, middle), (rect.x1, middle), color=stroke, width=width, dashes=dashes, overlay=True)
                elif shape == "vertical-line":
                    middle = (rect.x0 + rect.x1) / 2
                    page.draw_line((middle, rect.y0), (middle, rect.y1), color=stroke, width=width, dashes=dashes, overlay=True)
                elif shape == "horizontal-frame":
                    page.draw_line((rect.x0, rect.y0), (rect.x1, rect.y0), color=stroke, width=width, dashes=dashes, overlay=True)
                    page.draw_line((rect.x0, rect.y1), (rect.x1, rect.y1), color=stroke, width=width, dashes=dashes, overlay=True)
                else:
                    page.draw_rect(rect, color=stroke, fill=fill, width=width, dashes=dashes, overlay=True)
    doc.set_metadata({"title": "Postcards Studio publication", "creator": "Postcards Studio"})
    doc.save(output, garbage=3, deflate=True)
    doc.close()


def publish_release(template: Path, assets_root: Path, releases_root: Path, release_id: str,
                    documents: list[dict], manifest_base: dict) -> dict:
    staging = releases_root / f".{release_id}.staging"
    final = releases_root / release_id
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=False)
    files = []
    try:
        for document in documents:
            filename = f"{document['slot']}.pdf"
            target = staging / filename
            render_document(template, document, assets_root, target)
            files.append({"slot": document["slot"], "name": filename,
                          "size": target.stat().st_size, "sha256": sha256(target),
                          "documentRevision": document["revision"]})
        attachments = []
        fourth = next((value for value in documents if value['slot'] == 'pdf4'), None)
        if fourth:
            editable = staging / 'editable-pdf4.json'
            editable.write_text(json.dumps({'pages': fourth['pages']}, ensure_ascii=False), 'utf-8')
            attachments.append({'name': editable.name, 'size': editable.stat().st_size, 'sha256': sha256(editable)})
        manifest = {**manifest_base, "files": files, "attachments": attachments}
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
        os.replace(staging, final)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

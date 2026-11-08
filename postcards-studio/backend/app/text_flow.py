"""Split a postcard text across its two existing fields at the fixed font size."""
import re

import pymupdf as fitz

from .pdf_renderer import _font_path, prepare_textbox
from .layout_geometry import DEFAULT_FONT_SIZE, body_line_height


def split_for_fields(text: str, fields: list[dict], width=1190.55, height=841.89) -> tuple[list[str], bool]:
    document = fitz.open()
    page = document.new_page(width=width, height=height)
    remaining = text
    parts = []
    try:
        for index, field in enumerate(fields):
            font = _font_path(field.get("fontFamily", "Times New Roman"), field.get("bold"), field.get("italic"))
            if not font:
                raise ValueError("Шрифт шаблона не установлен")
            name = f"flow-{index}"
            page.insert_font(fontname=name, fontfile=str(font))
            rect = fitz.Rect(0, 0, round(field["w"], 9) * width, round(field["h"], 9) * height)

            def fits(value):
                if not value.strip():
                    return True
                size = field.get('fontSize', DEFAULT_FONT_SIZE)
                _, spare = prepare_textbox(page, rect, value, name, size, lineheight=body_line_height(size, rect.height))
                return spare >= -.0001

            if fits(remaining):
                parts.append(remaining)
                remaining = ""
                continue
            if index == len(fields) - 1:
                # Never discard excess text. The editor warns and PDF export
                # refuses publication instead of silently shrinking/omitting it.
                parts.append(remaining)
                return parts, True
            low, high = 0, len(remaining)
            while low < high:
                middle = (low + high + 1) // 2
                if fits(remaining[:middle]):
                    low = middle
                else:
                    high = middle - 1
            boundary = low
            if boundary and boundary < len(remaining) and not remaining[boundary - 1].isspace() and not remaining[boundary].isspace():
                breaks = list(re.finditer(r"\s+", remaining[:boundary]))
                if breaks:
                    boundary = breaks[-1].end()
            parts.append(remaining[:boundary])
            remaining = remaining[boundary:]
        return parts, False
    finally:
        document.close()

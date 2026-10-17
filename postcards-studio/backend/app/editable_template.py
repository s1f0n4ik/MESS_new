from __future__ import annotations

import json
from pathlib import Path

import pymupdf as fitz


PAGE_COUNT = 28
DOCUMENT_TITLES = {
    "pdf1": "Экфрасисы",
    "pdf2": "Формальный анализ",
    "pdf3": "Контекст создания",
    "pdf4": "Контекст восприятия",
}

# Порядок разворотов подтверждён заказчиком 15.10.2026. ``None`` означает
# намеренно чёрную заглушку: оборот в архиве не сохранился.
SPREAD_SCANS = (
    ((1, "1"), (None, "1.1")),
    ((17, "1.21"), (9, "1.2")),
    ((2, "2"), (None, "2.1")),
    ((18, "2.21"), (10, "2.2")),
    ((3, "3"), (11, "3.1")),
    ((4, "4"), (None, "4.1")),
    ((None, "4.21"), (12, "4.2")),
    ((5, "5"), (13, "5.1")),
    ((6, "6"), (None, "6.1")),
    ((19, "6.21"), (14, "6.2")),
    ((7, "7"), (None, "7.1")),
    ((20, "7.21"), (15, "7.2")),
    ((8, "8"), (None, "8.1")),
    ((21, "8.21"), (16, "8.2")),
)


def _item(item_id: str, item_type: str, x: float, y: float, w: float, h: float, **extra) -> dict:
    return {"id": item_id, "type": item_type, "x": x, "y": y, "w": w, "h": h, **extra}


def blank_editable_layout(page_count: int = PAGE_COUNT) -> dict[str, list[dict]]:
    """Create the 14-spread layout used by the installation.

    Odd pages contain the scans, captions and the beginning of each text. Even
    pages are continuation pages. The geometry is locked, while text and image
    contents remain editable in the browser.
    """
    pages: dict[str, list[dict]] = {}
    for page in range(1, page_count + 1):
        items = [_item(f"background-{page}", "page-background", 0, 0, 1, 1,
                       color="#ffffff", locked=True)]
        for column in range(2):
            card_index = ((page - 1) // 2) * 2 + column + 1
            scan_number, scan_code = SPREAD_SCANS[(page - 1) // 2][column]
            x = 0.018 if column == 0 else 0.510
            items.append(_item(
                f"outline-{page}-{column}", "shape", x, 0.032, 0.472, 0.936,
                shape="rectangle", fill="transparent", stroke="#777777", strokeWidth=1,
                strokeStyle="dotted", locked=True, role="outline", cardIndex=card_index,
            ))
            if page % 2:
                items.extend([
                    _item(
                        f"scan-{page}-{column}", "image", x + 0.058, 0.034, 0.358, 0.337,
                        src="", fit="contain", locked=True, role="scan", sequence=scan_number,
                        scanCode=scan_code, missing=scan_number is None, cardIndex=card_index,
                    ),
                    _item(
                        f"scan-divider-{page}-{column}", "shape", x + 0.005, 0.382, 0.462, 0.006,
                        shape="line", fill="transparent", stroke="#777777", strokeWidth=1,
                        strokeStyle="solid", locked=True, role="scan-divider", cardIndex=card_index,
                    ),
                    _item(
                        f"caption-{page}-{column}", "text", x + 0.005, 0.393, 0.462, 0.078,
                        text="", placeholder="", fontSize=16,
                        fontFamily="Times New Roman", color="#111111", background="transparent",
                        align="right", bold=False, italic=False, locked=True, role="caption",
                        cardIndex=card_index,
                    ),
                    _item(
                        f"caption-divider-{page}-{column}", "shape", x + 0.005, 0.476, 0.462, 0.006,
                        shape="line", fill="transparent", stroke="#777777", strokeWidth=1,
                        strokeStyle="solid", locked=True, role="caption-divider", cardIndex=card_index,
                    ),
                    _item(
                        f"body-{page}-{column}", "text", x + 0.005, 0.489, 0.462, 0.473,
                        text="", placeholder="", fontSize=15, fontFamily="Times New Roman",
                        color="#111111", background="transparent", align="left", bold=False,
                        italic=False, locked=True, role="body", cardIndex=card_index,
                    ),
                ])
            else:
                items.append(_item(
                    f"body-{page}-{column}", "text", x + 0.005, 0.025, 0.462, 0.935,
                    text="", placeholder="", fontSize=15,
                    fontFamily="Times New Roman", color="#111111", background="transparent",
                    align="left", bold=False, italic=False, locked=True, role="body",
                    cardIndex=card_index,
                ))
        pages[str(page)] = items
    return pages


def _region_text(page: fitz.Page, x0: float, x1: float, y0: float, y1: float,
                 reflow: bool = False) -> str:
    rows: list[list] = []
    for trace in page.get_texttrace():
        for codepoint, _glyph, origin, bbox in trace["chars"]:
            x, y = origin
            if not (x0 <= x < x1 and y0 <= y < y1 and bbox[1] < page.rect.height and bbox[3] > 0):
                continue
            if codepoint < 0 or codepoint > 0x10FFFF:
                continue
            row = next((value for value in rows if abs(value[0] - y) < 1), None)
            if row is None:
                row = [y, []]
                rows.append(row)
            row[1].append((x, chr(codepoint)))
    lines: list[tuple[float, float, str]] = []
    for _y, chars in sorted(rows, key=lambda value: value[0]):
        chars = sorted(chars, key=lambda value: value[0])
        line = "".join(char for _x, char in chars).strip()
        if line:
            lines.append((_y, chars[0][0], line))
    if not reflow:
        return "\n".join(line for _y, _x, line in lines)
    paragraphs: list[str] = []
    for index, (line_y, line_x, line) in enumerate(lines):
        previous_y = lines[index - 1][0] if index else line_y
        begins_paragraph = index == 0 or line_x > x0 + 8 or line_y - previous_y > 24
        if begins_paragraph:
            paragraphs.append(line)
        elif paragraphs[-1].endswith("-"):
            paragraphs[-1] = paragraphs[-1][:-1] + line
        else:
            paragraphs[-1] += " " + line
    return "\n".join(paragraphs)


def import_legacy_pdf(source_pdf: Path, assets_root: Path, project_id: int = 1) -> dict[str, list[dict]]:
    """Convert the legacy 28-page PDF into editable page objects and scan PNGs."""
    source_pdf = Path(source_pdf)
    document = fitz.open(source_pdf)
    if len(document) != PAGE_COUNT:
        document.close()
        raise ValueError(f"Ожидалось {PAGE_COUNT} страниц, найдено {len(document)}")

    pages = blank_editable_layout()
    asset_folder = Path(assets_root) / str(project_id) / "starter-v1"
    asset_folder.mkdir(parents=True, exist_ok=True)
    width = document[0].rect.width

    for page_index, page in enumerate(document):
        page_number = page_index + 1
        for column in range(2):
            x0 = column * width / 2
            x1 = (column + 1) * width / 2
            card_index = (page_index // 2) * 2 + column + 1
            body = _region_text(page, x0, x1, 405 if page_number % 2 else 0,
                                page.rect.height, reflow=True)
            body_item = next(item for item in pages[str(page_number)]
                             if item.get("role") == "body" and item.get("cardIndex") == card_index)
            body_item["text"] = body

            if page_number % 2 == 0:
                continue
            caption = _region_text(page, x0, x1, 315, 405)
            caption_item = next(item for item in pages[str(page_number)]
                                if item.get("role") == "caption" and item.get("cardIndex") == card_index)
            caption_item["text"] = caption

            # Real scans are placed by their catalogue number. Missing reverse
            # sides remain generated black placeholders instead of bitmap files.
            image_item = next(item for item in pages[str(page_number)]
                              if item.get("role") == "scan" and item.get("cardIndex") == card_index)
            if image_item.get("missing"):
                continue
            clip = fitz.Rect(x0 + 90, 27, x0 + 518, 313)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), clip=clip, alpha=False)
            name = f"scan-{int(image_item['sequence']):02d}.png"
            pixmap.save(asset_folder / name)
            image_item["src"] = f"/assets/{project_id}/starter-v1/{name}"
            image_item["sourceLabel"] = caption.replace("\n", " ")
    document.close()
    return pages


def without_body_text(pages: dict[str, list[dict]]) -> dict[str, list[dict]]:
    clone = json.loads(json.dumps(pages, ensure_ascii=False))
    for items in clone.values():
        for item in items:
            if item.get("role") == "body":
                item["text"] = ""
    return clone

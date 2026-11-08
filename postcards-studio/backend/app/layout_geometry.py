from copy import deepcopy

# Illustrator's 16 pt Times New Roman composes like 15.75 pt with the bundled
# Windows font. At the editor's normal page scale this is the approved 15.3 px
# on screen, while preserving the reference line breaks.
DEFAULT_FONT_SIZE = 15.75
LINE_HEIGHT = 1.2
PAGE_HEIGHT = 841.89
CAPTION_DIVIDER_Y = .40104 + ((3 * LINE_HEIGHT - .22) * DEFAULT_FONT_SIZE + 1) / PAGE_HEIGHT


def body_line_height(font_size, height_points):
    """Fit an integral row grid to the fixed frame instead of leaving a partial row."""
    rows = int((height_points + .000001) / (font_size * LINE_HEIGHT))
    return height_points / (rows * font_size) if rows >= 2 else LINE_HEIGHT


def align_template_text(pages: dict) -> dict:
    """Fit standard text fields inside their contours; preserve all content."""
    result = deepcopy(pages)
    for items in result.values():
        for item in items:
            if item.get("type") != "text" or item.get("role") not in {"caption", "body"}:
                continue
            siblings = [value for value in items if value.get("cardIndex") == item.get("cardIndex")]
            outline = next((value for value in siblings if value.get("role") == "outline"), None)
            if not outline:
                continue
            upper = next((value for value in siblings if value.get("role") == "scan-divider"), None)
            lower = next((value for value in siblings if value.get("role") == "caption-divider"), None)
            # Align visible glyphs, rather than the top of the font's line box,
            # to the guide. The same inset is used for captions and prose.
            ink_offset = -.22 * float(item.get('fontSize', DEFAULT_FONT_SIZE)) / PAGE_HEIGHT
            if item["role"] == "caption":
                top = upper["y"] + upper["h"] / 2 + ink_offset if upper else item["y"]
                bottom = lower["y"] + lower["h"] / 2 - 1 / PAGE_HEIGHT if lower else item["y"] + item["h"]
            else:
                top = lower["y"] + lower["h"] / 2 + ink_offset if lower else outline["y"] + ink_offset
                # Stay mathematically inside the contour without creating a
                # visible gap at the lower guide.
                bottom = outline["y"] + outline["h"] - 1e-7
            item.update(x=outline["x"] + .0005, y=top, w=round(max(.001, outline["w"] - .001), 9),
                        h=round(max(.001, bottom - top), 9))
    return result

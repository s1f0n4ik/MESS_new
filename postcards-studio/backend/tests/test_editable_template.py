import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import pymupdf as fitz
from PIL import Image

from app.editable_template import (
    PAGE_COUNT, PARAGRAPH_INDENT, SPREAD_SCANS, _best_original, blank_editable_layout,
    import_legacy_pdf, indent_paragraphs, without_body_text,
)


class ImagePart:
    def __init__(self, image: Image.Image):
        stream = BytesIO()
        image.save(stream, format="PNG")
        self.blob = stream.getvalue()


class EditableTemplateTests(unittest.TestCase):
    def test_paragraphs_receive_red_line_once(self):
        value = indent_paragraphs("Первый абзац\nВторой абзац\n\n" + PARAGRAPH_INDENT + "Третий")
        self.assertEqual(value, PARAGRAPH_INDENT + "Первый абзац\n" + PARAGRAPH_INDENT +
                         "Второй абзац\n\n" + PARAGRAPH_INDENT + "Третий")
        self.assertEqual(indent_paragraphs(value), value)

    def test_word_thumbnail_resolves_to_larger_original(self):
        original_image = Image.new("RGB", (640, 420), (180, 40, 20))
        thumbnail_image = original_image.resize((64, 42))
        unrelated_image = Image.new("RGB", (640, 420), (20, 80, 180))
        original = ImagePart(original_image)
        thumbnail = ImagePart(thumbnail_image)
        unrelated = ImagePart(unrelated_image)
        self.assertIs(_best_original(thumbnail, [unrelated, original]), original)

    def test_layout_uses_fourteen_two_page_spreads(self):
        pages = blank_editable_layout()
        self.assertEqual(len(pages), PAGE_COUNT)
        self.assertEqual(len([item for item in pages["1"] if item.get("role") == "scan"]), 2)
        self.assertEqual(len([item for item in pages["2"] if item.get("role") == "scan"]), 0)
        self.assertEqual({item["cardIndex"] for item in pages["1"] if item.get("role") == "body"}, {1, 2})
        self.assertEqual({item["cardIndex"] for item in pages["2"] if item.get("role") == "body"}, {1, 2})
        self.assertEqual({item["cardIndex"] for item in pages["27"] if item.get("role") == "body"}, {27, 28})
        first_scans = [item for item in pages["1"] if item.get("role") == "scan"]
        self.assertEqual([(item.get("sequence"), item.get("scanCode"), item.get("missing"))
                          for item in first_scans], [(1, "1", False), (None, "1.1", True)])
        real_numbers = sorted(item["sequence"] for values in pages.values() for item in values
                              if item.get("role") == "scan" and item.get("sequence"))
        self.assertEqual(real_numbers, list(range(1, 22)))
        self.assertEqual(len(SPREAD_SCANS), 14)
        self.assertTrue(all(len([item for item in values if item.get("role") == "divider"]) == 1
                            for values in pages.values()))
        outlines = [item for item in pages["1"] if item.get("role") == "outline"]
        divider = next(item for item in pages["1"] if item.get("role") == "divider")
        self.assertEqual(divider["shape"], "vertical-line")
        self.assertEqual(divider["strokeStyle"], "solid")
        self.assertAlmostEqual(divider["x"] + divider["w"] / 2, 0.5)
        self.assertLess(outlines[0]["x"] + outlines[0]["w"], 0.5)
        self.assertGreater(outlines[1]["x"], 0.5)
        self.assertAlmostEqual(0.5 - (outlines[0]["x"] + outlines[0]["w"]), outlines[1]["x"] - 0.5)
        self.assertTrue(all(item["strokeStyle"] == "dashed" for item in outlines))
        dividers = [item for item in pages["1"] if item.get("role") in {"scan-divider", "caption-divider"}]
        self.assertTrue(all(item["strokeStyle"] == "dashed" for item in dividers))
        self.assertTrue(all(item.get("placeholder", "") == "" for values in pages.values()
                            for item in values if item.get("type") == "text"))

    def test_import_makes_scans_and_editable_unicode_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.pdf"
            pdf = fitz.open()
            for page_number in range(PAGE_COUNT):
                page = pdf.new_page(width=1190.55, height=841.89)
                if page_number % 2 == 0:
                    page.draw_rect((90, 27, 518, 313), fill=(0.8, 0.4, 0.2))
                    page.insert_text((30, 360), "Editable caption", fontsize=16)
                page.insert_text((30, 430 if page_number % 2 == 0 else 40), "Editable body", fontsize=16)
            pdf.save(source)
            pdf.close()

            pages = import_legacy_pdf(source, root / "assets")
            first = pages["1"]
            self.assertEqual(next(item for item in first if item.get("role") == "caption")["text"],
                             "Editable caption")
            self.assertEqual(next(item for item in first if item.get("role") == "body")["text"],
                             PARAGRAPH_INDENT + "Editable body")
            self.assertTrue((root / "assets" / "1" / "starter-v1" / "scan-01.png").is_file())
            blank = without_body_text(pages)
            self.assertEqual(next(item for item in blank["1"] if item.get("role") == "body")["text"], "")
            self.assertEqual(next(item for item in blank["1"] if item.get("role") == "caption")["text"],
                             "Editable caption")


if __name__ == "__main__":
    unittest.main()

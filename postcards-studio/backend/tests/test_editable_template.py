import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from app.editable_template import PAGE_COUNT, SPREAD_SCANS, blank_editable_layout, import_legacy_pdf, without_body_text


class EditableTemplateTests(unittest.TestCase):
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
        self.assertFalse(any(item.get("role") == "divider" for values in pages.values() for item in values))

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
                             "Editable body")
            self.assertTrue((root / "assets" / "1" / "starter-v1" / "scan-01.png").is_file())
            blank = without_body_text(pages)
            self.assertEqual(next(item for item in blank["1"] if item.get("role") == "body")["text"], "")
            self.assertEqual(next(item for item in blank["1"] if item.get("role") == "caption")["text"],
                             "Editable caption")


if __name__ == "__main__":
    unittest.main()

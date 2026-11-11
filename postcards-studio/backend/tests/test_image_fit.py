import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw

from app.pdf_renderer import render_document


class ImageFitTests(unittest.TestCase):
    def test_cover_crops_from_the_center_without_stretching(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = Image.new("RGB", (300, 100), "green")
            drawing = ImageDraw.Draw(image)
            drawing.rectangle((0, 0, 99, 99), fill="red")
            drawing.rectangle((200, 0, 299, 99), fill="blue")
            image.save(root / "wide.png")

            template = fitz.open()
            template.new_page(width=200, height=200)
            template.save(root / "blank.pdf")
            template.close()
            content = {"pages": {"1": [{
                "id": "image", "type": "image", "src": "/assets/wide.png", "fit": "cover",
                "x": .25, "y": .25, "w": .5, "h": .5,
            }]}}
            render_document(root / "blank.pdf", content, root, root / "output.pdf")

            with fitz.open(root / "output.pdf") as document:
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                # The centered square crop contains only the green middle third.
                for x, y in ((102, 200), (200, 200), (298, 200)):
                    red, green, blue = pixmap.pixel(x, y)
                    self.assertGreater(green, 90)
                    self.assertLess(red, 30)
                    self.assertLess(blue, 30)

    def test_cover_crops_a_tall_image_from_the_center(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = Image.new("RGB", (100, 300), "green")
            drawing = ImageDraw.Draw(image)
            drawing.rectangle((0, 0, 99, 99), fill="red")
            drawing.rectangle((0, 200, 99, 299), fill="blue")
            image.save(root / "tall.png")

            template = fitz.open()
            template.new_page(width=200, height=200)
            template.save(root / "blank.pdf")
            template.close()
            content = {"pages": {"1": [{
                "id": "image", "type": "image", "src": "/assets/tall.png", "fit": "cover",
                "x": .25, "y": .25, "w": .5, "h": .5,
            }]}}
            render_document(root / "blank.pdf", content, root, root / "output.pdf")

            with fitz.open(root / "output.pdf") as document:
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                for x, y in ((200, 102), (200, 200), (200, 298)):
                    red, green, blue = pixmap.pixel(x, y)
                    self.assertGreater(green, 90)
                    self.assertLess(red, 30)
                    self.assertLess(blue, 30)


if __name__ == "__main__":
    unittest.main()

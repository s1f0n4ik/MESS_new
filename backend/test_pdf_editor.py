import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from pdf_editor import PdfEditorStore, SaveBody


class PdfEditorStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PdfEditorStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_history_and_conflict_protection(self):
        saved = self.store.save("pdf4", SaveBody(baseRevision=0, updatedBy="pc4", pages={
            "1": [{"id": "t1", "type": "text", "x": .1, "y": .2, "w": .4, "h": .1,
                   "text": "Новый текст", "fontSize": 31}],
        }))
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(self.store.load("pdf4")["pages"]["1"][0]["text"], "Новый текст")
        self.assertEqual(self.store.history("pdf4")[0]["revision"], 1)
        self.assertEqual(self.store.load_history("pdf4", 1)["updatedBy"], "pc4")

        with self.assertRaises(HTTPException) as conflict:
            self.store.save("pdf4", SaveBody(baseRevision=0, updatedBy="pc1", pages={}))
        self.assertEqual(conflict.exception.status_code, 409)

    def test_images_are_scoped_to_document(self):
        image = self.store.save_asset("pdf2", b"fake png bytes", "photo.png")
        saved = self.store.save("pdf2", SaveBody(baseRevision=0, pages={
            "1": [{"id": "i1", "type": "image", "src": image["url"],
                   "x": 0, "y": 0, "w": 1, "h": 1}],
        }))
        self.assertEqual(saved["pages"]["1"][0]["src"], image["url"])

        rejected = self.store.save("pdf1", SaveBody(baseRevision=0, pages={
            "1": [{"id": "i1", "type": "image", "src": image["url"],
                   "x": 0, "y": 0, "w": 1, "h": 1}],
        }))
        self.assertEqual(rejected["pages"], {})

    def test_configurable_archive_receives_dated_revisions(self):
        archive = Path(self.tmp.name) / "nas-share"
        config = self.store.set_archive(str(archive))
        self.assertEqual(config["source"], "config")
        self.store.save("pdf1", SaveBody(baseRevision=0, updatedBy="pc1", pages={
            "1": [{"id": "c1", "type": "cover", "x": .1, "y": .1,
                   "w": .2, "h": .2, "color": "#ffffff"}],
        }))
        mirrored = list((archive / "pdf1" / "history").glob("*.json"))
        self.assertEqual(len(mirrored), 1)


if __name__ == "__main__":
    unittest.main()

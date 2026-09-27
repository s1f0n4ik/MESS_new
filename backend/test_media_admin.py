import tempfile
import unittest
from pathlib import Path

from media_admin import MediaAdmin, PDF_SLOTS


class MediaTemplateTests(unittest.TestCase):
    def test_template_installs_all_four_pdfs_and_backs_up_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.pdf"
            template.write_bytes(b"canonical-template")
            pdf_dir = root / "pdfs"
            pdf_dir.mkdir()
            (pdf_dir / "pdf1.pdf").write_bytes(b"old-pdf1")

            admin = MediaAdmin(root, pdf_dir=pdf_dir, template_path=template)
            admin.install_template()

            for slot in PDF_SLOTS:
                self.assertEqual((pdf_dir / f"{slot}.pdf").read_bytes(), b"canonical-template")
            backups = list((root / "pdf-template-backups").glob("*/pdf1.pdf"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"old-pdf1")
            self.assertTrue(admin.snapshot()["template"]["available"])


if __name__ == "__main__":
    unittest.main()

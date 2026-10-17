import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from media_admin import MediaAdmin, PDF_SLOTS


class MediaTemplateTests(unittest.TestCase):
    def test_document_titles_have_defaults_and_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            admin = MediaAdmin(root)
            self.assertEqual(admin.snapshot()["pdfTitles"]["pdf1"], "Документ 1")
            admin.set_pdf_title("pdf1", "Экфрасисы")
            self.assertEqual(MediaAdmin(root).snapshot()["pdfTitles"]["pdf1"], "Экфрасисы")

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

    def test_verified_studio_release_installs_all_four_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "release"
            release.mkdir()
            files = []
            for slot in PDF_SLOTS:
                payload = f"published-{slot}".encode()
                name = f"{slot}.pdf"
                (release / name).write_bytes(payload)
                files.append({"slot": slot, "name": name, "size": len(payload),
                              "sha256": hashlib.sha256(payload).hexdigest()})
            (release / "manifest.json").write_text(json.dumps({"releaseId": "r-test", "files": files}), "utf-8")
            admin = MediaAdmin(root, pdf_dir=root / "pdfs")
            result = admin.install_release(str(release))
            self.assertEqual(result["releaseId"], "r-test")
            for slot in PDF_SLOTS:
                self.assertEqual((root / "pdfs" / f"{slot}.pdf").read_bytes(), f"published-{slot}".encode())

    def test_sync_latest_release_follows_current_manifest_and_remembers_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            releases = root / "releases"
            release = releases / "2026-10-17-test"
            release.mkdir(parents=True)
            files = []
            for slot in PDF_SLOTS:
                payload = f"synced-{slot}".encode()
                name = f"{slot}.pdf"
                (release / name).write_bytes(payload)
                files.append({"slot": slot, "name": name,
                              "sha256": hashlib.sha256(payload).hexdigest()})
            manifest = {"releaseId": release.name, "files": files}
            (release / "manifest.json").write_text(json.dumps(manifest), "utf-8")
            (releases / "current.json").write_text(json.dumps(manifest), "utf-8")

            admin = MediaAdmin(root, releases_dir=releases)
            result = admin.sync_latest_release()
            self.assertEqual(result["status"], "installed")
            self.assertEqual(admin.snapshot()["sync"]["installedReleaseId"], release.name)
            self.assertEqual(admin.sync_latest_release()["status"], "already-current")
            for slot in PDF_SLOTS:
                self.assertEqual((root / "pdfs" / f"{slot}.pdf").read_bytes(), f"synced-{slot}".encode())

    def test_sync_rejects_release_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            releases = root / "releases"
            releases.mkdir()
            (releases / "current.json").write_text(json.dumps({"releaseId": "../outside"}), "utf-8")
            admin = MediaAdmin(root, releases_dir=releases)
            with self.assertRaisesRegex(Exception, "некорректный releaseId"):
                admin.sync_latest_release()


if __name__ == "__main__":
    unittest.main()

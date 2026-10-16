import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from app.yandex_disk import YandexDiskDelivery, YandexDiskDeliveryError


class YandexDiskDeliveryTests(unittest.TestCase):
    def test_current_manifest_is_uploaded_after_complete_release(self):
        requests: list[tuple[str, str, bytes]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = request.read()
            requests.append((request.method, request.url.path, body))
            return httpx.Response(201)

        with tempfile.TemporaryDirectory() as raw_directory:
            release_dir = Path(raw_directory)
            files = []
            for number in range(1, 5):
                name = f"pdf{number}.pdf"
                data = f"pdf-{number}".encode()
                (release_dir / name).write_bytes(data)
                files.append({"slot": f"pdf{number}", "name": name, "size": len(data),
                              "sha256": hashlib.sha256(data).hexdigest()})
            manifest = {"releaseId": "20261016-r0001-test", "files": files}
            client = httpx.Client(transport=httpx.MockTransport(handler))
            delivery = YandexDiskDelivery(
                "https://webdav.yandex.ru", "user", "app-password",
                "/Выставка/Postcards Studio/Релизы", client=client,
            )
            delivery.upload_release(release_dir, manifest)
            put_paths = [path for method, path, _ in requests if method == "PUT"]
            self.assertEqual(put_paths[-1], "/Выставка/Postcards Studio/Релизы/current.json")
            self.assertEqual(len(put_paths), 6)
            self.assertEqual(json.loads(requests[-1][2]), manifest)

    def test_webdav_error_does_not_upload_current_manifest(self):
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            if request.method == "PUT":
                return httpx.Response(507)
            return httpx.Response(201)

        with tempfile.TemporaryDirectory() as raw_directory:
            release_dir = Path(raw_directory)
            (release_dir / "pdf1.pdf").write_bytes(b"pdf")
            manifest = {"releaseId": "failed", "files": [{"name": "pdf1.pdf"}]}
            delivery = YandexDiskDelivery(
                "https://webdav.yandex.ru", "user", "app-password", "/Releases",
                client=httpx.Client(transport=httpx.MockTransport(handler)),
            )
            with self.assertRaises(YandexDiskDeliveryError):
                delivery.upload_release(release_dir, manifest)
            self.assertNotIn("/Releases/current.json", paths)


if __name__ == "__main__":
    unittest.main()

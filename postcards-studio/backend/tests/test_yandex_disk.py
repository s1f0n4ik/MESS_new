import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from app.yandex_disk import (YandexDiskApiDelivery, YandexDiskDelivery,
                             YandexDiskDeliveryError)


class YandexDiskDeliveryTests(unittest.TestCase):
    def test_rest_api_uploads_current_manifest_last(self):
        requested_paths: list[str] = []
        upload_targets: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_paths.append(request.url.path)
            if request.method == "GET" and request.url.path.endswith("/resources/upload"):
                target = request.url.params["path"]
                upload_targets.append(target)
                return httpx.Response(200, json={"href": f"https://upload.test/{len(upload_targets)}"})
            if request.url.host == "upload.test":
                return httpx.Response(201)
            return httpx.Response(201)

        with tempfile.TemporaryDirectory() as raw_directory:
            release_dir = Path(raw_directory)
            files = []
            for number in range(1, 5):
                name = f"pdf{number}.pdf"
                (release_dir / name).write_bytes(name.encode())
                files.append({"slot": f"pdf{number}", "name": name})
            manifest = {"releaseId": "release-api", "files": files}
            delivery = YandexDiskApiDelivery(
                "https://cloud-api.yandex.net/v1/disk", "oauth-token", "/Releases",
                client=httpx.Client(transport=httpx.MockTransport(handler)),
            )
            delivery.upload_release(release_dir, manifest)
            self.assertEqual(upload_targets[-1], "/Releases/current.json")
            self.assertEqual(len(upload_targets), 6)

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

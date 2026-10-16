from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import httpx


class YandexDiskDeliveryError(RuntimeError):
    pass


class YandexDiskDelivery:
    """Publish immutable PDF releases to a Yandex Disk WebDAV folder.

    ``current.json`` is deliberately uploaded last.  A consumer therefore
    never sees a partially uploaded release as the current one.
    """

    def __init__(self, base_url: str, username: str, app_password: str,
                 root_path: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.root_parts = [part for part in root_path.replace("\\", "/").split("/") if part]
        self.client = client or httpx.Client(
            auth=(username, app_password), timeout=120, follow_redirects=True
        )

    def close(self) -> None:
        self.client.close()

    def _url(self, *parts: str) -> str:
        encoded = "/".join(quote(part, safe="") for part in (*self.root_parts, *parts))
        return f"{self.base_url}/{encoded}"

    def _ensure_collection(self, parts: list[str]) -> None:
        current: list[str] = []
        for part in parts:
            current.append(part)
            url = f"{self.base_url}/" + "/".join(quote(item, safe="") for item in current)
            response = self.client.request("MKCOL", url)
            if response.status_code not in {201, 405}:
                raise YandexDiskDeliveryError(
                    f"Яндекс Диск не создал каталог ({response.status_code})"
                )

    def _put(self, url: str, data: bytes, content_type: str) -> None:
        response = self.client.put(url, content=data, headers={"Content-Type": content_type})
        if response.status_code not in {200, 201, 204}:
            raise YandexDiskDeliveryError(
                f"Яндекс Диск отклонил загрузку ({response.status_code})"
            )

    def upload_release(self, release_dir: Path, manifest: dict) -> None:
        release_id = str(manifest["releaseId"])
        self._ensure_collection(self.root_parts + [release_id])
        for item in manifest["files"]:
            source = release_dir / item["name"]
            if not source.is_file():
                raise YandexDiskDeliveryError(f"Файл релиза не найден: {item['name']}")
            self._put(self._url(release_id, item["name"]), source.read_bytes(), "application/pdf")
        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        self._put(self._url(release_id, "manifest.json"), payload, "application/json; charset=utf-8")
        self._put(self._url("current.json"), payload, "application/json; charset=utf-8")


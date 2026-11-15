"""Direct NAS WebDAV delivery, with read-back verification and atomic pointers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx

from .yandex_disk import YandexDiskDeliveryError as DeliveryError


def safe_parts(value: str) -> list[str]:
    parts = value.split('/')
    if any(p in {'.', '..'} or '\\' in p or '\x00' in p for p in parts):
        raise DeliveryError('Некорректный путь NAS')
    return [p for p in parts if p]


class NasWebDAVDelivery:
    def __init__(self, base_url: str, username: str, password: str, root_path: str = '',
                 client: httpx.Client | None = None):
        parsed = urlsplit(base_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise DeliveryError('Для NAS требуется HTTPS URL без пароля и параметров')
        if not username or not password:
            raise DeliveryError('Задайте логин и пароль NAS')
        self.base_url = base_url.rstrip('/')
        self.parts = safe_parts(root_path)
        self.client = client or httpx.Client(auth=(username, password), timeout=120,
                                             follow_redirects=False, transport=httpx.HTTPTransport(retries=2))

    def close(self):
        self.client.close()

    def _url(self, *parts):
        return self.base_url + '/' + '/'.join(quote(p, safe='') for p in (*self.parts, *parts))

    def _request(self, method, url, **kwargs):
        try:
            response = self.client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            # Do not put exception URLs, credentials or response bodies in API errors.
            raise DeliveryError(f'NAS: ошибка связи ({type(exc).__name__})') from None
        return response

    def _ensure_collection(self, parts):
        # base_url is an existing mount; never create or inspect its parents.
        all_parts = self.parts + list(parts)
        for count in range(1, len(all_parts) + 1):
            url = self.base_url + '/' + '/'.join(quote(p, safe='') for p in all_parts[:count])
            response = self._request('MKCOL', url)
            if response.status_code == 405:
                check = self._request('PROPFIND', url + '/', headers={'Depth': '0'})
                if check.status_code != 207 or b'collection' not in check.content:
                    raise DeliveryError('NAS: путь существует, но не является каталогом')
            elif response.status_code != 201:
                raise DeliveryError(f'NAS: каталог не создан (HTTP {response.status_code})')

    def _put(self, url, data, content_type):
        response = self._request('PUT', url, content=data, headers={'Content-Type': content_type})
        if response.status_code not in {200, 201, 204}:
            raise DeliveryError(f'NAS: запись отклонена (HTTP {response.status_code})')

    def _upload_file(self, folder: Path, parts, item):
        name = str(item['name'])
        if safe_parts(name) != [name]:
            raise DeliveryError('NAS: некорректное имя файла')
        source = folder / name
        if not source.is_file() or source.is_symlink():
            raise DeliveryError('NAS: исходный файл отсутствует')
        expected_size, expected_hash = int(item['size']), item['sha256']
        digest = hashlib.sha256()
        with source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if source.stat().st_size != expected_size or digest.hexdigest() != expected_hash:
            raise DeliveryError('NAS: исходный файл не соответствует manifest')
        url = self._url(*parts, name)
        with source.open('rb') as stream:
            chunks = iter(lambda: stream.read(1024 * 1024), b'')
            response = self._request('PUT', url, content=chunks,
                                     headers={'Content-Length': str(expected_size), 'Content-Type': 'application/octet-stream'})
        if response.status_code not in {200, 201, 204}:
            raise DeliveryError(f'NAS: файл не записан (HTTP {response.status_code})')
        digest, size = hashlib.sha256(), 0
        try:
            with self.client.stream('GET', url) as response:
                if response.status_code != 200:
                    raise DeliveryError(f'NAS: проверка чтением не выполнена (HTTP {response.status_code})')
                for chunk in response.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
        except httpx.HTTPError as exc:
            raise DeliveryError(f'NAS: ошибка проверки ({type(exc).__name__})') from None
        if size != expected_size or digest.hexdigest() != expected_hash:
            raise DeliveryError('NAS: размер или SHA-256 загруженного файла не совпадает')

    def _atomic_pointer(self, parts, payload):
        temporary = [*parts[:-1], '.' + parts[-1] + '.' + uuid4().hex + '.tmp']
        self._put(self._url(*temporary), payload, 'application/json; charset=utf-8')
        response = self._request('MOVE', self._url(*temporary),
                                 headers={'Destination': self._url(*parts), 'Overwrite': 'T'})
        if response.status_code not in {201, 204}:
            raise DeliveryError(f'NAS: указатель не переключён (MOVE HTTP {response.status_code})')
        check = self._request('GET', self._url(*parts))
        if check.status_code != 200 or check.content != payload:
            raise DeliveryError('NAS: указатель не прошёл проверку чтением')

    def _upload(self, folder, parts, manifest, pointer):
        self._ensure_collection(parts)
        for item in [*manifest['files'], *manifest.get('attachments', [])]:
            self._upload_file(folder, parts, item)
        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
        self._put(self._url(*parts, 'manifest.json'), payload, 'application/json; charset=utf-8')
        self._atomic_pointer(pointer, payload)

    def upload_release(self, release_dir: Path, manifest: dict):
        release_id = str(manifest['releaseId'])
        if safe_parts(release_id) != [release_id]:
            raise DeliveryError('NAS: некорректный ID релиза')
        self._upload(release_dir, [release_id], manifest, ['current.json'])

    def upload_mediation(self, folder: Path, manifest: dict):
        project, version = str(manifest['projectId']), str(manifest['version'])
        if safe_parts(project) != [project] or safe_parts(version) != [version]:
            raise DeliveryError('NAS: некорректный архив медиации')
        parts = ['Медиации', project, version]
        self._upload(folder, parts, manifest, [*parts[:-1], 'latest.json'])

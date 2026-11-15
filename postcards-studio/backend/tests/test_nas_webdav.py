import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from app.webdav import NasWebDAVDelivery, DeliveryError
from app.config import Settings
from app.delivery import create_delivery


class NasDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        data = b'%PDF-test'
        (self.folder / 'pdf1.pdf').write_bytes(data)
        self.manifest = {'releaseId': 'test-release', 'files': [
            {'name': 'pdf1.pdf', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]}
        self.remote = {'/studio/test/current.json': b'old'}
        self.calls = []
        self.corrupt = False
        self.fail_move = False

    def tearDown(self):
        self.temp.cleanup()

    def handle(self, request):
        path = request.url.path
        self.calls.append((request.method, path))
        if request.method == 'MKCOL':
            return httpx.Response(201)
        if request.method == 'PUT':
            self.remote[path] = request.read()
            return httpx.Response(201)
        if request.method == 'GET':
            data = self.remote.get(path, b'')
            if self.corrupt and path.endswith('.pdf'):
                data = b'corrupted'
            return httpx.Response(200, content=data)
        if request.method == 'MOVE':
            if self.fail_move:
                return httpx.Response(403)
            target = httpx.URL(request.headers['Destination']).path
            self.remote[target] = self.remote.pop(path)
            return httpx.Response(204)
        return httpx.Response(500)

    def delivery(self):
        return NasWebDAVDelivery('https://nas.test/studio', 'user', 'secret', 'test',
                                 client=httpx.Client(transport=httpx.MockTransport(self.handle)))

    def test_verified_files_then_atomic_pointer_and_existing_pointer_replace(self):
        delivery = self.delivery()
        try:
            delivery.upload_release(self.folder, self.manifest)
        finally:
            delivery.close()
        self.assertEqual(json.loads(self.remote['/studio/test/current.json']), self.manifest)
        move = next(i for i, call in enumerate(self.calls) if call[0] == 'MOVE')
        verification = self.calls.index(('GET', '/studio/test/test-release/pdf1.pdf'))
        self.assertLess(verification, move)
        self.assertFalse(any(path == '/studio' for _, path in self.calls))

    def test_corrupted_readback_preserves_current(self):
        self.corrupt = True
        with self.assertRaises(DeliveryError):
            self.delivery().upload_release(self.folder, self.manifest)
        self.assertEqual(self.remote['/studio/test/current.json'], b'old')
        self.assertFalse(any(method == 'MOVE' for method, _ in self.calls))

    def test_move_denied_preserves_current(self):
        self.fail_move = True
        with self.assertRaises(DeliveryError):
            self.delivery().upload_release(self.folder, self.manifest)
        self.assertEqual(self.remote['/studio/test/current.json'], b'old')

    def test_mediation_uses_separate_latest_pointer(self):
        manifest = {**self.manifest, 'projectId': 8, 'version': 'r0000000001'}
        self.delivery().upload_mediation(self.folder, manifest)
        self.assertIn('/studio/test/Медиации/8/latest.json', self.remote)
        self.assertEqual(self.remote['/studio/test/current.json'], b'old')

    def test_transport_failure_is_sanitized(self):
        def offline(request):
            raise httpx.ConnectError('https://private-host/secret', request=request)
        delivery = NasWebDAVDelivery('https://nas.test/studio', 'user', 'secret',
            client=httpx.Client(transport=httpx.MockTransport(offline)))
        with self.assertRaises(DeliveryError) as result:
            delivery.upload_release(self.folder, self.manifest)
        self.assertNotIn('private-host', str(result.exception))

    def test_nas_precedes_yandex(self):
        cfg = Settings(_env_file=None, nas_webdav_url='https://nas.test/studio', nas_username='u',
                       nas_password='p', yandex_disk_oauth_token='legacy', yandex_disk_path='/legacy')
        delivery = create_delivery(cfg)
        self.assertIsInstance(delivery, NasWebDAVDelivery)
        delivery.close()

    def test_missing_credentials_and_traversal_rejected(self):
        with self.assertRaises(ValueError):
            Settings(_env_file=None, nas_webdav_url='https://nas.test').nas_delivery_enabled
        self.manifest['files'][0]['name'] = '../private'
        with self.assertRaises(DeliveryError):
            self.delivery().upload_release(self.folder, self.manifest)

    def test_invalid_nas_configuration_fails_before_application_start(self):
        for url in ('http://nas.test/studio', 'https://user:secret@nas.test/studio', 'https://nas.test/studio?token=secret'):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                Settings(_env_file=None, nas_webdav_url=url, nas_username='u', nas_password='p').validate_runtime()

    def test_editable_attachment_is_verified_before_pointer_activation(self):
        data = b'{"pages": {}}'
        (self.folder / 'editable-pdf4.json').write_bytes(data)
        self.manifest['attachments'] = [{'name': 'editable-pdf4.json', 'size': len(data),
                                         'sha256': hashlib.sha256(data).hexdigest()}]
        self.delivery().upload_release(self.folder, self.manifest)
        verification = self.calls.index(('GET', '/studio/test/test-release/editable-pdf4.json'))
        activation = next(i for i, call in enumerate(self.calls) if call[0] == 'MOVE')
        self.assertLess(verification, activation)


if __name__ == '__main__':
    unittest.main()

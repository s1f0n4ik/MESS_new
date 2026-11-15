"""Exercise real NAS publication/archive through an isolated temporary API.

Requires the configured NAS credentials and explicit --run. Uses a temporary
SQLite database, tiny test PDFs and a unique NAS directory, then cleans up.
Never publishes the real database or switches its exhibition current.json.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        parser.exit(message='Dry run: supply --run to write and remove an isolated NAS test directory.\n')
    from app.config import Settings
    from app.webdav import NasWebDAVDelivery
    cfg = Settings()
    if not cfg.nas_delivery_enabled:
        raise RuntimeError('Direct NAS is not configured')
    remote = NasWebDAVDelivery(cfg.nas_webdav_url, cfg.nas_username, cfg.nas_password, cfg.nas_path)
    parent, leaf = '_deployment_checks', 'studio-' + secrets.token_hex(8)
    before = remote._request('GET', remote._url('current.json'))
    if before.status_code != 200: raise RuntimeError('Cannot read existing release pointer before test')
    pointer_hash = hashlib.sha256(before.content).hexdigest()
    parent_check = remote._request('PROPFIND', remote._url(parent), headers={'Depth': '0'})
    parent_existed = parent_check.status_code == 207
    if parent_check.status_code not in (207, 404):
        raise RuntimeError('Cannot inspect isolated test parent')
    result = {'temporaryApi': True, 'directory': parent + '/' + leaf}
    try:
        with tempfile.TemporaryDirectory(prefix='studio-nas-check-') as directory:
            root = Path(directory)
            import pymupdf as fitz
            pdf = fitz.open(); pdf.new_page(width=1190.55, height=841.89)
            pdf.save(root/'blank.pdf'); pdf.close()
            password = secrets.token_urlsafe(24)
            os.environ.update({
                'STUDIO_ENVIRONMENT': 'development',
                'STUDIO_DATABASE_URL': 'sqlite:///' + (root/'check.db').as_posix(),
                'STUDIO_STORAGE_DIR': str(root/'data'), 'STUDIO_TEMPLATE_PDF': str(root/'blank.pdf'),
                'STUDIO_ADMIN_EMAIL': 'deployment-check@localhost.test', 'STUDIO_ADMIN_PASSWORD': password,
                'STUDIO_SECRET_KEY': secrets.token_urlsafe(48), 'STUDIO_SYNC_TOKEN': secrets.token_urlsafe(32),
                'STUDIO_NAS_PATH': '/'.join(filter(None, [cfg.nas_path, parent, leaf])),
            })
            from fastapi.testclient import TestClient
            from app import main
            with TestClient(main.app) as api:
                login = api.post('/api/auth/login', json={'email': 'deployment-check@localhost.test', 'password': password})
                assert login.status_code == 200
                headers = {'Authorization': 'Bearer ' + login.json()['token']}
                for sequence in (1, 2):
                    response = api.post('/api/projects/1/publish', headers=headers)
                    if response.status_code != 200:
                        raise RuntimeError('Temporary publication failed: HTTP ' + str(response.status_code))
                    manifest = response.json()
                    assert manifest['sequence'] == sequence and len(manifest['files']) == 4
                    assert len(manifest['attachments']) == 1
                    check = remote._request('GET', remote._url(parent, leaf, 'current.json'))
                    assert check.status_code == 200 and check.json() == manifest
                result['twoVerifiedPublications'] = True
                source = api.get('/api/projects/1/documents/pdf4', headers=headers).json()
                response = api.put('/api/projects/1/documents/pdf4', headers=headers, json={
                    'baseRevision': source['revision'], 'pages': {'1': [
                        {'id': 'bg', 'type': 'page-background', 'x': 0, 'y': 0, 'w': 1, 'h': 1, 'color': '#ffffff'},
                        {'id': 'body', 'type': 'text', 'role': 'body', 'cardIndex': 1,
                         'text': 'Deployment NAS archive check.', 'x': .1, 'y': .1, 'w': .8, 'h': .3,
                         'fontSize': 15.75, 'fontFamily': 'Times New Roman'},
                    ]}})
                assert response.status_code == 200
                mediation = api.post('/api/mediations', headers=headers, json={'title': 'Temporary NAS check'}).json()
                pid = mediation['projectId']
                archive = api.post(f'/api/mediations/{pid}/archive', headers=headers)
                assert archive.status_code == 200 and archive.json()['deliveryStatus'] == 'nas-sent'
                assert not archive.json().get('pdfError')
                latest = remote._request('GET', remote._url(parent, leaf, 'Медиации', str(pid), 'latest.json'))
                assert latest.status_code == 200 and latest.json()['revision'] == archive.json()['revision']
                check = remote._request('GET', remote._url(parent, leaf, 'current.json'))
                assert check.json() == manifest
                result['mediationVerifiedSeparately'] = True
    finally:
        cleanup = remote._request('DELETE', remote._url(parent, leaf))
        result['testDirectoryRemoved'] = cleanup.status_code in (200, 204, 404)
        if not parent_existed:
            listing = remote._request('PROPFIND', remote._url(parent), headers={'Depth': '1'})
            if listing.status_code == 207 and len(ET.fromstring(listing.content).findall('{DAV:}response')) == 1:
                remote._request('DELETE', remote._url(parent))
        after = remote._request('GET', remote._url('current.json'))
        result['exhibitionPointerUnchanged'] = after.status_code == 200 and hashlib.sha256(after.content).hexdigest() == pointer_hash
        remote.close()
        if not result['testDirectoryRemoved'] or not result['exhibitionPointerUnchanged']:
            raise RuntimeError('NAS cleanup or release-pointer verification failed')
    print(json.dumps(result))


if __name__ == '__main__': main()

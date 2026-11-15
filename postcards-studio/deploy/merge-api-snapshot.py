"""Overlay a stable API snapshot on a restored database, preserving accounts.

Run offline before starting API/collaboration. Dry run is the default.
The original Yjs volume is retained; template revisions create fresh rooms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sqlalchemy import func, select
from app.config import settings
from app.db import Document, DocumentRevision, Mediation, Project, ProjectTemplate, Release, SessionLocal, User


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.snapshot.resolve()
    inventory = load(root / 'inventory.json')
    if not inventory.get('stableDuringCapture'):
        raise RuntimeError('Snapshot revisions changed during capture; take a stable snapshot')
    marker = settings().storage_dir / 'migrations' / (root.name + '.json')
    if marker.exists():
        print(json.dumps({'alreadyApplied': True, 'report': str(marker)}))
        return
    docs = [load(file) for file in sorted(root.glob('projects/*/pdf*/document.json'))]
    if not docs:
        raise RuntimeError('Snapshot has no documents')
    expected_users = load(root / 'users.json')
    expected_mediations = load(root / 'mediations.json')
    report = {'applied': args.apply, 'snapshot': root.name, 'documents': [], 'newHistory': 0,
              'newAssets': 0, 'newRooms': {}, 'timestamp': datetime.now(timezone.utc).isoformat()}
    with SessionLocal() as db:
        users = {u.email: u for u in db.scalars(select(User))}
        original_passwords = {u.id: u.password_hash for u in users.values()}
        for user in expected_users:
            existing = users.get(user['email'])
            if existing is None or existing.id != user['id'] or existing.role != user['role']:
                raise RuntimeError('Staff accounts differ from dump; reconcile accounts before overlay')
        for mediation in expected_mediations:
            existing = db.get(Mediation, mediation['projectId'])
            if not existing or db.get(User, existing.guest_user_id).email != mediation['login']:
                raise RuntimeError('Mediation accounts differ from dump')
        for document in docs:
            existing = db.get(Document, document['id'])
            if not existing or (existing.project_id, existing.slot) != (document['projectId'], document['slot']):
                raise RuntimeError('Document IDs differ from restored database')
            if existing.revision > document['revision']:
                raise RuntimeError('Database contains newer edits; refusing to overwrite')
            report['documents'].append({'projectId': existing.project_id, 'slot': existing.slot,
                                        'fromRevision': existing.revision, 'toRevision': document['revision']})
            if args.apply:
                existing.title = document['title']
                # Match the API's compact serialization so a read-only Yjs
                # bootstrap does not create a false document revision.
                existing.content_json = json.dumps({'pages': document['pages']}, ensure_ascii=False,
                                                   separators=(',', ':'))
                existing.revision = document['revision']
                existing.updated_by = document['updatedBy']
                existing.updated_at = datetime.fromisoformat(document['updatedAt'])
            folder = root / f'projects/{document["projectId"]}/{document["slot"]}/history'
            saved = {item.revision: item for item in db.scalars(select(DocumentRevision).where(DocumentRevision.document_id == existing.id))}
            for history_file in folder.glob('*.json'):
                history = load(history_file)
                old = saved.get(history['revision'])
                if old:
                    if json.loads(old.content_json).get('pages', {}) != history['pages']:
                        raise RuntimeError('Historical revision differs; refusing to overwrite history')
                    continue
                report['newHistory'] += 1
                if args.apply:
                    db.add(DocumentRevision(document_id=existing.id, revision=history['revision'],
                         content_json=json.dumps({'pages': history['pages']}, ensure_ascii=False),
                         created_at=datetime.fromisoformat(history['createdAt']), created_by=history['createdBy']))
        projects = {d['projectId'] for d in docs}
        for pid in projects:
            project = load(root / f'projects/{pid}/project.json')
            existing = db.get(Project, pid)
            if not existing: raise RuntimeError('Project not found in restored dump')
            template = db.scalar(select(ProjectTemplate).where(ProjectTemplate.project_id == pid))
            if not template or template.revision != project['templateRevision']:
                raise RuntimeError('Shared template revision changed; requires raw template reconciliation')
            for release in load(root / f'projects/{pid}/releases.json'):
                if db.get(Release, release['releaseId']) is None:
                    raise RuntimeError('New release is missing from baseline files; restore it before overlay')
            report['newRooms'][str(pid)] = template.revision + 1
            if args.apply:
                existing.name = project['name']
                template.revision += 1
                template.updated_at = datetime.now(timezone.utc)
                template.updated_by = 'migration'
        for item in expected_mediations:
            if args.apply:
                db.get(Mediation, item['projectId']).archive_manifest_json = json.dumps(item.get('archive', {}), ensure_ascii=False)
        for source in (root / 'assets').rglob('*'):
            if not source.is_file(): continue
            target = settings().storage_dir / 'assets' / source.relative_to(root / 'assets')
            if target.exists():
                if digest(target) != digest(source):
                    raise RuntimeError('Asset path collision; refusing to replace original file')
            else:
                report['newAssets'] += 1
                if args.apply:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
        # A delta archive may omit assets already present in the full backup.
        # Verify every indexed asset, including those omitted from the transfer.
        for item in inventory.get('files', []):
            relative = Path(item['path'])
            if not relative.parts or relative.parts[0] != 'assets': continue
            if relative.is_absolute() or '..' in relative.parts:
                raise RuntimeError('Invalid asset inventory path')
            target = settings().storage_dir / relative
            candidate = target if target.is_file() else root / relative
            if not candidate.is_file() or digest(candidate) != item['sha256']:
                raise RuntimeError('Referenced asset is missing or differs from snapshot')
        if args.apply:
            db.flush()
            if original_passwords != {u.id: u.password_hash for u in db.scalars(select(User))}:
                raise RuntimeError('Account hashes unexpectedly changed')
            for document in docs:
                if json.loads(db.get(Document, document['id']).content_json)['pages'] != document['pages']:
                    raise RuntimeError('Document verification failed')
            db.commit()
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

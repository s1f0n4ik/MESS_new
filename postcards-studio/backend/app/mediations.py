"""Isolated, collaborative fourth documents for individual museum mediations."""
import hashlib
import json
import os
import re
import secrets
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Document, DocumentRevision, Mediation, Project, ProjectTemplate, Release, User, session_scope, utcnow
from .pdf_renderer import render_document, TextOverflowError, sha256
from .security import administrator, current_user, hash_password, require_project_access, sync_access
from .yandex_disk import YandexDiskApiDelivery, YandexDiskDelivery

router = APIRouter()


class CreateMediation(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    sourceProjectId: int = 1
    releaseId: str = Field(default='', max_length=80)


def view(record, db):
    project = db.get(Project, record.project_id)
    guest = db.get(User, record.guest_user_id)
    doc = db.scalar(select(Document).where(Document.project_id == record.project_id, Document.slot == 'pdf4'))
    return {'projectId': project.id, 'title': project.name, 'login': guest.email,
            'sourceProjectId': record.source_project_id, 'revision': doc.revision,
            'createdAt': record.created_at.isoformat(), 'archive': json.loads(record.archive_manifest_json)}


@router.get('/api/mediations')
def list_mediations(user=Depends(current_user), db: Session=Depends(session_scope)):
    query = select(Mediation).order_by(Mediation.created_at.desc())
    if user.role == 'mediation': query = query.where(Mediation.guest_user_id == user.id)
    return [view(record, db) for record in db.scalars(query).all()]


@router.post('/api/mediations')
def create_mediation(body: CreateMediation, user=Depends(current_user), db: Session=Depends(session_scope)):
    if user.role not in ('admin', 'publisher', 'editor'):
        raise HTTPException(403, 'Создать медиацию может сотрудник музея')
    if db.get(Mediation, body.sourceProjectId): raise HTTPException(400, 'Выберите общий документ, а не другую медиацию')
    source = db.scalar(select(Document).where(Document.project_id == body.sourceProjectId, Document.slot == 'pdf4'))
    if not source: raise HTTPException(404, 'Четвёртый документ не найден')
    content = json.loads(source.content_json)
    if body.releaseId:
        release = db.get(Release, body.releaseId)
        if not release or release.project_id != body.sourceProjectId: raise HTTPException(404, 'Релиз не найден')
        manifest = json.loads(release.manifest_json)
        snapshot = settings().storage_dir / 'releases' / release.id / 'editable-pdf4.json'
        if snapshot.is_file(): content = json.loads(snapshot.read_text('utf-8'))
        else:
            published = next((f for f in manifest['files'] if f['slot'] == 'pdf4'), {})
            revision = published.get('documentRevision')
            if revision != source.revision:
                previous = db.scalar(select(DocumentRevision).where(DocumentRevision.document_id == source.id,
                                                                      DocumentRevision.revision == revision))
                if not previous: raise HTTPException(409, 'Для установленного PDF нет редактируемого исходника. Опубликуйте новый комплект на сайте и синхронизируйте приложение.')
                content = json.loads(previous.content_json)
    pages = content.get('pages', {})
    if not pages or not all(any(i.get('type') == 'page-background' for i in items) for items in pages.values()):
        raise HTTPException(409, 'В четвёртом документе сначала нужен редактируемый макет')
    project = Project(name=body.title.strip())
    password = secrets.token_urlsafe(12)
    guest = User(email=f'mediation-{uuid.uuid4().hex[:12]}@mess-studio.ru', name=body.title.strip(),
                 role='mediation', password_hash=hash_password(password))
    db.add_all([project, guest]); db.flush()
    payload = json.dumps({'pages': pages}, ensure_ascii=False, separators=(',', ':'))
    db.add(Document(project_id=project.id, slot='pdf4', title=source.title, content_json=payload,
                    updated_by=user.email))
    db.add(ProjectTemplate(project_id=project.id, revision=1, content_json=payload, updated_by=user.email))
    record = Mediation(project_id=project.id, source_project_id=body.sourceProjectId, guest_user_id=guest.id,
                       source_release_id=body.releaseId, created_by=user.email)
    db.add(record); db.commit()
    return {**view(record, db), 'password': password}


@router.post('/api/mediations/{project_id}/promotion')
def prepare_promotion(project_id: int, user=Depends(administrator), db: Session=Depends(session_scope)):
    record = db.get(Mediation, project_id)
    if not record: raise HTTPException(404, 'Медиация не найдена')
    source = db.scalar(select(Document).where(Document.project_id == project_id, Document.slot == 'pdf4'))
    target = db.scalar(select(Document).where(Document.project_id == record.source_project_id, Document.slot == 'pdf4'))
    texts = {i['id']: i.get('text', '') for items in json.loads(source.content_json)['pages'].values()
             for i in items if i.get('role') == 'body'}
    fields = [{'page': int(page), 'id': i['id'], 'text': texts.get(i['id'], '')}
              for page, items in json.loads(target.content_json)['pages'].items() for i in items if i.get('role') == 'body']
    if set(texts) != {i['id'] for i in fields}:
        raise HTTPException(409, 'Состав полей общего документа изменился. Сначала сопоставьте версии макета.')
    # Apply through the normal Yjs editor so all connected staff see the change.
    return {'sourceProjectId': record.source_project_id, 'mediationRevision': source.revision,
            'documentRevision': target.revision, 'fields': fields}


@router.post('/api/mediations/{project_id}/archive')
def archive_mediation(project_id: int, user=Depends(current_user), db: Session=Depends(session_scope)):
    require_project_access(user, project_id, db)
    record = db.get(Mediation, project_id)
    if not record: raise HTTPException(404, 'Медиация не найдена')
    doc = db.scalar(select(Document).where(Document.project_id == project_id, Document.slot == 'pdf4'))
    cfg = settings()
    version = f'r{doc.revision:010d}'
    folder = cfg.storage_dir / 'mediations' / str(project_id) / version
    if not (folder / 'manifest.json').is_file():
        staging = folder.parent / f'.{version}-{uuid.uuid4().hex}.staging'
        staging.mkdir(parents=True)
        try:
            content = json.loads(doc.content_json)
            (staging / 'editable.json').write_text(json.dumps({'schemaVersion': 1, 'projectId': project_id,
                'title': db.get(Project, project_id).name, 'revision': doc.revision, **content}, ensure_ascii=False), 'utf-8')
            pdf_error = ''
            try: render_document(cfg.template_pdf, content, cfg.storage_dir / 'assets', staging / 'pdf4.pdf')
            except TextOverflowError as exc: pdf_error = str(exc)
            files = [{'name': p.name, 'size': p.stat().st_size, 'sha256': sha256(p)}
                     for p in staging.iterdir() if p.is_file()]
            manifest = {'projectId': project_id, 'version': version, 'revision': doc.revision,
                        'title': db.get(Project, project_id).name, 'files': files, 'pdfError': pdf_error}
            (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), 'utf-8')
            if folder.exists(): shutil.rmtree(staging)
            else: os.replace(staging, folder)
        finally:
            if staging.exists(): shutil.rmtree(staging)
    manifest = json.loads((folder / 'manifest.json').read_text('utf-8'))
    status, error = 'server-only', ''
    if cfg.yandex_delivery_enabled:
        delivery = YandexDiskApiDelivery(cfg.yandex_disk_api_url, cfg.yandex_disk_oauth_token, cfg.yandex_disk_path) if cfg.yandex_disk_oauth_token else YandexDiskDelivery(cfg.yandex_webdav_url, cfg.yandex_disk_username, cfg.yandex_disk_app_password, cfg.yandex_disk_path)
        try: delivery.upload_mediation(folder, manifest); status = 'nas-sent'
        except Exception: status, error = 'retry-needed', 'Версия сохранена на сервере, но NAS недоступен. Повторите отправку.'
        finally: delivery.close()
    value = {**manifest, 'deliveryStatus': status, 'deliveryError': error}
    record.archive_manifest_json = json.dumps(value, ensure_ascii=False); db.commit()
    return value


@router.get('/api/sync/mediations')
def sync_mediations(access=Depends(sync_access), db: Session=Depends(session_scope)):
    return [json.loads(record.archive_manifest_json) for record in db.scalars(select(Mediation))
            if json.loads(record.archive_manifest_json).get('version')]


@router.get('/api/sync/mediations/{project_id}/{version}/{filename}')
def sync_mediation_file(project_id: int, version: str, filename: str, access=Depends(sync_access)):
    if not re.fullmatch(r'r\d{10}', version) or filename not in ('editable.json', 'pdf4.pdf', 'manifest.json'):
        raise HTTPException(400, 'Некорректный путь архива')
    path = settings().storage_dir / 'mediations' / str(project_id) / version / filename
    if not path.is_file(): raise HTTPException(404, 'Файл не найден')
    return FileResponse(path)

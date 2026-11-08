"""Remember one Studio mediation per exhibition run on the coordinator."""
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class Selection(BaseModel):
    runKey: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_.-]+$')
    projectId: int = Field(gt=0)
    title: str = Field(max_length=160)


def create_router(data_dir: Path):
    router = APIRouter(prefix='/api/mediation')
    path = Path(data_dir) / 'mediation-selections.json'
    studio = os.environ.get('POSTCARDS_STUDIO_URL', 'https://mess-studio.ru').rstrip('/')
    url = urlsplit(studio)
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('POSTCARDS_STUDIO_URL должен использовать HTTPS')

    def read():
        try: return json.loads(path.read_text('utf-8'))
        except FileNotFoundError: return {}

    @router.get('/current')
    def current(runKey: str = 'manual'):
        if len(runKey) > 100: raise HTTPException(400, 'Некорректный идентификатор медиации')
        return {'studioUrl': studio, **read().get(runKey, {})}

    @router.post('/current')
    def select(body: Selection):
        values = read()
        values[body.runKey] = {'projectId': body.projectId, 'title': body.title}
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(values, stream, ensure_ascii=False)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {'studioUrl': studio, **values[body.runKey]}

    return router

"""Метаданные PDF-файлов: mtime для cache-buster на клиенте."""
from fastapi import APIRouter

from paths import PDFS_DIR

router = APIRouter()


@router.get("/api/pdfs/meta")
def pdfs_meta():
    out = {}
    for p in sorted(PDFS_DIR.glob("*.pdf")):
        st = p.stat()
        out[p.name] = {"mtime": int(st.st_mtime), "size": st.st_size}
    return out
"""Управление медиа из служебного меню: тексты (PDF) и настраиваемые звуки.

<base_dir>/pdfs/pdf1..pdf4.pdf       — тексты (уже отдаются как /pdfs/*)
<base_dir>/audio/circle1..4.<ext>    — звук начала волны N  (отдаётся как /audio/*)
<base_dir>/audio/vibro_final.<ext>   — вибро-финал
Нет файла звука — фронт играет встроенный из бандла.
"""
from __future__ import annotations

import inspect
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PDF_SLOTS = ("pdf1", "pdf2", "pdf3", "pdf4")
DEFAULT_PDF_TITLES = {slot: f"Документ {index}" for index, slot in enumerate(PDF_SLOTS, 1)}
AUDIO_SLOTS = ("circle1", "circle2", "circle3", "circle4", "vibro_final")
AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a")
DEFAULT_RELEASES_DIR = Path(
    r"Z:\Yandex.Disk\Выставка Анастасии Чермантеевой\Postcards Studio\Релизы"
)


class MediaAdmin:
    def __init__(self, base_dir, pdf_dir=None, on_change: Optional[Callable] = None,
                 template_path: Optional[Path] = None, releases_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir)
        self.pdf_dir = Path(pdf_dir) if pdf_dir else self.base_dir / "pdfs"
        self.audio_dir = self.base_dir / "audio"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self._sources_path = self.base_dir / "media_sources.json"
        self._sources = self._load_sources()
        self._titles_path = self.base_dir / "document_titles.json"
        self._pdf_titles = self._load_titles()
        self._on_change = on_change
        self.template_path = Path(template_path) if template_path else None
        configured_releases = releases_dir or os.environ.get("POSTCARDS_RELEASES_DIR") or DEFAULT_RELEASES_DIR
        self.releases_dir = Path(configured_releases)
        self._sync_state_path = self.base_dir / "release_sync.json"
        self._sync_state = self._load_sync_state()

    # ---------- служебное ----------
    def _load_sources(self) -> dict:
        try:
            return json.loads(self._sources_path.read_text("utf-8"))
        except Exception:
            return {}

    def _save_sources(self) -> None:
        try:
            self._sources_path.write_text(
                json.dumps(self._sources, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception as e:
            print(f"[media] sources save failed: {e}")

    def _load_titles(self) -> dict:
        try:
            raw = json.loads(self._titles_path.read_text("utf-8"))
        except Exception:
            raw = {}
        return {
            slot: str(raw.get(slot) or DEFAULT_PDF_TITLES[slot]).strip()[:80]
            for slot in PDF_SLOTS
        }

    def _save_titles(self) -> None:
        self._titles_path.write_text(
            json.dumps(self._pdf_titles, ensure_ascii=False, indent=2), "utf-8"
        )

    def _load_sync_state(self) -> dict:
        try:
            raw = json.loads(self._sync_state_path.read_text("utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _save_sync_state(self) -> None:
        self._sync_state_path.write_text(
            json.dumps(self._sync_state, ensure_ascii=False, indent=2), "utf-8"
        )

    def set_pdf_title(self, slot: str, title: str) -> None:
        if slot not in PDF_SLOTS:
            raise HTTPException(400, f"неизвестный слот {slot}")
        value = " ".join(str(title or "").split()).strip()
        if not value:
            raise HTTPException(400, "название не может быть пустым")
        if len(value) > 80:
            raise HTTPException(400, "название длиннее 80 символов")
        self._pdf_titles[slot] = value
        self._save_titles()

    async def changed(self) -> None:
        if not self._on_change:
            return
        try:
            r = self._on_change()
            if inspect.isawaitable(r):
                await r
        except Exception as e:
            print(f"[media] on_change failed: {e}")

    def _audio_file(self, slot: str) -> Optional[Path]:
        for p in self.audio_dir.glob(f"{slot}.*"):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                return p
        return None

    def _target(self, kind: str, slot: str, ext: str) -> Path:
        ext = (ext or "").lower()
        if kind == "pdf":
            if slot not in PDF_SLOTS:
                raise HTTPException(400, f"неизвестный слот {slot}")
            if ext != ".pdf":
                raise HTTPException(400, "для текста нужен файл .pdf")
            return self.pdf_dir / f"{slot}.pdf"
        if kind == "audio":
            if slot not in AUDIO_SLOTS:
                raise HTTPException(400, f"неизвестный слот {slot}")
            if ext not in AUDIO_EXTS:
                raise HTTPException(400, f"аудио: {', '.join(AUDIO_EXTS)}")
            return self.audio_dir / f"{slot}{ext}"
        raise HTTPException(400, "kind должен быть pdf или audio")

    def _describe(self, p: Optional[Path]) -> Optional[dict]:
        if not p or not p.exists():
            return None
        st = p.stat()
        return {
            "file": p.name,
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "source": self._sources.get(p.stem),
        }

    def snapshot(self) -> dict:
        return {
            "pdfs": {s: self._describe(self.pdf_dir / f"{s}.pdf") for s in PDF_SLOTS},
            "pdfTitles": dict(self._pdf_titles),
            "audio": {s: self._describe(self._audio_file(s)) for s in AUDIO_SLOTS},
            "dirs": {"pdfs": str(self.pdf_dir), "audio": str(self.audio_dir)},
            "template": {
                "available": bool(self.template_path and self.template_path.is_file()),
                "name": self.template_path.name if self.template_path else None,
                "pages": 28,
                "blocks": 14,
            },
            "sync": {
                "path": str(self.releases_dir),
                "installedReleaseId": self._sync_state.get("installedReleaseId"),
                "lastSyncedAt": self._sync_state.get("lastSyncedAt"),
            },
        }

    def install_template(self) -> None:
        if not self.template_path or not self.template_path.is_file():
            raise HTTPException(404, "встроенный шаблон 2x2 не найден")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = self.base_dir / "pdf-template-backups" / stamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        for slot in PDF_SLOTS:
            target = self.pdf_dir / f"{slot}.pdf"
            if target.is_file():
                shutil.copy2(target, backup_dir / target.name)
        for slot in PDF_SLOTS:
            target = self.pdf_dir / f"{slot}.pdf"
            self._install(
                target,
                lambda tmp, source=self.template_path: shutil.copyfile(source, tmp),
                f"встроенный шаблон 2x2, резервная копия: {backup_dir}",
            )

    def install_release(self, raw_path: str) -> dict:
        release_dir = Path(str(raw_path or "").strip().strip('"'))
        manifest_path = release_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except Exception as exc:
            raise HTTPException(400, f"не удалось прочитать manifest.json: {exc}") from exc
        release_id = str(manifest.get("releaseId") or "").strip()
        files = manifest.get("files")
        if not release_id or not isinstance(files, list):
            raise HTTPException(400, "некорректный манифест релиза")
        by_slot = {str(item.get("slot")): item for item in files if isinstance(item, dict)}
        if set(by_slot) != set(PDF_SLOTS):
            raise HTTPException(400, "релиз должен содержать pdf1–pdf4")
        verified = {}
        for slot in PDF_SLOTS:
            item = by_slot[slot]
            name = str(item.get("name") or "")
            source = (release_dir / name).resolve()
            if release_dir.resolve() not in source.parents or not source.is_file() or source.suffix.lower() != ".pdf":
                raise HTTPException(400, f"файл {slot} не найден в релизе")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if digest != str(item.get("sha256") or "").lower():
                raise HTTPException(400, f"контрольная сумма {slot} не совпадает")
            verified[slot] = source
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_dir = self.base_dir / "pdf-release-backups" / stamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        for slot in PDF_SLOTS:
            target = self.pdf_dir / f"{slot}.pdf"
            if target.is_file():
                shutil.copy2(target, backup_dir / target.name)
        for slot, source in verified.items():
            self._install(self.pdf_dir / f"{slot}.pdf",
                          lambda tmp, src=source: shutil.copyfile(src, tmp),
                          f"Postcards Studio release {release_id}")
        return {"releaseId": release_id, "backupDir": str(backup_dir)}

    def sync_latest_release(self) -> dict:
        """Install the release referenced by current.json in the synced NAS folder."""
        root = self.releases_dir.resolve()
        current_path = root / "current.json"
        try:
            manifest = json.loads(current_path.read_text("utf-8"))
        except FileNotFoundError as exc:
            raise HTTPException(
                404,
                f"current.json не найден в {self.releases_dir}. Проверь подключение диска Z: и синхронизацию Яндекс Диска",
            ) from exc
        except Exception as exc:
            raise HTTPException(400, f"не удалось прочитать {current_path}: {exc}") from exc

        release_id = str(manifest.get("releaseId") or "").strip()
        if not release_id or release_id in {".", ".."} or any(char in release_id for char in "/\\"):
            raise HTTPException(400, "в current.json указан некорректный releaseId")
        release_dir = (root / release_id).resolve()
        if root not in release_dir.parents:
            raise HTTPException(400, "путь релиза выходит за пределы папки Релизы")

        if self._sync_state.get("installedReleaseId") == release_id and all(
            (self.pdf_dir / f"{slot}.pdf").is_file() for slot in PDF_SLOTS
        ):
            return {"releaseId": release_id, "status": "already-current", "backupDir": None}

        result = self.install_release(str(release_dir))
        self._sync_state = {
            "installedReleaseId": release_id,
            "lastSyncedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self._save_sync_state()
        return {**result, "status": "installed"}

    # ---------- запись: временный файл рядом + атомарная подмена ----------
    def _install(self, target: Path, write, source: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.stem}.", suffix=".tmp")
        os.close(fd)
        try:
            write(tmp)
            try:
                os.replace(tmp, target)
            except PermissionError:
                # Windows: файл сейчас отдаётся клиенту (206 Partial Content).
                raise HTTPException(409, "файл сейчас читает клиент — повтори через пару секунд")
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        if target.parent == self.audio_dir:
            # Один слот — один файл: убираем прежнюю версию с другим расширением.
            for p in self.audio_dir.glob(f"{target.stem}.*"):
                if p != target and p.suffix.lower() in AUDIO_EXTS:
                    try:
                        p.unlink()
                    except OSError:
                        pass
        self._sources[target.stem] = source
        self._save_sources()
        print(f"[media] {target.name} <- {source}")

    def import_path(self, kind: str, slot: str, path: str) -> None:
        src = Path(path)
        if not src.is_file():
            raise HTTPException(404, f"файл не найден: {path}")
        target = self._target(kind, slot, src.suffix)
        if target.exists() and src.resolve() == target.resolve():
            return  # выбрали уже стоящий файл
        self._install(target, lambda tmp: shutil.copyfile(src, tmp), str(src))

    def import_bytes(self, kind: str, slot: str, data: bytes, filename: str) -> None:
        if not data:
            raise HTTPException(400, "пустой файл")
        target = self._target(kind, slot, Path(filename or "").suffix)
        self._install(target, lambda tmp: Path(tmp).write_bytes(data), filename or "upload")

    def remove(self, kind: str, slot: str) -> None:
        if kind != "audio":
            raise HTTPException(400, "сбросить можно только звук — у текста нет встроенного варианта")
        p = self._audio_file(slot)
        if p:
            p.unlink()
        self._sources.pop(slot, None)
        self._save_sources()
        print(f"[media] {slot}: сброшен на встроенный")


class ImportBody(BaseModel):
    kind: str
    slot: str
    path: str


class ReleaseBody(BaseModel):
    path: str


class TitleBody(BaseModel):
    title: str


def create_router(admin: MediaAdmin) -> APIRouter:
    r = APIRouter(prefix="/api/media")

    @r.get("")
    async def get_media():
        return admin.snapshot()

    @r.post("/import")
    async def import_media(body: ImportBody):
        admin.import_path(body.kind, body.slot, body.path)
        await admin.changed()
        return admin.snapshot()

    @r.post("/upload/{kind}/{slot}")
    async def upload_media(kind: str, slot: str, request: Request, filename: str = ""):
        admin.import_bytes(kind, slot, await request.body(), filename)
        await admin.changed()
        return admin.snapshot()

    @r.post("/template")
    async def install_template():
        admin.install_template()
        await admin.changed()
        return admin.snapshot()

    @r.put("/pdf/{slot}/title")
    async def set_pdf_title(slot: str, body: TitleBody):
        admin.set_pdf_title(slot, body.title)
        await admin.changed()
        return admin.snapshot()

    @r.post("/release")
    async def install_release(body: ReleaseBody, request: Request):
        client = request.client.host if request.client else ""
        if client not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(403, "установка релиза разрешена только локальному Sync Agent")
        result = admin.install_release(body.path)
        await admin.changed()
        return {**admin.snapshot(), "installedRelease": result}

    @r.post("/sync")
    async def sync_latest():
        # Путь фиксирован в конфигурации самого ПК1, поэтому запрос не может
        # заставить сервер читать произвольный файл. Кнопку можно нажать и из
        # служебной панели на соседнем ноутбуке в той же сети.
        result = admin.sync_latest_release()
        if result.get("status") == "installed":
            await admin.changed()
        return {**admin.snapshot(), "installedRelease": result}

    @r.delete("/{kind}/{slot}")
    async def delete_media(kind: str, slot: str):
        admin.remove(kind, slot)
        await admin.changed()
        return admin.snapshot()

    return r


def mount_static(app, admin: MediaAdmin) -> None:
    app.mount("/audio", StaticFiles(directory=str(admin.audio_dir)), name="audio")

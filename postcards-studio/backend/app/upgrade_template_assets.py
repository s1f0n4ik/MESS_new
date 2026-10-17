from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from PIL import Image

from .config import settings
from .db import Document, DocumentRevision, DocumentTemplate, SessionLocal, init_db
from .editable_template import (
    LEGACY_CARD_BY_SCAN, extract_customer_scans, indent_paragraphs, prefer_legacy_for_small_scans,
)


def upgrade_pages(pages: dict[str, list[dict]], scans: dict[int, dict]) -> bool:
    """Upgrade only images and paragraph indentation, preserving all user work."""
    changed = False
    for items in pages.values():
        for item in items:
            if item.get("role") == "body":
                current = str(item.get("text") or "")
                indented = indent_paragraphs(current)
                if current != indented:
                    item["text"] = indented
                    changed = True
            if item.get("role") != "scan" or item.get("missing"):
                continue
            try:
                number = int(item.get("sequence"))
            except (TypeError, ValueError):
                continue
            scan = scans.get(number)
            if not scan:
                continue
            if item.get("src") != scan["url"]:
                item["src"] = scan["url"]
                changed = True
            if scan.get("label") and item.get("sourceLabel") != scan["label"]:
                item["sourceLabel"] = scan["label"]
                changed = True
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Upgrade scan quality and add red-line paragraph indents")
    parser.add_argument("--source-docx", type=Path, required=True)
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    cfg = settings()
    assets_root = cfg.storage_dir / "assets"
    scans = extract_customer_scans(args.source_docx, assets_root, args.project_id, "starter-v3")
    prefer_legacy_for_small_scans(scans, assets_root, args.project_id, "starter-v3")
    if 21 not in scans:
        legacy = assets_root / str(args.project_id) / "starter-v1" / f"legacy-card-{LEGACY_CARD_BY_SCAN[21]:02d}.png"
        if not legacy.is_file():
            raise FileNotFoundError(f"Не найден исходник скана 21: {legacy}")
        folder = assets_root / str(args.project_id) / "starter-v3"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "scan-21.png"
        shutil.copyfile(legacy, target)
        scans[21] = {"path": target, "url": f"/assets/{args.project_id}/starter-v3/scan-21.png",
                     "label": "А. М. Греков. Тачанка"}

    dimensions = {}
    for number, value in scans.items():
        with Image.open(value["path"]) as image:
            dimensions[number] = [image.width, image.height]
    print(json.dumps({"projectId": args.project_id, "apply": args.apply, "scans": dimensions}, ensure_ascii=False))
    if not args.apply:
        return

    init_db()
    stamp = datetime.now(timezone.utc)
    with SessionLocal() as db:
        documents = db.scalars(select(Document).where(Document.project_id == args.project_id)).all()
        updated = 0
        for document in documents:
            content = json.loads(document.content_json)
            if not upgrade_pages(content.get("pages") or {}, scans):
                continue
            payload = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            document.revision += 1
            document.content_json = payload
            document.updated_at = stamp
            document.updated_by = "quality-and-indent-upgrade"
            db.add(DocumentRevision(document_id=document.id, revision=document.revision,
                                    content_json=payload, created_at=stamp,
                                    created_by="quality-and-indent-upgrade"))
            template = db.scalar(select(DocumentTemplate).where(DocumentTemplate.document_id == document.id))
            if template:
                template_content = json.loads(template.content_json)
                upgrade_pages(template_content.get("pages") or {}, scans)
                template.content_json = json.dumps(template_content, ensure_ascii=False, separators=(",", ":"))
                template.updated_at = stamp
                template.updated_by = "quality-and-indent-upgrade"
            updated += 1
        db.commit()
    print(f"Updated documents: {updated}")
if __name__ == "__main__":
    main()

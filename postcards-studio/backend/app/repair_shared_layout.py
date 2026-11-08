"""Repair existing documents after deploying the shared layout fix.

Run without --apply first. Stop collaboration before applying so pending Yjs
updates are flushed; the incremented template revision starts fresh rooms.
Existing body text and the current shared line positions are preserved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from .db import Document, DocumentRevision, ProjectTemplate, SessionLocal
from .main import (clean_pages, fill_missing_shared_material, merge_global_template,
                   normalize_global_template, now)


def bodies(pages: dict) -> dict:
    return {(page, item["id"]): item.get("text", "") for page, items in pages.items()
            for item in items if item.get("role") == "body"}


def summary(pages: dict) -> dict:
    scans, captions = [], []
    for items in pages.values():
        codes = {item.get("cardIndex"): item.get("scanCode")
                 for item in items if item.get("role") == "scan"}
        for item in items:
            if item.get("role") == "scan" and not item.get("missing") and not item.get("src"):
                scans.append(item.get("scanCode"))
            if item.get("role") == "caption" and not item.get("text", "").strip():
                captions.append(codes.get(item.get("cardIndex")))
    return {"emptyScans": scans, "emptyCaptions": captions, "bodyFields": len(bodies(pages))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-file", type=Path)
    args = parser.parse_args()
    if args.apply and (not args.backup_file or args.backup_file.exists()):
        parser.error("--apply requires a new --backup-file path")
    with SessionLocal() as db:
        documents = db.scalars(select(Document).where(Document.project_id == args.project_id)
                               .order_by(Document.slot).with_for_update()).all()
        template = db.scalar(select(ProjectTemplate).where(ProjectTemplate.project_id == args.project_id)
                             .with_for_update())
        if len(documents) != 4 or not template:
            raise RuntimeError("Expected four documents and an existing shared template")
        originals = {document.id: json.loads(document.content_json).get("pages") or {}
                     for document in documents}
        master = json.loads(template.content_json).get("pages") or {}
        master = clean_pages(fill_missing_shared_material(master, list(originals.values())))
        master = normalize_global_template(master)
        merged = {document.id: merge_global_template(originals[document.id], master) for document in documents}
        for document in documents:
            if bodies(merged[document.id]) != bodies(originals[document.id]):
                raise RuntimeError(f"Body text would change in {document.slot}; repair cancelled")
        report = {"apply": args.apply, "oldTemplateRevision": template.revision,
                  "newTemplateRevision": template.revision + 1, "documents": [
                      {"slot": document.slot, "before": summary(originals[document.id]),
                       "after": summary(merged[document.id]), "bodyTextPreserved": True}
                      for document in documents]}
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        if not args.apply:
            return
        backup = {"templateRevision": template.revision, "templateContent": template.content_json,
                  "documents": [{"id": doc.id, "slot": doc.slot, "revision": doc.revision,
                                 "content": doc.content_json} for doc in documents]}
        args.backup_file.parent.mkdir(parents=True, exist_ok=True)
        with args.backup_file.open("x", encoding="utf-8") as stream:
            json.dump(backup, stream, ensure_ascii=False)
        stamp = now()
        for document in documents:
            old_checkpoint = db.scalar(select(DocumentRevision.id).where(
                DocumentRevision.document_id == document.id, DocumentRevision.revision == document.revision))
            if not old_checkpoint:
                db.add(DocumentRevision(document_id=document.id, revision=document.revision,
                                        content_json=document.content_json, created_by="pre-layout-repair"))
            document.revision += 1
            document.content_json = json.dumps({"pages": merged[document.id]}, ensure_ascii=False, separators=(",", ":"))
            document.updated_at = stamp
            document.updated_by = "shared-layout-repair"
            db.add(DocumentRevision(document_id=document.id, revision=document.revision,
                                    content_json=document.content_json, created_by="shared-layout-repair"))
        template.revision += 1
        template.content_json = json.dumps({"pages": master}, ensure_ascii=False, separators=(",", ":"))
        template.updated_at = stamp
        template.updated_by = "shared-layout-repair"
        db.commit()
        print("REPAIR_COMMITTED", flush=True)


if __name__ == "__main__":
    main()

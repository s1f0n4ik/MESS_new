from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .db import Document, DocumentRevision, DocumentTemplate, SessionLocal, init_db
from .editable_template import DOCUMENT_TITLES, import_legacy_pdf, without_body_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Create editable starter documents from the legacy PDF")
    parser.add_argument("--source-pdf", type=Path, required=True)
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--apply", action="store_true", help="write to the database; otherwise only validate")
    args = parser.parse_args()

    cfg = settings()
    pages_with_formal_analysis = import_legacy_pdf(args.source_pdf, cfg.storage_dir / "assets", args.project_id)
    blank_body_pages = without_body_text(pages_with_formal_analysis)
    print(json.dumps({
        "projectId": args.project_id,
        "pages": len(pages_with_formal_analysis),
        "scans": sum(item.get("role") == "scan" for values in pages_with_formal_analysis.values() for item in values),
        "textCharacters": sum(len(item.get("text", "")) for values in pages_with_formal_analysis.values() for item in values),
        "apply": args.apply,
    }, ensure_ascii=False))
    if not args.apply:
        return

    init_db()
    stamp = datetime.now(timezone.utc)
    with SessionLocal() as db:
        documents = {value.slot: value for value in db.scalars(
            select(Document).where(Document.project_id == args.project_id)
        ).all()}
        missing = sorted(set(DOCUMENT_TITLES) - set(documents))
        if missing:
            raise RuntimeError(f"Не найдены документы: {', '.join(missing)}")

        for slot, title in DOCUMENT_TITLES.items():
            document = documents[slot]
            # Preserve the complete pre-migration state in ordinary history.
            previous = db.scalar(select(DocumentRevision).where(
                DocumentRevision.document_id == document.id,
                DocumentRevision.revision == document.revision,
            ))
            if not previous:
                db.add(DocumentRevision(document_id=document.id, revision=document.revision,
                                        content_json=document.content_json,
                                        created_at=stamp, created_by="editable-template-backup"))
            pages = pages_with_formal_analysis if slot == "pdf2" else blank_body_pages
            payload = json.dumps({"pages": pages}, ensure_ascii=False, separators=(",", ":"))
            document.title = title
            document.revision += 1
            document.content_json = payload
            document.updated_at = stamp
            document.updated_by = "editable-template-migration"
            db.add(DocumentRevision(document_id=document.id, revision=document.revision,
                                    content_json=payload, created_at=stamp,
                                    created_by="editable-template-migration"))
            template = db.scalar(select(DocumentTemplate).where(DocumentTemplate.document_id == document.id))
            if template:
                template.content_json = payload
                template.updated_at = stamp
                template.updated_by = "editable-template-migration"
            else:
                db.add(DocumentTemplate(document_id=document.id, content_json=payload,
                                        updated_at=stamp, updated_by="editable-template-migration"))
        db.commit()
    print("Editable documents and templates saved")


if __name__ == "__main__":
    main()

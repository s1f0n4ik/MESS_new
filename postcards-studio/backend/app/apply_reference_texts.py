"""Apply the verified Illustrator-equivalent typography and supplied texts.

This is an explicit, backup-first production repair. It preserves scans,
captions, guide geometry, page order and all unrelated body text.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import select

from .db import Document, DocumentRevision, ProjectTemplate, SessionLocal, utcnow
from .layout_geometry import DEFAULT_FONT_SIZE, align_template_text
from .text_flow import split_for_fields


TARGETS = {
    "pdf1": ((3, "Т1"), (4, "Т1О")),
    "pdf2": ((3, "Т2"), (4, "Т2О")),
    "pdf3": ((3, "Т3"), (4, "Т3О")),
}
ACTOR = "reference-composition-20261029"
LINE_GEOMETRY_KEYS = ("x", "y", "w", "h", "shape", "fill", "stroke", "strokeWidth", "strokeStyle")


def normalize_paragraphs(value: str) -> str:
    """Match editor paste behaviour: every non-empty paragraph has a red line."""
    lines = str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(("\u2003" + line.lstrip(" \t\u2003")) if line.strip() else "" for line in lines).strip()


def sync_caption_dividers(pages: dict, reference_pages: dict) -> dict:
    """Use one approved divider geometry in every document and the common template."""
    result = json.loads(json.dumps(pages))
    reference = {
        item.get("id"): item
        for items in reference_pages.values()
        for item in items
        if item.get("role") == "caption-divider"
    }
    for items in result.values():
        for item in items:
            source = reference.get(item.get("id"))
            if item.get("role") == "caption-divider" and source:
                for key in LINE_GEOMETRY_KEYS:
                    if key in source:
                        item[key] = source[key]
    return result


def standardize(pages: dict, distribute: bool) -> tuple[dict, list[dict]]:
    result = json.loads(json.dumps(pages))
    for items in result.values():
        for item in items:
            if item.get("type") == "text" and item.get("role") in {"caption", "body"}:
                item.update(
                    fontFamily="Times New Roman",
                    fontSize=DEFAULT_FONT_SIZE,
                    bold=False,
                    italic=False,
                    align="justify" if item.get("role") == "body" else "right",
                )
    result = align_template_text(result)
    warnings = []
    if distribute:
        for page in range(1, 29, 2):
            for first in [item for item in result[str(page)] if item.get("role") == "body"]:
                second = next(item for item in result[str(page + 1)]
                              if item.get("role") == "body" and item.get("cardIndex") == first.get("cardIndex"))
                original = first.get("text", "") + second.get("text", "")
                if not original:
                    continue
                parts, overflow = split_for_fields(original, [first, second])
                if "".join(parts) != original:
                    raise RuntimeError("Text flow lost content")
                first["text"], second["text"] = parts
                if overflow:
                    warnings.append({"page": page, "cardIndex": first.get("cardIndex"), "characters": len(original)})
    return result, warnings


def set_pair(pages: dict, card_index: int, value: str) -> dict:
    first = next(item for item in pages["3"] if item.get("role") == "body" and item.get("cardIndex") == card_index)
    second = next(item for item in pages["4"] if item.get("role") == "body" and item.get("cardIndex") == card_index)
    text = normalize_paragraphs(value)
    if not text:
        first["text"] = second["text"] = ""
        return {"cardIndex": card_index, "characters": 0, "overflow": False, "cleared": True}
    parts, overflow = split_for_fields(text, [first, second])
    if "".join(parts) != text:
        raise RuntimeError("Reference text flow lost content")
    first["text"], second["text"] = parts
    return {"cardIndex": card_index, "characters": len(text), "parts": list(map(len, parts)), "overflow": overflow}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--backup-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and (not args.backup_file or args.backup_file.exists()):
        parser.error("Applying requires a new backup path")
    source = json.loads(args.source_file.read_text(encoding="utf-8"))
    sections = source.get("sections") or {}
    missing = [name for name in ("Т1", "Т1О", "Т2", "Т3", "Т3О") if not sections.get(name, "").strip()]
    if missing:
        raise RuntimeError(f"Required source texts are empty: {', '.join(missing)}")

    with SessionLocal() as db:
        docs = db.scalars(select(Document).where(Document.project_id == 1)
                          .order_by(Document.slot).with_for_update()).all()
        master = db.scalar(select(ProjectTemplate).where(ProjectTemplate.project_id == 1).with_for_update())
        if [doc.slot for doc in docs] != ["pdf1", "pdf2", "pdf3", "pdf4"] or not master:
            raise RuntimeError("Expected four documents and a common template")
        backup = {
            "templateRevision": master.revision,
            "templateContent": master.content_json,
            "documents": [{"id": doc.id, "slot": doc.slot, "revision": doc.revision,
                           "content": doc.content_json} for doc in docs],
        }
        reports = []
        new_values = []
        reference_pages = json.loads(docs[0].content_json)["pages"]
        for record in [*docs, master]:
            value = json.loads(record.content_json)
            original = json.loads(record.content_json)
            synced_pages = sync_caption_dividers(value["pages"], reference_pages)
            pages, warnings = standardize(synced_pages, record is not master)
            loaded = []
            if record is not master and record.slot in TARGETS:
                for card_index, source_name in TARGETS[record.slot]:
                    loaded.append({"source": source_name, **set_pair(pages, card_index, sections.get(source_name, ""))})
            value["pages"] = pages
            # The repair may change typography and body contents only.
            for page, items in original["pages"].items():
                before = {item["id"]: item for item in items}
                for item in pages[page]:
                    old = before[item["id"]]
                    if old.get("role") not in {"caption", "body", "caption-divider"} and old != item:
                        raise RuntimeError(f"Unexpected layout mutation: {record.slot if record is not master else 'template'} {item['id']}")
                    if old.get("role") == "caption" and old.get("text") != item.get("text"):
                        raise RuntimeError(f"Caption changed: {item['id']}")
            new_values.append(value)
            reports.append({
                "slot": getattr(record, "slot", "common-template"),
                "oldRevision": record.revision,
                "newRevision": record.revision + 1,
                "loaded": loaded,
                "existingOverflow": warnings,
            })

        if args.apply:
            args.backup_file.parent.mkdir(parents=True, exist_ok=True)
            with args.backup_file.open("x", encoding="utf-8") as stream:
                json.dump(backup, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            for record, value in zip([*docs, master], new_values):
                if record is not master and not db.scalar(select(DocumentRevision.id).where(
                        DocumentRevision.document_id == record.id,
                        DocumentRevision.revision == record.revision)):
                    db.add(DocumentRevision(document_id=record.id, revision=record.revision,
                                            content_json=record.content_json, created_by=f"before-{ACTOR}"))
                record.revision += 1
                record.content_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                record.updated_at = utcnow()
                record.updated_by = ACTOR
                if record is not master:
                    db.add(DocumentRevision(document_id=record.id, revision=record.revision,
                                            content_json=record.content_json, created_by=ACTOR))
            db.commit()
        print(json.dumps({"applied": args.apply, "fontSize": DEFAULT_FONT_SIZE,
                          "emptySourceTexts": [name for name in ("Т2О",) if not sections.get(name, "").strip()],
                          "records": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

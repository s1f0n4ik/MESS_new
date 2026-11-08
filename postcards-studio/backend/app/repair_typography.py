"""Apply the approved text formatting to all four live drafts, with backup."""
import argparse
import json
from pathlib import Path

from sqlalchemy import select

from .db import Document, DocumentRevision, ProjectTemplate, SessionLocal, utcnow
from .layout_geometry import align_template_text, DEFAULT_FONT_SIZE, LINE_HEIGHT, PAGE_HEIGHT
from .text_flow import split_for_fields


def revise(pages, distribute=True, guide_pages=None):
    result = json.loads(json.dumps(pages))
    for page_number, items in result.items():
        guides = {item['id']:item for item in (guide_pages or {}).get(page_number, [])}
        for item in items:
            if item.get('role') in ('outline', 'outline-vertical', 'scan-divider', 'caption-divider', 'divider'):
                guide = guides.get(item['id'], {})
                for key in ('x','y','w','h','stroke','strokeWidth','strokeStyle','side'):
                    if key in guide: item[key] = guide[key]
            if item.get('role') in ('caption', 'body'):
                item.update(fontFamily='Times New Roman', fontSize=DEFAULT_FONT_SIZE, bold=False, italic=False,
                            align='justify' if item['role']=='body' else 'right')
        for item in items:
            if item.get('role') != 'caption-divider': continue
            upper = next(i for i in items if i.get('role')=='scan-divider' and i['cardIndex']==item['cardIndex'])
            item['y'] = upper['y'] + upper['h']/2 + ((3*LINE_HEIGHT-.22)*DEFAULT_FONT_SIZE+1)/PAGE_HEIGHT - item['h']/2
    result = align_template_text(result)
    warnings = []
    for page in range(1, 29, 2):
        for first in result.get(str(page), []):
            if first.get('role') != 'body':
                continue
            second = next((i for i in result.get(str(page + 1), [])
                           if i.get('role') == 'body' and i.get('cardIndex') == first.get('cardIndex')), None)
            if not second:
                raise RuntimeError('Missing continuation field')
            original = first.get('text', '') + second.get('text', '')
            if not distribute or not original:
                continue
            parts, overflow = split_for_fields(original, [first, second])
            assert ''.join(parts) == original
            if any(len(part) > 30000 for part in parts):
                raise RuntimeError('Refusing to exceed persisted field capacity')
            first['text'], second['text'] = parts
            if overflow:
                warnings.append({'page':page, 'field':first.get('cardIndex'), 'characters':len(original)})
    return result, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-file', type=Path)
    args = parser.parse_args()
    if args.apply and (not args.backup_file or args.backup_file.exists()):
        parser.error('Applying requires a new backup path')
    actor = 'automatic-text-flow-15-3-20261026'
    with SessionLocal() as db:
        docs = db.scalars(select(Document).where(Document.project_id==1)
                          .order_by(Document.slot).with_for_update()).all()
        master = db.scalar(select(ProjectTemplate).where(ProjectTemplate.project_id==1).with_for_update())
        if [d.slot for d in docs] != ['pdf1','pdf2','pdf3','pdf4'] or not master:
            raise RuntimeError('Expected all four documents and common template')
        report = []
        new_values = []
        guide_pages = json.loads(docs[0].content_json)['pages']
        for record in [*docs, master]:
            value = json.loads(record.content_json)
            if set(value.get('pages', {})) != {str(i) for i in range(1, 29)}:
                raise RuntimeError('Expected 28 pages')
            revised, warnings = revise(value['pages'], record is not master, guide_pages)
            # Scans, captions and the current ordering cannot change here.
            for page, items in value['pages'].items():
                for original, updated in zip(items, revised[page]):
                    assert original['id'] == updated['id']
                    if original.get('role') == 'scan': assert original == updated
                    if original.get('role') == 'caption': assert original.get('text') == updated.get('text')
            value['pages'] = revised
            new_values.append(value)
            report.append({'slot':getattr(record,'slot','common-template'),
                           'oldRevision':record.revision,'newRevision':record.revision+1,
                           'bodyTextPreserved':True,'overflowFields':warnings})
        if args.apply:
            backup = {'templateRevision':master.revision,'templateContent':master.content_json,
                      'documents':[{'id':d.id,'slot':d.slot,'revision':d.revision,'content':d.content_json} for d in docs]}
            args.backup_file.parent.mkdir(parents=True,exist_ok=True)
            with args.backup_file.open('x',encoding='utf-8') as stream:
                json.dump(backup,stream,ensure_ascii=False)
                stream.flush()
                import os
                os.fsync(stream.fileno())
            for record, value in zip([*docs,master],new_values):
                if record is not master and not db.scalar(select(DocumentRevision.id).where(
                    DocumentRevision.document_id==record.id,DocumentRevision.revision==record.revision)):
                    db.add(DocumentRevision(document_id=record.id,revision=record.revision,
                                            content_json=record.content_json,created_by=f'before-{actor}'))
                record.revision += 1
                record.content_json = json.dumps(value,ensure_ascii=False,separators=(',',':'))
                record.updated_by = actor
                record.updated_at = utcnow()
                if record is not master:
                    db.add(DocumentRevision(document_id=record.id,revision=record.revision,
                                            content_json=record.content_json,created_by=actor))
            db.commit()
        print(json.dumps({'applied':args.apply,'documents':report},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()

import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from app.editable_template import blank_editable_layout
from app.layout_geometry import align_template_text, body_line_height
from app.pdf_renderer import TextOverflowError, render_document
from app.text_flow import split_for_fields


class TextFlowTests(unittest.TestCase):
    def setUp(self):
        self.pages = align_template_text(blank_editable_layout())
        self.fields = [next(i for i in self.pages[str(p)] if i.get('role') == 'body' and i['cardIndex'] == 1)
                       for p in (1, 2)]

    def test_text_fits_two_fields_without_loss_or_font_reduction(self):
        sentence = ('На лицевой стороне открытки изображены люди и лошади на заснеженном поле. '
                    'В центре находится артиллерийское орудие. ')
        text = (('\u2003' + sentence * 7 + '\n') * 6)[:4200]
        parts, overflow = split_for_fields(text, self.fields)
        self.assertEqual(''.join(parts), text)
        self.assertFalse(overflow)
        self.assertTrue(all(parts))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            doc = fitz.open()
            doc.new_page(width=1190.55, height=841.89)
            doc.new_page(width=1190.55, height=841.89)
            doc.save(root / 'blank.pdf')
            doc.close()
            pages = {str(p): [{**field, 'text': text_part}] for p, field, text_part in zip((1, 2), self.fields, parts)}
            render_document(root / 'blank.pdf', {'pages': pages}, root, root / 'output.pdf')
            with fitz.open(root / 'output.pdf') as doc:
                for page_number, page in enumerate(doc):
                    spans = [span for block in page.get_text('dict')['blocks'] if 'lines' in block
                             for line in block['lines'] for span in line['spans']]
                    self.assertTrue(spans)
                    self.assertTrue(all(abs(span['size'] - 15.75) < .01 for span in spans))
                    self.assertTrue(all(span['bbox'][3] <= 815 for span in spans))
                    lines = [line for block in page.get_text('dict')['blocks'] if 'lines' in block for line in block['lines']]
                    right = (self.fields[0]['x'] + self.fields[0]['w']) * page.rect.width
                    self.assertAlmostEqual(max(line['bbox'][2] for line in lines), right, delta=1)
                    field = self.fields[page_number]
                    step = body_line_height(field['fontSize'], field['h'] * page.rect.height) * field['fontSize']
                    self.assertAlmostEqual(lines[1]['spans'][0]['origin'][1] - lines[0]['spans'][0]['origin'][1], step, delta=.01)
                    if page_number == 0:
                        bottom = (field['y'] + field['h']) * page.rect.height
                        self.assertGreaterEqual(bottom - spans[-1]['bbox'][3], 0)
                        self.assertLess(bottom - spans[-1]['bbox'][3], 2)

    def test_identical_text_is_split_identically_in_independent_columns(self):
        text = ('\u2003Текст для сравнения одинаковых колонок. ' * 130)[:4200]
        right = [next(i for i in self.pages[str(p)] if i.get('role') == 'body' and i['cardIndex'] == 2)
                 for p in (1, 2)]
        right[0]['w'] += 1e-15
        right[1]['w'] -= 1e-15
        left_parts, left_overflow = split_for_fields(text, self.fields)
        right_parts, right_overflow = split_for_fields(text, right)
        self.assertEqual(left_parts, right_parts)
        self.assertEqual(left_overflow, right_overflow)
        self.assertEqual(''.join(left_parts), text)

    def test_excess_text_is_retained_and_export_refuses_to_omit_it(self):
        text = 'Очень длинный текст. ' * 2000
        parts, overflow = split_for_fields(text, self.fields)
        self.assertEqual(''.join(parts), text)
        self.assertTrue(overflow)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            doc = fitz.open(); doc.new_page(); doc.save(root / 'blank.pdf'); doc.close()
            with self.assertRaises(TextOverflowError):
                render_document(root / 'blank.pdf', {'pages': {'1': [{**self.fields[0], 'text': text}]}},
                                root, root / 'output.pdf')

    def test_short_and_long_text_keep_the_same_template_contours(self):
        import copy
        pages = copy.deepcopy(self.pages)
        body = next(i for i in pages['1'] if i.get('role') == 'body' and i['cardIndex'] == 1)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            doc = fitz.open(); doc.new_page(width=1190.55, height=841.89)
            doc.save(root / 'blank.pdf'); doc.close()
            contours = []
            for text in ('', 'Ручки поднимаются вверх и почти параллельны горлышку.',
                         'На лицевой стороне открытки изображены люди и лошади. ' * 12):
                body['text'] = text
                render_document(root / 'blank.pdf', {'pages': {'1': pages['1']}}, root, root / 'output.pdf')
                with fitz.open(root / 'output.pdf') as doc:
                    contours.append([(tuple(drawing['rect']), drawing['dashes'], drawing['width'])
                                     for drawing in doc[0].get_drawings()])
            self.assertEqual(contours[0], contours[1])
            self.assertEqual(contours[1], contours[2])
            outline = next(i for i in pages['1'] if i.get('role') == 'outline' and i['cardIndex'] == 1)
            self.assertTrue(any(abs(rect[1] - (outline['y'] + outline['h']) * 841.89) < .01
                                and abs(rect[3] - rect[1]) < .01 for rect, _, _ in contours[0]))


if __name__ == '__main__':
    unittest.main()

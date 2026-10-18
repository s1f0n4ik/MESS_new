from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "deliverables"
SHOTS = ROOT / "docs" / "manual_work" / "screenshots"
WEB_OUT = OUT / "Postcards Studio Инструкция веб сервиса.docx"
DESKTOP_OUT = OUT / "Postcards Краткая инструкция для выставки.docx"

INK = "171717"
MUTED = "5E6570"
BLUE = "215FA6"
PALE_BLUE = "EAF2FB"
PALE_GREEN = "EAF6EF"
PALE_YELLOW = "FFF6D9"
PALE_RED = "FCEBEC"
LINE = "D9DEE5"
WHITE = "FFFFFF"


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color=LINE, size="5") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    tr_pr.append(repeat)


def set_keep_with_next(paragraph, value=True) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    el = p_pr.find(qn("w:keepNext"))
    if value and el is None:
        p_pr.append(OxmlElement("w:keepNext"))


def remove_paragraph_border(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    border = p_pr.find(qn("w:pBdr"))
    if border is not None:
        p_pr.remove(border)


def set_repeat_heading_rows(table, count=1) -> None:
    for row in table.rows[:count]:
        set_repeat_table_header(row)


def set_cell_margins(cell, top=85, start=100, bottom=85, end=100) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def configure(doc: Document, title: str, subject: str) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.62)
    section.left_margin = Inches(0.72)
    section.right_margin = Inches(0.72)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(9.4)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.08

    for name, size, before, after in (
        ("Title", 27, 0, 12),
        ("Subtitle", 12, 0, 16),
        ("Heading 1", 18, 13, 7),
        ("Heading 2", 12.5, 10, 4),
        ("Heading 3", 10.5, 8, 3),
    ):
        style = styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(INK)
        style.font.bold = name != "Subtitle"
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    doc.core_properties.title = title
    doc.core_properties.subject = subject
    doc.core_properties.author = "MESS / Postcards"
    doc.core_properties.keywords = "Postcards, инструкция, веб-сервис, выставка, NAS, PDF"


def footer(doc: Document, label: str) -> None:
    for section in doc.sections:
        f = section.footer
        p = f.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4)
        run = p.add_run(f"{label}   •   ")
        run.font.name = "Arial"
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor.from_string(MUTED)
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), "PAGE")
        p._p.append(field)


def title_page(doc: Document, kicker: str, title: str, subtitle: str, audience: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Inches(0.6)
    r = p.add_run(kicker.upper())
    r.font.name = "Arial"
    r.font.size = Pt(10)
    r.font.bold = True
    r.font.color.rgb = RGBColor.from_string(BLUE)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(12)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(title)
    r.font.name = "Arial"
    r.font.size = Pt(27)
    r.font.bold = True
    r.font.color.rgb = RGBColor.from_string(INK)
    p = doc.add_paragraph(style="Subtitle")
    p.add_run(subtitle)

    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    table.columns[0].width = Inches(6.8)
    cell = table.cell(0, 0)
    set_cell_shading(cell, PALE_BLUE)
    set_cell_border(cell, "C7D8EC")
    set_cell_margins(cell, 150, 170, 150, 170)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run("Для кого")
    r.bold = True
    p = cell.add_paragraph(audience)
    p.paragraph_format.space_after = Pt(0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Inches(3.25)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = p.add_run("Версия от 18 октября 2026")
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor.from_string(MUTED)
    doc.add_page_break()


def heading(doc: Document, text: str, level=1) -> None:
    doc.add_heading(text, level=level)


def body(doc: Document, text: str, bold_lead: str | None = None) -> None:
    p = doc.add_paragraph()
    if bold_lead and text.startswith(bold_lead):
        p.add_run(bold_lead).bold = True
        p.add_run(text[len(bold_lead):])
    else:
        p.add_run(text)


def bullets(doc: Document, items: list[str], ordered=False) -> None:
    style = "List Number" if ordered else "List Bullet"
    for item in items:
        p = doc.add_paragraph(style=style)
        p.paragraph_format.space_after = Pt(3)
        p.add_run(item)


def steps(doc: Document, items: list[str]) -> None:
    for number, item in enumerate(items, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.28)
        p.paragraph_format.first_line_indent = Inches(-0.28)
        p.paragraph_format.space_after = Pt(3)
        marker = p.add_run(f"{number}.  ")
        marker.bold = True
        p.add_run(item)


def callout(doc: Document, title: str, text: str, tone="blue") -> None:
    fills = {"blue": PALE_BLUE, "green": PALE_GREEN, "yellow": PALE_YELLOW, "red": PALE_RED}
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    cell = table.cell(0, 0)
    set_cell_shading(cell, fills[tone])
    set_cell_border(cell, "CBD2DA")
    set_cell_margins(cell, 105, 130, 105, 130)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(title)
    r.bold = True
    p = cell.add_paragraph(text)
    p.paragraph_format.space_after = Pt(0)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float] | None = None) -> None:
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    hdr = t.rows[0]
    for idx, text in enumerate(headers):
        cell = hdr.cells[idx]
        set_cell_shading(cell, "EEF1F4")
        set_cell_border(cell)
        set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(text)
        r.bold = True
    for values in rows:
        row = t.add_row()
        for idx, text in enumerate(values):
            cell = row.cells[idx]
            set_cell_border(cell)
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.add_run(text)
    if widths:
        for row in t.rows:
            for idx, width in enumerate(widths):
                row.cells[idx].width = Inches(width)
    set_repeat_heading_rows(t)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def screenshot(doc: Document, filename: str, caption: str, width=6.7) -> None:
    path = SHOTS / filename
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_together = True
    p.add_run().add_picture(str(path), width=Inches(width))
    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    c.paragraph_format.space_after = Pt(7)
    r = c.add_run(caption)
    r.italic = True
    r.font.size = Pt(8)
    r.font.color.rgb = RGBColor.from_string(MUTED)


def web_guide() -> None:
    doc = Document()
    configure(doc, "Postcards Studio — инструкция веб-сервиса", "Работа медиаторов, публикация PDF и доставка на выставку")
    footer(doc, "Postcards Studio — веб-сервис")
    title_page(
        doc,
        "Inheritance / Postcards",
        "Postcards Studio",
        "Обновлённая инструкция по совместной подготовке четырёх документов",
        "Медиаторы, редакторы, издатели и администраторы проекта.",
    )

    heading(doc, "1. Что делает сервис")
    body(doc, "Postcards Studio — общий онлайн-редактор материалов выставки. Исходником является структурированный редактируемый макет, а PDF создаётся только при скачивании или публикации. Сервис доступен по адресу https://mess-studio.ru.")
    callout(doc, "Главное правило", "Сохранение и публикация — разные действия. Рабочие правки сохраняются автоматически, но в приложение выставки попадает только явно опубликованный комплект из четырёх PDF.", "yellow")
    table(doc, ["Раздел", "Назначение"], [
        ["Экфрасисы", "Документ для ПК1"],
        ["Формальный анализ", "Документ для ПК2"],
        ["Контекст создания", "Документ для ПК3"],
        ["Контекст восприятия", "Документ для ПК4"],
    ], [1.8, 4.9])

    heading(doc, "2. Вход и роли")
    steps(doc, [
        "Откройте https://mess-studio.ru в современном браузере.",
        "Введите личную учётную запись. Не передавайте общий пароль другим участникам.",
        "Выберите один из четырёх документов в левой панели.",
        "Дождитесь статуса подключения и только затем начинайте редактирование.",
    ])
    table(doc, ["Роль", "Возможности"], [
        ["editor", "Редактировать документы, экспортировать текущий документ, работать с историей."],
        ["publisher", "Всё из editor, плюс сохранение шаблона и публикация комплекта из 4 PDF."],
        ["admin", "Всё из publisher, плюс создание и удаление учётных записей медиаторов."],
    ], [1.25, 5.45])

    heading(doc, "3. Как устроен редактор")
    body(doc, "Слева находятся четыре документа, сверху — панель команд, ниже — свойства выбранного объекта. На рабочем поле показаны 28 страниц: 14 разворотов по две страницы. Все страницы и элементы доступны для редактирования.")
    table(doc, ["Команда", "Что делает"], [
        ["＋ Текст", "Добавляет редактируемый текстовый блок на текущую страницу."],
        ["＋ Изображение", "Загружает PNG, JPG или WEBP и помещает его на страницу."],
        ["＋ Фигура", "Добавляет прямоугольник, эллипс или линию; доступны цвет, толщина и тип контура."],
        ["＋ Маска", "Создаёт цветную плашку, которой можно закрыть ненужный фрагмент."],
        ["Дублировать / Удалить", "Копирует или удаляет выбранный объект. Удаление также работает клавишей Delete."],
        ["Очистить…", "Очищает страницу до белого листа, возвращает шаблон на странице или создаёт пустой документ."],
    ], [1.75, 4.95])

    heading(doc, "4. Работа с готовым редактируемым макетом")
    body(doc, "В штатном шаблоне изображения, подписи и основные тексты — отдельные объекты. Контуры и геометрия закреплены, чтобы случайное движение не ломало вёрстку.")
    heading(doc, "Текст", 2)
    steps(doc, [
        "Щёлкните по текстовому полю внутри пунктирного контура.",
        "Введите или вставьте текст как в обычном редакторе.",
        "В панели свойств настройте единый шрифт, размер, цвет, жирное или курсивное начертание и выравнивание.",
        "Для изменения геометрии нажмите «Разблокировать положение», переместите или измените размер и снова нажмите «Закрепить положение».",
    ])
    callout(doc, "Единый шрифт", "Изменение пункта «Единый шрифт» применяется ко всем текстовым полям выбранного документа. Для основного макета используйте Times New Roman, если художественная группа не утвердила другое.", "blue")
    heading(doc, "Изображения", 2)
    steps(doc, [
        "Выберите слот изображения или нажмите «＋ Изображение».",
        "Для штатного слота используйте «Заменить файл».",
        "Режим «Вписать» показывает изображение целиком и центрирует его; «Заполнить» заполняет область с возможной обрезкой.",
        "При необходимости разблокируйте положение, измените рамку и снова закрепите её.",
    ])
    heading(doc, "Линии и контуры", 2)
    steps(doc, [
        "Выберите горизонтальную или вертикальную пунктирную линию. По умолчанию используется тонкий вариант «Как в Illustrator».",
        "Нажмите «Разблокировать положение», чтобы переместить линию. Её внешний вид и координата при разблокировке не меняются.",
        "Потяните за круглую ручку на конце линии, чтобы укоротить или удлинить её без появления выступающих «хвостов».",
        "При необходимости выберите другой вариант пунктира и толщину. После проверки нажмите «Зафиксировать и синхронизировать».",
    ])
    body(doc, "Изменение геометрии штатного элемента синхронизируется с однотипными элементами макета. Текст, подписи и изображения при этом не копируются между карточками.")

    heading(doc, "5. Новый макет, Word и шаблоны")
    table(doc, ["Задача", "Действие"], [
        ["Начать с подготовленной структуры", "Нажмите «Новый редактируемый макет». Создадутся 28 белых страниц с закреплёнными слотами изображений, подписями и текстовыми полями."],
        ["Автоматически расставить сканы", "Нажмите «Импорт таблицы Word» и выберите DOCX. Берётся последняя таблица; ячейки читаются слева направо и сверху вниз, изображения вписываются и центрируются."],
        ["Зафиксировать удачную основу", "Пользователь publisher или admin нажимает «Сохранить как шаблон». Геометрия и стили становятся единым шаблоном для всех 14 разворотов и четырёх документов; тексты и сканы каждого документа сохраняются отдельно."],
        ["Вернуться к сохранённой основе", "Нажмите «Применить шаблон». Общий шаблон применяется без подмены текстов и изображений; действие видно всем участникам."],
        ["Полностью начать заново", "В меню «Очистить…» выберите «Создать пустой документ». Все 28 страниц станут белыми."],
    ], [2.0, 4.7])
    callout(doc, "Перед массовой заменой", "Изменение общего шаблона обновляет вёрстку сразу во всех четырёх документах. Перед сохранением проверьте первый и последний разворот; вручную исправлять 56 отдельных страниц не требуется.", "yellow")

    heading(doc, "6. Совместная работа и сохранение")
    bullets(doc, [
        "Аватары в правом верхнем углу показывают участников текущего документа.",
        "Правки синхронизируются сразу; при кратком обрыве сети они остаются в локальном буфере браузера и отправляются после восстановления связи.",
        "Рабочее состояние сохраняется после изменений, но автоматическая контрольная версия в истории создаётся не чаще одного раза в 15 минут.",
        "Экспорт PDF и публикация всегда создают отдельную контрольную версию.",
        "Ctrl+Z отменяет, Ctrl+Y повторяет, Ctrl+D дублирует выбранный объект, Delete удаляет его.",
    ])
    heading(doc, "История", 2)
    steps(doc, [
        "Нажмите «История».",
        "Выберите версию по номеру, дате и автору.",
        "Подтвердите восстановление. Оно станет общим для всех медиаторов, а прежняя версия останется в истории.",
    ])

    heading(doc, "7. Скачать PDF и опубликовать комплект")
    heading(doc, "Скачать один документ", 2)
    steps(doc, [
        "Откройте нужный документ и дождитесь статуса сохранения.",
        "Нажмите «Скачать PDF».",
        "Откройте файл локально и проверьте кириллицу, красные строки, переносы, изображения, все 28 страниц и границы текстовых полей. Предпросмотр использует те же метрики текста, что и опубликованный PDF.",
    ])
    heading(doc, "Опубликовать для выставки", 2)
    steps(doc, [
        "Проверьте по очереди все четыре документа.",
        "Пользователь publisher или admin нажимает «Опубликовать 4 PDF».",
        "Дождитесь идентификатора нового релиза. Сервис соберёт четыре неизменяемых PDF и manifest.json с контрольными суммами.",
        "Не публикуйте повторно, если после проверки ничего не изменилось.",
    ])
    callout(doc, "Важно", "Кнопка «Скачать PDF» сохраняет только текущий документ на ваш компьютер. Кнопка «Опубликовать 4 PDF» создаёт комплект, который получает выставочное приложение.", "green")

    heading(doc, "8. Пользователи")
    body(doc, "Раздел «Медиаторы» доступен администратору.")
    steps(doc, [
        "Откройте «Медиаторы» в верхней панели.",
        "Создайте именную учётную запись и назначьте минимально необходимую роль.",
        "Чтобы отозвать доступ, нажмите «Удалить» напротив пользователя и подтвердите действие.",
    ])
    callout(doc, "Ограничение", "Текущую учётную запись удалить нельзя. Перед удалением другого администратора убедитесь, что остаётся хотя бы один рабочий admin.", "red")

    heading(doc, "9. Как публикация попадает на выставку")
    table(doc, ["Этап", "Результат"], [
        ["1. Публикация", "mess-studio.ru создаёт неизменяемый комплект: pdf1–pdf4 и manifest.json."],
        ["2. Архив NAS", "Опубликованный комплект появляется в общей папке NAS / Яндекс Диска; current.json указывает на актуальную версию."],
        ["3. Синхронизация на ПК1", "В десктопном приложении оператор нажимает «Синхронизировать все документы». Приложение читает current.json и проверяет SHA‑256 всех четырёх PDF."],
        ["4. Установка", "ПК1 создаёт резервную копию прежнего комплекта и атомарно заменяет pdf1–pdf4 в локальном кеше."],
        ["5. Показ", "ПК1–ПК4 получают документы от координатора и продолжают работать на последнем установленном релизе без интернета."],
    ], [1.4, 5.3])
    body(doc, "Рекомендуемая папка архива: Z:\\Yandex.Disk\\Выставка Анастасии Чермантеевой\\Postcards Studio\\Релизы. Внутри неё не редактируйте PDF вручную и не меняйте current.json.")

    heading(doc, "10. Быстрая диагностика")
    table(doc, ["Симптом", "Что сделать"], [
        ["Редактор пишет «Офлайн»", "Не закрывайте вкладку. Проверьте интернет и дождитесь повторного подключения; затем убедитесь, что статус снова нормальный."],
        ["Изменения другого участника не видны", "Проверьте, что открыт тот же документ. Обновите вкладку только после возвращения соединения."],
        ["Объект не двигается", "Он закреплён. Выберите объект и нажмите «Разблокировать положение»."],
        ["PDF выглядит не так", "Проверьте выбранный документ, все 28 страниц, режим изображения и переполнение текста; затем скачайте заново."],
        ["На выставке старая версия", "Проверьте новый релиз и доступность диска Z:, затем на ПК1 нажмите «Синхронизировать все документы». Если NAS подключён под другой буквой, задайте POSTCARDS_RELEASES_DIR."],
    ], [2.0, 4.7])
    heading(doc, "Контроль перед публикацией", 2)
    bullets(doc, [
        "Все четыре документа просмотрены целиком.",
        "Кириллица, переносы, курсив и жирное начертание отображаются правильно.",
        "Изображения вписаны или обрезаны осознанно и не выходят за контуры.",
        "История содержит контрольную версию, а в редакторе нет статуса офлайн.",
        "После публикации записан идентификатор релиза и проверена доставка на ПК1.",
    ])

    OUT.mkdir(parents=True, exist_ok=True)
    doc.save(WEB_OUT)


def desktop_guide() -> None:
    doc = Document()
    configure(doc, "Postcards — краткая инструкция для выставки", "Запуск и управление инсталляцией на ПК1–ПК4")
    footer(doc, "Postcards — памятка выставки")
    title_page(
        doc,
        "Inheritance / Postcards",
        "Краткая инструкция для выставки",
        "Запуск, проверка, работа посетителей и перезапуск следующего показа",
        "Технический оператор и дежурный медиатор на площадке.",
    )

    heading(doc, "1. Запуск стенда")
    steps(doc, [
        "Включите локальную сеть, аудио/MIDI‑оборудование и ПК1.",
        "Запустите Postcards на ПК1 и дождитесь появления сцены с открытками.",
        "Запустите приложение на ПК2, ПК3 и ПК4.",
        "На ПК1 нажмите M и убедитесь, что ws — online, а pc1, pc2, pc3 и pc4 отмечены зелёным.",
        "Проверьте MIDI, звук и открытие документов, затем обязательно выполните Hard reset.",
    ])
    callout(doc, "Порядок важен", "ПК1 — координатор. Его запускают первым; остальные компьютеры подключаются к нему по адресу http://192.168.88.54:8787.", "blue")
    screenshot(doc, "02-main-scene.png", "Штатный экран посетителя: восемь открыток")

    heading(doc, "2. Первичная настройка компьютеров")
    body(doc, "Настройка выполняется один раз. Вернуться к ней можно из меню по клавише M.")
    table(doc, ["Компьютер", "Роль", "Координатор", "Адрес"], [
        ["ПК1", "PC1", "включён", "http://localhost:8787"],
        ["ПК2", "PC2", "выключен", "http://192.168.88.54:8787"],
        ["ПК3", "PC3", "выключен", "http://192.168.88.54:8787"],
        ["ПК4", "PC4", "выключен", "http://192.168.88.54:8787"],
    ], [0.65, 0.7, 1.2, 4.15])
    steps(doc, [
        "Выберите роль, укажите адрес и нажмите «Проверить».",
        "Продолжайте только после сообщения «Координатор отвечает».",
        "На ПК1 оставьте включённым меню администратора по M.",
        "Нажмите «Сохранить и запустить».",
    ])
    screenshot(doc, "01-setup.png", "Экран настройки ПК1; на ПК2–ПК4 выбирается своя роль и сетевой адрес")

    heading(doc, "3. Проверка перед каждым показом")
    bullets(doc, [
        "ПК1 показывает ws: online; все четыре роли видны в Devices.",
        "Включён режим «Выставка / MIDI / Reaper».",
        "MIDI‑порт открыт; входящие тестовые ноты распознаются по правильному каналу.",
        "Все четыре документа открываются вручную и содержат актуальный опубликованный комплект.",
        "Звук кликов и финальный звук проверены.",
        "После любых тестов выполнен Hard reset.",
    ])
    callout(doc, "Не пропускайте сброс", "Ручное открытие PDF и имитация MIDI меняют реальное состояние сценария. Перед посетителями всегда нажимайте Hard reset.", "yellow")

    heading(doc, "4. Обновление документов с NAS")
    body(doc, "Публикация в Postcards Studio не заменяет файлы на выставочном ПК автоматически. После публикации установите свежий комплект на ПК1 одной командой.")
    steps(doc, [
        "Убедитесь, что диск Z: доступен и папка «Релизы» содержит current.json.",
        "На ПК1 нажмите M и найдите раздел «Документы и звуки».",
        "Нажмите «Синхронизировать все документы» и дождитесь сообщения с идентификатором установленного релиза.",
        "Откройте все четыре документа вручную и проверьте первую и последнюю страницы.",
        "После проверки закройте окна и выполните Hard reset.",
    ])
    callout(doc, "Путь по умолчанию", "Z:\\Yandex.Disk\\Выставка Анастасии Чермантеевой\\Postcards Studio\\Релизы. Если NAS смонтирован иначе, задайте переменную POSTCARDS_RELEASES_DIR на ПК1.", "blue")

    heading(doc, "5. Что происходит во время показа")
    body(doc, "На каждом компьютере ведётся собственный счётчик. Посетитель нажимает открытку, она переворачивается и воспроизводит связанный фрагмент. Нажатие во время уже играющего фрагмента не засчитывается.")
    body(doc, "Когда любой один компьютер достигает 17 засчитанных кликов, ПК1 отправляет в Reaper MIDI‑ноту 72 и запускается последовательность показа документов. Счётчики других компьютеров остаются независимыми.", bold_lead="Когда")
    screenshot(doc, "06-pdf-view.png", "Окно документа во время показа")

    heading(doc, "6. Горячие клавиши оператора")
    table(doc, ["Клавиша", "Действие"], [
        ["M", "Открыть или закрыть меню администратора. Работает и на финальном чёрном экране."],
        ["F", "Перевернуть все открытки на четырёх ПК без звука и без увеличения счётчиков. Повторное нажатие возвращает их."],
        ["P", "Свернуть или вернуть окно документа на текущем компьютере."],
        ["L", "Открыть или закрыть журнал диагностики."],
        ["Esc", "Закрыть открытое служебное окно."],
    ], [0.8, 5.9])
    callout(doc, "Русская раскладка", "M и F привязаны к физическим клавишам и работают при русской раскладке.", "green")

    heading(doc, "7. Финальный чёрный экран и следующий показ")
    steps(doc, [
        "На чёрном экране нажмите M на ПК1.",
        "Нажмите Hard reset. Сбросятся сценарий, четыре счётчика, блокировки и положение открыток.",
        "Закройте меню клавишей Esc или M.",
        "Убедитесь, что снова видна сцена с открытками и ws остаётся online.",
    ])
    callout(doc, "Какой сброс использовать", "Для нового полного показа нужен именно Hard reset. Reset scenario предназначен только для служебного восстановления текущего сценария.", "yellow")

    heading(doc, "8. Если что-то не работает")
    table(doc, ["Симптом", "Действие"], [
        ["ПК2–ПК4 offline", "Проверьте адрес 192.168.88.54:8787, кабель/сеть и правило файрвола для порта 8787; затем повторите «Проверить»."],
        ["MIDI виден, но команды нет", "Проверьте режим выставки, порт, канал и маппинг; откройте журнал L."],
        ["Документ не открылся", "На ПК1 откройте нужную роль вручную. Если комплект устарел, проверьте диск Z: и нажмите «Синхронизировать все документы»."],
        ["После теста странное состояние", "Остановите тест и выполните Hard reset."],
        ["Только чёрный экран", "Это штатный финал. Нажмите M, затем Hard reset."],
    ], [1.8, 4.9])
    heading(doc, "Что записать для разработчика", 2)
    bullets(doc, [
        "точное время ошибки и роль компьютера",
        "текущую фазу сценария и счётчик кликов",
        "MIDI‑ноту и канал, если проблема связана с Reaper",
        "несколько строк журнала L до и после события",
        "идентификатор опубликованного релиза PDF",
    ])

    heading(doc, "9. Памятка в одну минуту")
    table(doc, ["Перед показом", "Во время", "После"], [[
        "ПК1 первым → все роли зелёные → MIDI и PDF проверены → Hard reset",
        "Не менять сеть; F — переворот без кликов; P — свернуть PDF; L — журнал",
        "На чёрном экране M → Hard reset → проверить сцену и online",
    ]], [2.25, 2.25, 2.25])
    body(doc, "Опубликованные PDF хранятся в общем архиве NAS и устанавливаются в локальный кеш ПК1. Если интернет исчезнет во время выставки, приложение продолжит работать на последнем успешно установленном комплекте.")

    OUT.mkdir(parents=True, exist_ok=True)
    doc.save(DESKTOP_OUT)


if __name__ == "__main__":
    web_guide()
    desktop_guide()
    print(WEB_OUT)
    print(DESKTOP_OUT)

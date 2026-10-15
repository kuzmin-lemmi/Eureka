"""Выгрузки для оргкомитета: Excel, Word и архив с работами.

groups — список (направление, номер секции); None — все секции всех направлений.
Отклонённые заявки никуда не попадают. СНИЛС не выгружается: файлы пересылают по почте.
"""

import re
import zipfile
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import AWARD_ORDER, ConferenceSettings, Section, Submission

HEADER_FILL = PatternFill("solid", fgColor="FFF3B0")
TITLE_FONT = Font(bold=True, size=14)
BOLD = Font(bold=True)


def _created(s):
    return timezone.localtime(s.created_at).strftime("%d.%m.%Y %H:%M")


# (заголовок, ширина колонки, значение из заявки)
COLUMNS = [
    ("№", 5, None),
    ("Заявка", 9, lambda s: s.number),
    ("Участник", 26, lambda s: s.full_name),
    ("Класс", 7, lambda s: s.grade),
    ("Соавтор", 26, lambda s: s.coauthor),
    ("Образовательная организация", 40, lambda s: s.school),
    ("Муниципальный район", 24, lambda s: s.district),
    ("Название работы", 45, lambda s: s.title),
    ("Руководитель", 28, lambda s: s.supervisor),
    ("Должность", 22, lambda s: s.supervisor_position),
    ("Телефон руководителя", 18, lambda s: s.supervisor_phone),
    ("Второй руководитель", 28, lambda s: s.supervisor2),
    ("Почта участника", 26, lambda s: s.email),
    ("Допуск", 13, lambda s: s.get_admission_display() if s.admission else ""),
    ("Подана", 17, _created),
]
PARTICIPANT_COLUMNS = COLUMNS[:2] + [("Секция", 34, lambda s: s.section_label)] + COLUMNS[2:]
# Список для проверяющего: без телефонов и почты.
REVIEWER_COLUMNS = [
    ("№", 5, None),
    ("Заявка", 9, lambda s: s.number),
    ("Участник", 26, lambda s: s.full_name),
    ("Класс", 7, lambda s: s.grade),
    ("Соавтор", 26, lambda s: s.coauthor),
    ("Образовательная организация", 40, lambda s: s.school),
    ("Руководитель", 28, lambda s: s.supervisor),
    ("Название работы", 45, lambda s: s.title),
    ("Файл в архиве", 45, lambda s: work_filename(s)),
]


def all_groups():
    return [(s, n) for s in Section.objects.all() for n in range(1, s.groups + 1)]


def group_submissions(section, number):
    return list(
        Submission.objects.filter(section=section, section_number=number)
        .select_related("section")
        .order_by("last_name", "first_name", "pk")
    )


def _clean_name(text, limit):
    """Строка, годная для имени файла или папки в Windows."""
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:limit].rstrip(" .") or "без названия"


def work_filename(s):
    ext = Path(s.original_filename or s.file.name).suffix.lower()
    return f"{s.pk:04d} {_clean_name(s.full_name, 60)} — {_clean_name(s.title, 70)}{ext}"


def _sheet_title(name, number, groups, used):
    """Имя листа Excel: до 31 символа, без []:*?/\\, уникальное."""
    base = re.sub(r"\s+", " ", re.sub(r"[\[\]:*?/\\]", " ", name)).strip()
    suffix = f" {number}" if groups > 1 else ""
    title = base[: 31 - len(suffix)].rstrip() + suffix
    candidate, i = title, 2
    while candidate in used:
        tail = f" ({i})"
        candidate, i = title[: 31 - len(tail)] + tail, i + 1
    used.add(candidate)
    return candidate


def _fill_sheet(ws, submissions, columns, header_row):
    ws.append([title for title, *_ in columns])
    for cell in ws[header_row]:
        cell.font, cell.fill = BOLD, HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for i, submission in enumerate(submissions, start=1):
        ws.append([i if get is None else get(submission) for _, _, get in columns])
    for col, (_, width, _) in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = f"C{header_row + 1}"
    if submissions:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(columns))}{ws.max_row}"


def _save(wb):
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_sections_workbook(groups=None, columns=COLUMNS):
    """Excel: лист «Сводка» и по листу на каждую секцию."""
    groups = all_groups() if groups is None else groups
    wb = Workbook()
    summary = wb.active
    summary.title = "Сводка"
    summary.append(["Направление", "Секция", "Работ", "Участников", "Мест в секции"])
    for cell in summary[1]:
        cell.font, cell.fill = BOLD, HEADER_FILL
    for letter, width in zip("ABCDE", (55, 60, 9, 13, 15)):
        summary.column_dimensions[letter].width = width

    used = {"Сводка"}
    for section, number in groups:
        submissions = group_submissions(section, number)
        label = section.group_label(number)
        people = sum(s.people for s in submissions)
        summary.append([section.name, label, len(submissions), people, section.capacity])

        ws = wb.create_sheet(_sheet_title(section.name, number, section.groups, used))
        ws.append([label])
        ws["A1"].font = TITLE_FONT
        ws.append([f"Работ: {len(submissions)} из {section.capacity}, участников: {people}"])
        _fill_sheet(ws, submissions, columns, header_row=3)
    return _save(wb)


def build_participants_workbook():
    """Excel: все участники, подавшие работы, на одном листе."""
    submissions = [s for section, number in all_groups() for s in group_submissions(section, number)]
    wb = Workbook()
    ws = wb.active
    ws.title = "Все участники"
    _fill_sheet(ws, submissions, PARTICIPANT_COLUMNS, header_row=1)
    return _save(wb)


def build_reviewer_workbook(groups):
    """Список для проверяющего: одним листом, без контактов."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Список работ"
    rows = []
    for section, number in groups:
        rows.extend(group_submissions(section, number))
    columns = REVIEWER_COLUMNS
    if len(groups) > 1:
        columns = REVIEWER_COLUMNS[:2] + [("Секция", 34, lambda s: s.section_label)] + REVIEWER_COLUMNS[2:]
    _fill_sheet(ws, rows, columns, header_row=1)
    return _save(wb)


# Этапы 1 и 2: таблицы учеников в формате рабочих документов оргкомитета.
STUDENT_HEADERS = ["№", "Секция", "ФИО", "Кл.", "ОУ", "Название работы", "Руководитель", "Дата подачи, e-mail"]
STUDENT_WIDTHS = [5, 28, 28, 6, 45, 45, 26, 28]
STUDENT_DOCX_WIDTHS = [1, 3.6, 3.6, 1, 5.5, 5.5, 3.6, 3.6]

ADMITTED_HEADERS = STUDENT_HEADERS[:-1]
ADMITTED_WIDTHS = STUDENT_WIDTHS[:-1]
ADMITTED_DOCX_WIDTHS = [1, 3.6, 3.8, 1, 6.2, 6.2, 4]

# Этап 3: по образцу списка оргкомитета — строка на работу, соавторы через запятую.
WINNERS_HEADERS = ["№", "ФИО", "Название работы", "Секция", "ОУ", "Статус"]
WINNERS_WIDTHS = [5, 28, 40, 28, 50, 26]
WINNERS_DOCX_WIDTHS = [1, 4, 5.5, 4, 7.5, 4.5]
FONT_DIR = Path(__file__).resolve().parent / "fonts"


def _student_rows(groups, contact):
    """Строка на каждого ученика: у работы с соавтором две строки."""
    rows = []
    for section, number in groups:
        for s in group_submissions(section, number):
            if not contact and s.admission != Submission.Admission.ADMITTED:
                continue
            supervisor = s.supervisor + (f"\n{s.supervisor2}" if s.supervisor2 else "")
            people = [(s.full_name, s.grade)]
            if s.coauthor_last_name:
                people.append((f"{s.coauthor_last_name} {s.coauthor_first_name}", s.coauthor_grade))
            for name, grade in people:
                row = [len(rows) + 1, s.section_label, name, grade, s.school, s.title, supervisor]
                if contact:
                    row.append(f"{timezone.localtime(s.created_at):%d.%m.%Y}\n{s.email}")
                rows.append(row)
    return rows


def student_rows():
    """Этап 1: все ученики; секции — в порядке направлений."""
    return _student_rows(all_groups(), contact=True)


def admitted_rows():
    """Этап 2: ученики допущенных работ; секции — по алфавиту."""
    groups = sorted(all_groups(), key=lambda g: g[0].group_label(g[1]).casefold())
    return _student_rows(groups, contact=False)


def admitted_title():
    conf = ConferenceSettings.load()
    return f"Список участников, допущенных ко 2 этапу {conf.full_name} школьников «Эврика» в {conf.year} году"


def winners_title():
    return f"Победители и призеры {ConferenceSettings.load().full_name} «Эврика»"


def winners_rows():
    """Этап 3: работы с местом или номинацией; секции по алфавиту, внутри — места, затем номинации."""
    works = Submission.objects.exclude(award="").select_related("section")
    works = sorted(works, key=lambda s: (s.section_label.casefold(), AWARD_ORDER.index(s.award), s.last_name, s.pk))
    rows = []
    for s in works:
        names = s.full_name + (f",\n{s.coauthor_last_name} {s.coauthor_first_name}" if s.coauthor_last_name else "")
        rows.append([len(rows) + 1, names, s.title, s.section_label, s.school, s.get_award_display()])
    return rows


def _table_workbook(sheet_title, headers, widths, rows, title=None):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    header_row = 1
    if title:
        ws.append([title])
        ws["A1"].font = TITLE_FONT
        header_row = 3
        ws.append([])
    ws.append(headers)
    for cell in ws[header_row]:
        cell.font, cell.fill = BOLD, HEADER_FILL
    for row in rows:
        ws.append(row)
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    for row in ws.iter_rows(min_row=header_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = f"A{header_row + 1}"
    if rows:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(headers))}{ws.max_row}"
    return _save(wb)


def _table_docx(title, headers, widths_cm, rows, note=None, subtitle=None):
    doc = Document()
    page = doc.sections[0]
    page.orientation = WD_ORIENT.LANDSCAPE
    page.page_width, page.page_height = page.page_height, page.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(page, side, Cm(1.5))
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10)

    if subtitle:
        doc.add_paragraph(subtitle).runs[0].italic = True
    heading = doc.add_heading(title, level=1)
    if note:
        doc.add_paragraph(note)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, headers):
        cell.text = text
        cell.paragraphs[0].runs[0].bold = True
    for row in rows:
        for cell, value in zip(table.add_row().cells, row):
            cell.text = str(value)
    for row in table.rows:
        for cell, width in zip(row.cells, widths_cm):
            cell.width = Cm(width)
    # Шапка таблицы повторяется на каждой странице.
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def build_students_workbook():
    return _table_workbook("Все ученики", STUDENT_HEADERS, STUDENT_WIDTHS, student_rows())


def build_students_docx():
    rows = student_rows()
    return _table_docx(
        "Список учеников по секциям", STUDENT_HEADERS, STUDENT_DOCX_WIDTHS, rows,
        note=f"Учеников: {len(rows)}", subtitle=ConferenceSettings.load().title,
    )


def build_admitted_workbook():
    return _table_workbook("Допущенные", ADMITTED_HEADERS, ADMITTED_WIDTHS, admitted_rows(), title=admitted_title())


def build_admitted_docx():
    return _table_docx(admitted_title(), ADMITTED_HEADERS, ADMITTED_DOCX_WIDTHS, admitted_rows())


def build_admitted_pdf():
    return _table_pdf(admitted_title(), ADMITTED_HEADERS, ADMITTED_DOCX_WIDTHS, admitted_rows())


def build_winners_workbook():
    return _table_workbook("Победители и призёры", WINNERS_HEADERS, WINNERS_WIDTHS, winners_rows(), title=winners_title())


def build_winners_docx():
    return _table_docx(winners_title(), WINNERS_HEADERS, WINNERS_DOCX_WIDTHS, winners_rows())


def build_winners_pdf():
    return _table_pdf(winners_title(), WINNERS_HEADERS, WINNERS_DOCX_WIDTHS, winners_rows())


def _table_pdf(heading, headers, widths_cm, rows):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    if "EurekaSerif" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("EurekaSerif", str(FONT_DIR / "DejaVuSerifCondensed.ttf")))
        pdfmetrics.registerFont(TTFont("EurekaSerif-Bold", str(FONT_DIR / "DejaVuSerifCondensed-Bold.ttf")))
        pdfmetrics.registerFontFamily("EurekaSerif", normal="EurekaSerif", bold="EurekaSerif-Bold")

    cell = ParagraphStyle("cell", fontName="EurekaSerif", fontSize=8.5, leading=10.5)
    head = ParagraphStyle("head", parent=cell, fontName="EurekaSerif-Bold")
    title = ParagraphStyle("title", parent=cell, fontName="EurekaSerif-Bold", fontSize=13, leading=17, alignment=TA_CENTER)

    def para(value, style=cell):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)

    data = [[para(h, head) for h in headers]]
    data += [[para(v) for v in row] for row in rows]
    widths = [w * cm for w in widths_cm]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFF3B0")),
    ]))
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=heading,
    )
    pdf.build([Paragraph(escape(heading), title), Spacer(1, 0.4 * cm), table])
    return buffer.getvalue()


def build_sections_docx(groups=None):
    """Word: каждая секция с новой страницы — заголовок и таблица участников, готово к печати."""
    groups = all_groups() if groups is None else groups
    doc = Document()
    page = doc.sections[0]
    page.orientation = WD_ORIENT.LANDSCAPE
    page.page_width, page.page_height = page.page_height, page.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(page, side, Cm(1.5))
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)

    conf_title = ConferenceSettings.load().title
    headers = ["№", "Участник", "Класс", "Образовательная организация", "Руководитель", "Название работы"]
    widths = [Cm(1), Cm(5), Cm(1.5), Cm(6.5), Cm(5), Cm(7.5)]
    for index, (section, number) in enumerate(groups):
        if index:
            doc.add_page_break()
        submissions = group_submissions(section, number)
        doc.add_paragraph(conf_title).runs[0].italic = True
        doc.add_heading(section.group_label(number), level=1)
        people = sum(s.people for s in submissions)
        doc.add_paragraph(f"Работ: {len(submissions)} из {section.capacity}, участников: {people}")
        if not submissions:
            doc.add_paragraph("Заявок пока нет.")
            continue
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        for cell, text in zip(table.rows[0].cells, headers):
            cell.text = text
            cell.paragraphs[0].runs[0].bold = True
        for i, s in enumerate(submissions, start=1):
            participant = s.full_name + (f"\nСоавтор: {s.coauthor}" if s.coauthor else "")
            supervisor = s.supervisor + (f"\n{s.supervisor2}" if s.supervisor2 else "")
            values = [str(i), participant, str(s.grade), s.school, supervisor, s.title]
            for cell, text in zip(table.add_row().cells, values):
                cell.text = text
        for row in table.rows:
            for cell, width in zip(row.cells, widths):
                cell.width = width
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


class _Sink:
    """Приёмник для zipfile: копит записанное, отдаём кусками по мере готовности."""

    def __init__(self):
        self.chunks = []
        self.position = 0

    def write(self, data):
        self.chunks.append(bytes(data))
        self.position += len(data)
        return len(data)

    def tell(self):
        return self.position

    def flush(self):
        pass

    def take(self):
        data = b"".join(self.chunks)
        self.chunks.clear()
        return data


def stream_archive(groups):
    """ZIP по частям, без сборки целиком в памяти: папка на секцию с работами и общий список.

    Работы и так сжаты (docx, pdf), поэтому файлы кладутся без сжатия — архив собирается быстро.
    """
    sink = _Sink()
    missing = []
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        zf.writestr("Список работ.xlsx", build_reviewer_workbook(groups))
        yield sink.take()
        for section, number in groups:
            folder = _clean_name(section.group_label(number), 90)
            for s in group_submissions(section, number):
                name = f"{folder}/{work_filename(s)}"
                try:
                    source = s.file.open("rb")
                except (OSError, ValueError):
                    missing.append(f"{s.number} {s.full_name}")
                    continue
                with source, zf.open(name, "w", force_zip64=True) as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        target.write(chunk)
                        yield sink.take()
                yield sink.take()
        if missing:
            zf.writestr("Не найдены файлы.txt", "Файлы этих работ не найдены на сервере:\n" + "\n".join(missing))
    yield sink.take()


def archive_filename(groups):
    if len(groups) == 1:
        section, number = groups[0]
        return f"Эврика — {_clean_name(section.group_label(number), 90)}.zip"
    return f"Эврика — все работы {timezone.localdate():%d.%m.%Y}.zip"

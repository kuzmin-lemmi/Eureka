"""Выгрузки для оргкомитета: Excel, Word и архив с работами.

groups — список (направление, номер секции); None — все секции всех направлений.
Отклонённые заявки никуда не попадают. СНИЛС не выгружается: файлы пересылают по почте.
"""

import re
import zipfile
from io import BytesIO
from pathlib import Path

from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from docx import Document
from docx.enum.section import WD_ORIENT
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
    conf_title = ConferenceSettings.load().official_title
    for section, number in groups:
        submissions = group_submissions(section, number)
        label = section.group_label(number)
        people = sum(s.people for s in submissions)
        summary.append([section.name, label, len(submissions), people, section.capacity])

        ws = wb.create_sheet(_sheet_title(section.name, number, section.groups, used))
        ws.append([label])
        ws["A1"].font = TITLE_FONT
        ws.append([f"{conf_title}. Работ: {len(submissions)} из {section.capacity}, участников: {people}"])
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


FONT_DIR = Path(__file__).resolve().parent / "fonts"


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

    conf_title = ConferenceSettings.load().official_title
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


def archive_response(groups):
    response = StreamingHttpResponse(stream_archive(groups), content_type="application/zip")
    response["Content-Disposition"] = content_disposition_header(True, archive_filename(groups))
    return response

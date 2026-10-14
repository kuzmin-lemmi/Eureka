"""Выгрузка сформированных секций в Excel: сводка и по листу на каждую секцию."""

import re
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Section, Submission

HEADER_FILL = PatternFill("solid", fgColor="FFF3B0")
TITLE_FONT = Font(bold=True, size=14)
BOLD = Font(bold=True)

# (заголовок, ширина колонки, значение из заявки). СНИЛС в выгрузку не попадает: файл пересылают по почте.
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
    ("Почта для ссылок", 26, lambda s: s.links_email),
    ("Статус", 13, lambda s: s.public_status),
    ("Подана", 17, lambda s: timezone.localtime(s.created_at).strftime("%d.%m.%Y %H:%M")),
]


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


def build_sections_workbook():
    """Возвращает xlsx (bytes). Отклонённые заявки не включаются."""
    wb = Workbook()
    summary = wb.active
    summary.title = "Сводка"
    summary.append(["Направление", "Секция", "Работ", "Участников", "Мест в секции"])
    for cell in summary[1]:
        cell.font, cell.fill = BOLD, HEADER_FILL
    for letter, width in zip("ABCDE", (55, 60, 9, 13, 15)):
        summary.column_dimensions[letter].width = width

    used = {"Сводка"}
    active = Submission.objects.exclude(status=Submission.Status.REJECTED).select_related("section")
    for section in Section.objects.all():
        rows = active.filter(section=section).order_by("section_number", "last_name", "first_name")
        for number in range(1, section.groups + 1):
            group = [s for s in rows if s.section_number == number]
            label = section.group_label(number)
            people = sum(s.people for s in group)
            summary.append([section.name, label, len(group), people, section.capacity])

            ws = wb.create_sheet(_sheet_title(section.name, number, section.groups, used))
            ws.append([label])
            ws["A1"].font = TITLE_FONT
            ws.append([f"Работ: {len(group)}, участников: {people} из {section.capacity}"])
            ws.append([title for title, *_ in COLUMNS])
            for cell in ws[3]:
                cell.font, cell.fill = BOLD, HEADER_FILL
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            for i, submission in enumerate(group, start=1):
                ws.append([i if get is None else get(submission) for _, _, get in COLUMNS])
            for col, (_, width, _) in enumerate(COLUMNS, start=1):
                ws.column_dimensions[get_column_letter(col)].width = width
            for row in ws.iter_rows(min_row=4):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.freeze_panes = "C4"
            if group:
                ws.auto_filter.ref = f"A3:{get_column_letter(len(COLUMNS))}{ws.max_row}"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

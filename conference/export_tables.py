"""Таблицы учеников для оргкомитета: общий движок «своей выгрузки» и готовые выгрузки этапов 1–3.

Выгрузка описывается Spec: какие поля, какие секции, какие работы (допуск, итог), строка на ученика или на работу.
Этапы — это просто заранее заполненные Spec (PRESETS); своя выгрузка собирается из формы в кабинете.
СНИЛС не выгружается: файлы пересылают по почте.
"""

from dataclasses import dataclass, field
from io import BytesIO

from django.utils import timezone
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from .exports import BOLD, FONT_DIR, HEADER_FILL, TITLE_FONT, _save, all_groups, group_submissions
from .models import AWARD_ORDER, PLACES, ConferenceSettings, Submission

PAGE_CM = 26.7  # ширина альбомной страницы A4 за вычетом полей
FORMATS = {"word": "Word", "excel": "Excel", "pdf": "PDF"}


def _authors(s):
    return s.full_name + (f",\n{s.coauthor_last_name} {s.coauthor_first_name}" if s.coauthor_last_name else "")


def _supervisors(s):
    return s.supervisor + (f"\n{s.supervisor2}" if s.supervisor2 else "")


# ключ: (название столбца, ширина в Excel, значение из заявки). number, name и grade собирает сам движок.
FIELDS = {
    "number": ("№ п/п", 5, None),
    "app_number": ("Номер заявки", 10, lambda s: s.number),
    "section": ("Секция", 28, lambda s: s.section_label),
    "name": ("ФИО", 28, lambda s: s.full_name),
    "authors": ("ФИО (все авторы)", 28, _authors),
    "grade": ("Класс", 7, lambda s: s.grade),
    "grades": ("Класс", 7, lambda s: f"{s.grade}\n{s.coauthor_grade}" if s.coauthor_last_name else s.grade),
    "coauthor": ("Соавтор", 28, lambda s: s.coauthor),
    "school": ("Образовательная организация", 45, lambda s: s.school),
    "district": ("Муниципальный район", 24, lambda s: s.district),
    "title": ("Название работы", 45, lambda s: s.title),
    "supervisor": ("Руководитель", 26, _supervisors),
    "supervisor_position": ("Должность руководителя", 24, lambda s: s.supervisor_position),
    "supervisor_phone": ("Телефон руководителя", 18, lambda s: s.supervisor_phone),
    "supervisor2": ("Второй руководитель", 26, lambda s: s.supervisor2),
    "email": ("Почта участника", 26, lambda s: s.email),
    "created": ("Дата подачи", 12, lambda s: f"{timezone.localtime(s.created_at):%d.%m.%Y}"),
    "contact": ("Дата подачи, e-mail", 28, lambda s: f"{timezone.localtime(s.created_at):%d.%m.%Y}\n{s.email}"),
    "admission": ("Допуск ко 2 этапу", 16, lambda s: s.get_admission_display()),
    "award": ("Итог", 26, lambda s: s.get_award_display() if s.award else ""),
    "snils": ("СНИЛС", 18, lambda s: s.snils),
    "coauthor_snils": ("СНИЛС соавтора", 18, lambda s: s.coauthor_snils),
    "snils_all": ("СНИЛС", 18, lambda s: s.snils + (f"\n{s.coauthor_snils}" if s.coauthor_last_name else "")),
}
# Поля, которые можно отметить в форме «своей выгрузки», и что отмечено сразу.
CUSTOM_FIELD_ORDER = [
    "number", "app_number", "section", "name", "snils", "grade", "coauthor", "coauthor_snils", "school", "district", "title", "supervisor",
    "supervisor_position", "supervisor_phone", "supervisor2", "email", "created", "admission", "award",
]
CUSTOM_DEFAULTS = {"number", "section", "name", "grade", "school", "title", "supervisor"}
CUSTOM_FIELDS = [(key, FIELDS[key][0], key in CUSTOM_DEFAULTS) for key in CUSTOM_FIELD_ORDER]
ALL_ADMISSIONS = tuple(Submission.Admission.values)


@dataclass
class Spec:
    fields: list
    groups: list | None = None  # None — все секции
    admissions: tuple = ALL_ADMISSIONS
    per_student: bool = False  # строка на ученика (соавтор отдельной строкой), иначе на работу
    sort: str = "order"  # order — как в кабинете, alpha — секции по алфавиту, award — по алфавиту и местам
    only_awarded: bool = False
    awards: tuple | None = None  # только эти итоги (места/номинации); None — без отбора
    title: str = ""
    subtitle: str = ""
    count_label: str = ""  # «Учеников» — в Word под заголовком выводится «Учеников: N»
    sheet: str = "Выгрузка"
    excel_title: str | None = None  # заголовок листа Excel; None — тот же, что title
    labels: dict = field(default_factory=dict)  # свои названия столбцов
    cm_widths: list | None = None  # ширины для Word/PDF; иначе пропорционально Excel


def select_submissions(spec):
    groups = list(all_groups() if spec.groups is None else spec.groups)
    if spec.sort in ("alpha", "award"):
        groups.sort(key=lambda g: g[0].group_label(g[1]).casefold())
    works = []
    for section, number in groups:
        works += [
            s for s in group_submissions(section, number)
            if s.admission in spec.admissions and (s.award or not spec.only_awarded)
            and (spec.awards is None or s.award in spec.awards)
        ]
    if spec.sort == "award":
        works.sort(key=lambda s: (s.section_label.casefold(), AWARD_ORDER.index(s.award), s.last_name, s.pk))
    return works


def build_rows(spec, works):
    rows = []
    for s in works:
        people = [(s.full_name, s.grade, s.snils)]
        if spec.per_student and s.coauthor_last_name:
            people.append((f"{s.coauthor_last_name} {s.coauthor_first_name}", s.coauthor_grade, s.coauthor_snils))
        for name, grade, snils in people:
            row = []
            for key in spec.fields:
                get = FIELDS[key][2]
                if key == "number":
                    row.append(len(rows) + 1)
                elif key == "name":
                    row.append(name)
                elif key == "grade":
                    row.append(grade)
                elif key == "snils":
                    row.append(snils)
                elif key in ("coauthor", "coauthor_snils") and spec.per_student:
                    row.append("")  # соавтор и так отдельной строкой, со своим СНИЛС
                else:
                    row.append(get(s))
            rows.append(row)
    return rows


def build(spec, fmt):
    """Файл выгрузки: fmt — word, excel или pdf."""
    rows = build_rows(spec, select_submissions(spec))
    headers = [spec.labels.get(key, FIELDS[key][0]) for key in spec.fields]
    widths = [FIELDS[key][1] for key in spec.fields]
    cm = spec.cm_widths or [w / sum(widths) * PAGE_CM for w in widths]
    title = spec.title or "Выгрузка"
    if fmt == "excel":
        sheet_title = spec.title if spec.excel_title is None else spec.excel_title
        return _table_workbook(spec.sheet, headers, widths, rows, title=sheet_title or None)
    if fmt == "word":
        note = f"{spec.count_label}: {len(rows)}" if spec.count_label else None
        return _table_docx(title, headers, cm, rows, note=note, subtitle=spec.subtitle or None)
    return _table_pdf(title, headers, cm, rows)


# ---------- готовые выгрузки этапов ----------

STUDENT_LABELS = {"number": "№", "grade": "Кл.", "school": "ОУ"}


def students_spec():
    official = ConferenceSettings.load().official_title
    return Spec(
        # Строка на работу: соавтор в той же ячейке ФИО, его класс под классом автора.
        fields=["number", "section", "authors", "grades", "school", "title", "supervisor", "contact"],
        title="Список учеников по секциям", subtitle=official,
        excel_title=f"Список учеников по секциям. {official}",
        count_label="Работ", sheet="Все ученики", labels={**STUDENT_LABELS, "authors": "ФИО", "grades": "Кл."},
        cm_widths=[1, 3.6, 3.6, 1, 5.5, 5.5, 3.6, 3.6],
    )


def admitted_title():
    conf = ConferenceSettings.load()
    return f"Список участников, допущенных ко 2 этапу {conf.full_name} школьников «Эврика» в {conf.year} году"


def admitted_spec():
    return Spec(
        fields=["number", "section", "authors", "grades", "school", "title", "supervisor"],
        admissions=(Submission.Admission.ADMITTED,), sort="alpha",
        title=admitted_title(), sheet="Допущенные", labels={**STUDENT_LABELS, "authors": "ФИО", "grades": "Кл."},
        cm_widths=[1, 3.6, 3.8, 1, 6.2, 6.2, 4],
    )


def winners_title():
    return f"Победители и призеры {ConferenceSettings.load().full_name} «Эврика»"


def winners_spec():
    # По образцу списка оргкомитета: строка на работу, соавторы в одной ячейке.
    return Spec(
        fields=["number", "authors", "title", "section", "school", "award"],
        sort="award", only_awarded=True, title=winners_title(), sheet="Победители и призёры",
        labels={"number": "№", "authors": "ФИО", "school": "ОУ", "award": "Статус"},
        cm_widths=[1, 4, 5.5, 4, 7.5, 4.5],
    )


def places_spec():
    # Этап 4: только места 1–3, строка на работу; СНИЛС автора и соавтора в одной ячейке, в том же порядке, что ФИО.
    return Spec(
        fields=["number", "authors", "title", "section", "school", "award", "snils_all"],
        sort="award", awards=tuple(value for value, _ in PLACES),
        title=winners_title(), sheet="Призёры",
        labels={"number": "№", "authors": "ФИО", "school": "ОУ", "award": "Статус"},
        cm_widths=[1, 4, 5.5, 4, 6.5, 2.5, 3.2],
    )


@dataclass(frozen=True)
class Preset:
    slug: str
    stage: int
    heading: str
    text: str
    filename: str  # часть имени скачиваемого файла
    spec: object


PRESETS = {
    p.slug: p
    for p in (
        Preset(
            "students", 1, "Все ученики по секциям",
            "Каждая работа отдельной строкой (соавтор в той же строке): секция, ФИО, класс, школа, работа, руководитель, дата и почта.",
            "все ученики по секциям", students_spec,
        ),
        Preset(
            "admitted", 2, "Допущенные ко 2 этапу",
            "Допущенные работы, секции по алфавиту; соавтор в одной строке с автором. Допуск отмечают на странице секции после закрытия приёма.",
            "допущенные ко 2 этапу", admitted_spec,
        ),
        Preset(
            "winners", 3, "Победители и призёры",
            "Места 1–3 и номинации по итогам конференции. Ставят на странице секции в столбце «Итог».",
            "победители и призёры", winners_spec,
        ),
        Preset(
            "places", 4, "Призёры 1–3 места со СНИЛС",
            "Только работы, занявшие 1, 2 и 3 места (без номинаций): авторы и их СНИЛС в одной строке.",
            "призёры 1-3 места со СНИЛС", places_spec,
        ),
    )
}


# ---------- писатели файлов ----------

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

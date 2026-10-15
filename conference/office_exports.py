"""Выгрузки в кабинете оргкомитета: списки секций, архив работ, выгрузки этапов и «своя выгрузка»."""

from io import BytesIO

from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from . import export_tables, exports
from .models import Submission
from .office import _group_or_404, office_required

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CONTENT_TYPES = {"word": DOCX, "excel": XLSX, "pdf": "application/pdf"}
EXTENSIONS = {"word": "docx", "excel": "xlsx", "pdf": "pdf"}
ADMISSION_VALUES = {
    "admitted": Submission.Admission.ADMITTED,
    "not_admitted": Submission.Admission.NOT_ADMITTED,
    "pending": Submission.Admission.PENDING,
}


def _file(data, filename, content_type):
    return FileResponse(BytesIO(data), as_attachment=True, filename=filename, content_type=content_type)


def _today():
    return f"{timezone.localdate():%d.%m.%Y}"


def _groups(pk=None, number=None):
    if pk is None:
        return exports.all_groups()
    return [(_group_or_404(pk, number), number)]


def _title(groups):
    return exports._clean_name(groups[0][0].group_label(groups[0][1]), 90) if len(groups) == 1 else "все секции"


@office_required
def export_word(request, pk=None, number=None):
    groups = _groups(pk, number)
    return _file(exports.build_sections_docx(groups), f"Эврика — {_title(groups)} {_today()}.docx", DOCX)


@office_required
def export_excel(request, pk=None, number=None):
    groups = _groups(pk, number)
    return _file(exports.build_sections_workbook(groups), f"Эврика — {_title(groups)} {_today()}.xlsx", XLSX)


@office_required
def export_participants(request):
    return _file(exports.build_participants_workbook(), f"Эврика — все участники {_today()}.xlsx", XLSX)


@office_required
def export_archive(request, pk=None, number=None):
    return exports.archive_response(_groups(pk, number))


@office_required
def export_preset(request, slug, fmt):
    """Выгрузка этапа (students, admitted, winners) в формате word, excel или pdf."""
    preset = export_tables.PRESETS[slug]
    data = export_tables.build(preset.spec(), fmt)
    return _file(data, f"Эврика — {preset.filename} {_today()}.{EXTENSIONS[fmt]}", CONTENT_TYPES[fmt])


@office_required
def export_custom(request):
    """Настраиваемая выгрузка: поля, секции, допуск, строка на работу или на ученика, формат."""
    params = request.GET
    fmt = params.get("format", "excel")
    keys = [k for k in export_tables.CUSTOM_FIELD_ORDER if k in params.getlist("field")]  # порядок столбцов фиксирован
    admissions = tuple(ADMISSION_VALUES[k] for k in params.getlist("admission") if k in ADMISSION_VALUES)
    chosen = set(params.getlist("group"))
    groups = [(s, n) for s, n in exports.all_groups() if f"{s.pk}:{n}" in chosen]
    problem = None
    if fmt not in CONTENT_TYPES:
        problem = "Выберите формат файла."
    elif not keys:
        problem = "Отметьте хотя бы одно поле."
    elif not groups:
        problem = "Отметьте хотя бы одну секцию."
    elif not admissions:
        problem = "Отметьте, какие работы включить: допущенные, не допущенные или не рассмотренные."
    if problem:
        messages.error(request, problem)
        return redirect(f"{reverse('conference:office')}#custom-export")
    spec = export_tables.Spec(
        fields=keys, groups=groups, admissions=admissions, per_student=params.get("rows") == "student",
        sort="alpha" if params.get("sort") == "alpha" else "order", title=params.get("title", "").strip()[:200],
        count_label="Строк",
    )
    return _file(export_tables.build(spec, fmt), f"Эврика — выгрузка {_today()}.{EXTENSIONS[fmt]}", CONTENT_TYPES[fmt])

"""Кабинет: поиск заявки (по СНИЛС, фамилии, номеру), правка данных и перенос в другую секцию."""

import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import OFFICE_SUBMISSION_FIELDSETS, SUBMISSION_FILE_FIELDS, MoveSubmissionForm, OfficeSubmissionForm
from .models import Submission
from .office import office_required

SEARCH_LIMIT = 50


def find_submissions(query):
    """СНИЛС (11 цифр, с дефисами или без) — участник или соавтор; до 6 цифр — номер заявки;
    иначе — часть фамилии или имени участника или соавтора."""
    query = query.strip()
    digits = re.sub(r"\D", "", query)
    submissions = Submission.objects.select_related("section")
    if len(digits) == 11 and not re.search(r"[^\d\s\-]", query):
        snils = f"{digits[:3]}-{digits[3:6]}-{digits[6:9]} {digits[9:]}"
        return list(submissions.filter(snils=snils)) + list(submissions.filter(coauthor_snils=snils).exclude(snils=snils))
    if digits and digits == query.lstrip("№ ").strip() and len(digits) <= 6:
        return list(submissions.filter(pk=int(digits)))
    # SQLite не умеет сравнивать кириллицу без учёта регистра — ищем в Python, заявок немного.
    needle = query.casefold()
    found = [
        s for s in submissions.order_by("last_name", "first_name", "pk")
        if any(needle in value.casefold() for value in (
            s.last_name, s.first_name, f"{s.last_name} {s.first_name}", s.coauthor_last_name, s.coauthor_first_name,
        ))
    ]
    return found[:SEARCH_LIMIT]


@office_required
def search(request):
    query = request.GET.get("q", "").strip()
    results = find_submissions(query) if len(query) >= 2 or query.isdigit() else []  # номер заявки бывает «7»
    return render(request, "conference/office/search.html", {"query": query, "results": results})


@office_required
def submission_edit(request, pk):
    if not request.user.has_perm("conference.change_submission"):
        raise PermissionDenied
    submission = get_object_or_404(Submission.objects.select_related("section"), pk=pk)
    is_move = request.POST.get("action") == "move"
    move_form = MoveSubmissionForm(request.POST if is_move else None, submission=submission)
    form = OfficeSubmissionForm(
        request.POST if request.method == "POST" and not is_move else None,
        request.FILES if request.method == "POST" and not is_move else None,
        instance=submission,
    )
    url = reverse("conference:office_submission", args=[pk])

    if is_move and move_form.is_valid():
        section, number = move_form.cleaned_data["slot"]
        old_label = submission.section_label
        with transaction.atomic():
            submission.section, submission.section_number = section, number
            submission.save(update_fields=["section", "section_number", "updated_at"])
        taken = section.occupied().get(number, 0)
        messages.success(request, f"Работа перенесена: {old_label} → {submission.section_label}.")
        if taken > section.capacity:
            messages.warning(request, f"В секции «{submission.section_label}» теперь {taken} работ при {section.capacity} местах.")
        return redirect(url)

    if request.method == "POST" and not is_move and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error("snils", "У участника с этим СНИЛС уже есть работа в этом направлении.")
        else:
            messages.success(request, "Данные заявки сохранены.")
            return redirect(url)

    def download_url(name):
        if name in SUBMISSION_FILE_FIELDS and getattr(submission, name):
            return reverse("conference:download_submission_file", args=[pk, SUBMISSION_FILE_FIELDS[name][1]])
        return None

    fieldsets = [
        (title, [(form[name], download_url(name)) for name in names]) for title, names in OFFICE_SUBMISSION_FIELDSETS
    ]
    return render(request, "conference/office/submission.html", {
        "submission": submission, "form": form, "move_form": move_form, "fieldsets": fieldsets,
        "section_url": reverse("conference:office_section", args=[submission.section_id, submission.section_number]),
    })

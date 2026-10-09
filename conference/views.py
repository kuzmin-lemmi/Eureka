from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import REPEAT_FIELDS, SubmissionForm
from .models import ConferenceSettings, Section, Submission

THANKS_SESSION_KEY = "conference_thanks"
REPEAT_SESSION_KEY = "conference_repeat"

# kind в URL → (поле файла, поле исходного имени, подпись в имени скачанного файла)
SUBMISSION_FILES = {
    "work": ("file", "original_filename", None),
    "application": ("application_file", "application_original_filename", "заявка"),
    "consent": ("consent_file", "consent_original_filename", "согласие"),
}
BLANKS = {
    "application": ("application_template", "Бланк заявки — Эврика"),
    "consent": ("consent_template", "Согласие на обработку ПДн — Эврика"),
}


def home(request):
    return render(request, "conference/home.html", {"sections": Section.objects.filter(is_active=True)})


@require_http_methods(["GET", "POST"])
def submit(request):
    if not ConferenceSettings.load().is_submission_open:
        return render(request, "conference/submit.html", {"closed": True})

    # «Подать ещё одну работу»: школа и руководитель подставляются из прошлой заявки.
    initial = request.session.get(REPEAT_SESSION_KEY, {}) if "more" in request.GET else {}
    form = SubmissionForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        if form.is_spam:
            return redirect("conference:thanks")
        submission = form.save()
        request.session[THANKS_SESSION_KEY] = {
            "number": submission.number,
            "email": submission.email,
            "links_email": submission.links_email,
        }
        request.session[REPEAT_SESSION_KEY] = {name: form.cleaned_data[name] for name in REPEAT_FIELDS}
        return redirect("conference:thanks")
    return render(request, "conference/submit.html", {"form": form, "repeat": bool(initial)})


def thanks(request):
    # Не удаляем из сессии, чтобы номер не пропадал при обновлении страницы.
    return render(request, "conference/thanks.html", {"application": request.session.get(THANKS_SESSION_KEY)})


def privacy(request):
    return render(request, "conference/privacy.html")


def blank(request, kind):
    """Пустой бланк документа — открыт всем, его скачивают участники."""
    if kind not in BLANKS:
        raise Http404
    field_name, title = BLANKS[kind]
    file = getattr(ConferenceSettings.load(), field_name)
    if not file or not file.storage.exists(file.name):
        raise Http404("Бланк не загружен")
    return FileResponse(file.open("rb"), as_attachment=True, filename=f"{title}{Path(file.name).suffix}")


@staff_member_required
def download_submission(request, pk, kind="work"):
    if kind not in SUBMISSION_FILES:
        raise Http404
    file_field, original_field, label = SUBMISSION_FILES[kind]
    submission = get_object_or_404(Submission, pk=pk)
    file = getattr(submission, file_field)
    if not file or not file.storage.exists(file.name):
        raise Http404("Файл не найден")
    original = getattr(submission, original_field) or file.name
    if label:
        filename = f"{submission.pk:04d}_{submission.last_name}_{label}{Path(original).suffix.lower()}"
    else:
        filename = f"{submission.pk:04d}_{submission.last_name}_{original}"
    return FileResponse(file.open("rb"), as_attachment=True, filename=filename)

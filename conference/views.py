from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import SubmissionForm
from .models import ConferenceSettings, Section, Submission

THANKS_SESSION_KEY = "conference_thanks"


def home(request):
    return render(request, "conference/home.html", {"sections": Section.objects.filter(is_active=True)})


@require_http_methods(["GET", "POST"])
def submit(request):
    if not ConferenceSettings.load().is_submission_open:
        return render(request, "conference/submit.html", {"closed": True})

    form = SubmissionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        if form.is_spam:
            return redirect("conference:thanks")
        submission = form.save()
        request.session[THANKS_SESSION_KEY] = {"number": submission.number, "email": submission.email}
        return redirect("conference:thanks")
    return render(request, "conference/submit.html", {"form": form})


def thanks(request):
    # Не удаляем из сессии, чтобы номер не пропадал при обновлении страницы.
    return render(request, "conference/thanks.html", {"application": request.session.get(THANKS_SESSION_KEY)})


def privacy(request):
    return render(request, "conference/privacy.html")


@staff_member_required
def download_submission(request, pk):
    submission = get_object_or_404(Submission, pk=pk)
    if not submission.file or not submission.file.storage.exists(submission.file.name):
        raise Http404("Файл не найден")
    filename = f"{submission.pk:04d}_{submission.last_name}_{submission.original_filename or submission.file.name}"
    return FileResponse(submission.file.open("rb"), as_attachment=True, filename=filename)

from datetime import datetime, timedelta
from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.db import IntegrityError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import REPEAT_FIELDS, LookupForm, SectionFull, SubmissionForm, duplicate_message
from .models import ConferenceSettings, Document, NewsPost, Section, Submission

THANKS_SESSION_KEY = "conference_thanks"
FRESH_NEWS_DAYS = 7
REPEAT_SESSION_KEY = "conference_repeat"
# «Мои заявки»: после входа по СНИЛС и почте доступ хранится в сессии ограниченное время.
MY_SESSION_KEY = "conference_my"
MY_SESSION_TTL = timedelta(hours=2)
# Не больше LOOKUP_LIMIT неудачных попыток входа за LOOKUP_WINDOW секунд — с одного адреса и на один СНИЛС.
LOOKUP_LIMIT = 10
LOOKUP_WINDOW = 15 * 60

# kind в URL → (поле файла, поле исходного имени, подпись в имени скачанного файла)
SUBMISSION_FILES = {
    "work": ("file", "original_filename", None),
    "application": ("application_file", "application_original_filename", "заявка"),
    "consent": ("consent_file", "consent_original_filename", "согласие"),
}
BLANKS = {
    "application": ("application_pdf", "Заявка на участие — Эврика"),
    "application-word": ("application_template", "Заявка на участие — Эврика"),
    "consent": ("consent_pdf", "Согласие родителя — Эврика"),
    "consent-word": ("consent_template", "Согласие родителя — Эврика"),
    "requirements": ("requirements_template", "Требования к работе — Эврика"),
}
# Бланки в блоке «Документы» на главной: (вид, название, пояснение).
BLANK_LISTING = (
    ("application", "Заявка на участие", "Заполнить, подписать и приложить скан в анкете"),
    ("consent", "Согласие родителя (законного представителя)", "Подписывает родитель, скан прикладывается к анкете"),
    ("requirements", "Требования к работе", "Объём, структура и оформление работы"),
)


def _blank_items(conf):
    items = []
    for kind, title, description in BLANK_LISTING:
        files = []
        for label, link_kind in getattr(conf, f"{kind}_links"):
            file = getattr(conf, BLANKS[link_kind][0])
            if file.storage.exists(file.name):
                files.append({"label": label, "kind": link_kind, "size": file.size})
        if files:
            items.append({"title": title, "description": description, "files": files})
    return items


def home(request):
    sections = list(Section.objects.filter(is_active=True))
    for section in sections:
        section.free_total = sum(section.free_places().values())
    news = list(NewsPost.visible())
    context = {
        "sections": sections,
        "news": news,
        # Свежая новость (до FRESH_NEWS_DAYS дней) дублируется плашкой под первым экраном.
        "fresh_news": news[0] if news and news[0].published_at >= timezone.now() - timedelta(days=FRESH_NEWS_DAYS) else None,
        "documents": Document.objects.filter(is_published=True),
        "blanks": _blank_items(ConferenceSettings.load()),
    }
    return render(request, "conference/home.html", context)


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
        try:
            submission = form.save()
        except IntegrityError:
            # Две одинаковые анкеты отправили одновременно — вторую не пропустило ограничение в базе.
            form.add_error("section_slot", duplicate_message(form.instance.section))
            return render(request, "conference/submit.html", {"form": form})
        except SectionFull:
            # Пересчитываем свободные места: проверка формы сама отметит занятую секцию.
            form = SubmissionForm(request.POST, request.FILES)
            if form.is_valid() or "section_slot" not in form.errors:
                form.add_error("section_slot", "Пока вы заполняли анкету, эту секцию заняли. Выберите другую.")
            return render(request, "conference/submit.html", {"form": form})
        request.session[THANKS_SESSION_KEY] = {
            "number": submission.number,
            "email": submission.email,
            "links_email": submission.links_email,
        }
        request.session[REPEAT_SESSION_KEY] = {name: form.cleaned_data[name] for name in REPEAT_FIELDS}
        _remember_participant(request, submission.snils, submission.email)
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


def news_redirect(request):
    return redirect(reverse("conference:home") + "#news")


def documents_redirect(request):
    return redirect(reverse("conference:home") + "#documents")


def download_document(request, pk):
    """Опубликованные документы открыты всем; файлы не раздаются через MEDIA_URL напрямую."""
    document = get_object_or_404(Document, pk=pk, is_published=True)
    if not document.file or not document.file.storage.exists(document.file.name):
        raise Http404("Файл не найден")
    filename = f"{document.title}{Path(document.file.name).suffix}"
    return FileResponse(document.file.open("rb"), as_attachment=True, filename=filename)


# --- «Мои заявки»: просмотр и редактирование своих заявок по СНИЛС и почте ---


def _remember_participant(request, snils, email):
    request.session[MY_SESSION_KEY] = {"snils": snils, "email": email.lower(), "at": timezone.now().isoformat()}


def _participant(request):
    """(СНИЛС, почта) вошедшего участника или None, если вход не выполнен или устарел."""
    data = request.session.get(MY_SESSION_KEY)
    if not data:
        return None
    try:
        at = datetime.fromisoformat(data["at"])
    except (KeyError, ValueError):
        return None
    if timezone.now() - at > MY_SESSION_TTL:
        request.session.pop(MY_SESSION_KEY, None)
        return None
    return data["snils"], data["email"]


def _my_submissions(participant):
    snils, email = participant
    return Submission.objects.filter(snils=snils, email__iexact=email).select_related("section")


def _lookup_keys(request, snils):
    ip = request.META.get("REMOTE_ADDR", "unknown")
    return [f"my-lookup:ip:{ip}", f"my-lookup:snils:{snils}"]


@require_http_methods(["GET", "POST"])
def my(request):
    participant = _participant(request)
    if participant and request.method == "GET":
        return render(request, "conference/my.html", {"submissions": _my_submissions(participant)})

    form = LookupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        snils, email = form.cleaned_data["snils"], form.cleaned_data["email"].lower()
        keys = _lookup_keys(request, snils)
        if any(cache.get(key, 0) >= LOOKUP_LIMIT for key in keys):
            form.add_error(None, "Слишком много попыток. Подождите 15 минут и попробуйте снова.")
        elif _my_submissions((snils, email)).exists():
            _remember_participant(request, snils, email)
            return redirect("conference:my")
        else:
            for key in keys:
                cache.add(key, 0, LOOKUP_WINDOW)
                cache.incr(key)
            form.add_error(
                None,
                "Заявки не найдены. Проверьте СНИЛС и почту: почта должна совпадать с почтой участника из анкеты.",
            )
    return render(request, "conference/my.html", {"form": form})


@require_http_methods(["POST"])
def my_logout(request):
    request.session.pop(MY_SESSION_KEY, None)
    return redirect("conference:my")


@require_http_methods(["GET", "POST"])
def my_edit(request, pk):
    participant = _participant(request)
    if not participant:
        return redirect("conference:my")
    submission = get_object_or_404(_my_submissions(participant), pk=pk)
    if not submission.is_editable:
        messages.info(request, f"Заявку {submission.number} изменить уже нельзя.")
        return redirect("conference:my")

    form = SubmissionForm(request.POST or None, request.FILES or None, instance=submission)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error("section_slot", duplicate_message(form.instance.section))
        except SectionFull:
            form = SubmissionForm(request.POST, request.FILES, instance=Submission.objects.get(pk=pk))
            if form.is_valid() or "section_slot" not in form.errors:
                form.add_error("section_slot", "Пока вы редактировали заявку, эту секцию заняли. Выберите другую.")
        else:
            # СНИЛС или почту могли поменять — входим заново с новыми данными.
            _remember_participant(request, form.instance.snils, form.instance.email)
            messages.success(request, f"Изменения в заявке {form.instance.number} сохранены.")
            return redirect("conference:my")
    return render(request, "conference/submit.html", {"form": form, "editing": submission})

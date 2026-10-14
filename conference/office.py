"""Кабинет оргкомитета: простой интерфейс для сотрудников, которые редко работают за компьютером.

Учётные записи — обычные пользователи Django со «Статусом персонала» и правом смотреть заявки
(например, группа «Оргкомитет»). Расширенные настройки — по-прежнему в /admin/.
"""

from functools import wraps
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST

from . import exports
from .models import ConferenceSettings, ReviewLink, Section, Submission

LOGIN_LIMIT = 10
LOGIN_WINDOW = 15 * 60
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


# --- Вход ---


class OfficeLoginForm(AuthenticationForm):
    """Вход с ограничением неудачных попыток: не больше LOGIN_LIMIT за LOGIN_WINDOW с адреса и на логин."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Неверный логин или пароль. Проверьте раскладку клавиатуры и Caps Lock.",
        "inactive": "Эта учётная запись отключена. Обратитесь к администратору сайта.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Логин"
        self.fields["password"].label = "Пароль"
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autocapitalize": "none"})

    def _keys(self):
        ip = self.request.META.get("REMOTE_ADDR", "unknown") if self.request else "unknown"
        username = (self.data.get("username") or "").strip().lower()
        return [f"office-login:ip:{ip}", f"office-login:user:{username}"]

    def clean(self):
        keys = self._keys()
        if any(cache.get(key, 0) >= LOGIN_LIMIT for key in keys):
            raise ValidationError("Слишком много неудачных попыток. Подождите 15 минут и попробуйте снова.")
        try:
            cleaned = super().clean()
        except ValidationError:
            for key in keys:
                cache.add(key, 0, LOGIN_WINDOW)
                cache.incr(key)
            raise
        user = self.get_user()
        if user and not _can_use_office(user):
            raise ValidationError(
                "У этой учётной записи нет доступа к кабинету оргкомитета. Обратитесь к администратору сайта."
            )
        return cleaned


class OfficeLoginView(auth_views.LoginView):
    template_name = "conference/office/login.html"
    authentication_form = OfficeLoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return reverse("conference:office")


@require_POST
def office_logout(request):
    logout(request)
    return redirect("conference:home")


def _can_use_office(user):
    return user.is_active and user.is_staff and user.has_perm("conference.view_submission")


def office_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('conference:office_login')}?next={request.path}")
        if not _can_use_office(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


# --- Страницы кабинета ---


def _group_info(section, number, taken):
    count = taken.get(number, 0)
    if count >= section.capacity:
        state, state_label = "full", "Мест нет"
    elif section.capacity - count <= 2:
        state, state_label = "almost", "Почти заполнена"
    else:
        state, state_label = "free", "Есть места"
    return {
        "section": section,
        "number": number,
        "label": section.group_label(number),
        "taken": count,
        "capacity": section.capacity,
        "percent": min(100, round(100 * count / section.capacity)) if section.capacity else 100,
        "state": state,
        "state_label": state_label,
    }


@office_required
def dashboard(request):
    conf = ConferenceSettings.load()
    directions, capacity, taken_total = [], 0, 0
    for section in Section.objects.filter(is_active=True):
        taken = section.occupied()
        groups = [_group_info(section, n, taken) for n in range(1, section.groups + 1)]
        directions.append({
            "section": section,
            "groups": groups,
            "taken": sum(taken.values()),
            "capacity": section.capacity * section.groups,
        })
        capacity += section.capacity * section.groups
        taken_total += sum(taken.values())
    works = Submission.objects.exclude(status=Submission.Status.REJECTED).count()
    days_left = None
    if conf.is_submission_open and conf.submissions_deadline:
        days_left = max(0, (timezone.localdate(conf.submissions_deadline) - timezone.localdate()).days)
    context = {
        "directions": directions,
        "works": works,
        "people": taken_total,
        "free": max(capacity - taken_total, 0),
        "capacity": capacity,
        "days_left": days_left,
    }
    return render(request, "conference/office/dashboard.html", context)


def _group_or_404(pk, number):
    section = get_object_or_404(Section, pk=pk)
    if not 1 <= number <= section.groups:
        raise Http404
    return section


@office_required
def section_detail(request, pk, number):
    section = _group_or_404(pk, number)
    info = _group_info(section, number, section.occupied())
    context = {
        "info": info,
        "submissions": exports.group_submissions(section, number),
        "link": _active_link(section, number),
    }
    return render(request, "conference/office/section.html", context)


# --- Выгрузки ---


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
def export_students_excel(request):
    return _file(exports.build_students_workbook(), f"Эврика — все ученики по секциям {_today()}.xlsx", XLSX)


@office_required
def export_students_word(request):
    return _file(exports.build_students_docx(), f"Эврика — все ученики по секциям {_today()}.docx", DOCX)


def _archive_response(groups):
    response = StreamingHttpResponse(exports.stream_archive(groups), content_type="application/zip")
    response["Content-Disposition"] = content_disposition_header(True, exports.archive_filename(groups))
    return response


@office_required
def export_archive(request, pk=None, number=None):
    return _archive_response(_groups(pk, number))


# --- Ссылки для проверяющих ---


def _active_link(section=None, number=None):
    links = ReviewLink.objects.filter(is_active=True, expires_at__gte=timezone.now())
    if section is None:
        return links.filter(section__isnull=True).first()
    return links.filter(section=section, section_number=number).first()


@office_required
@require_POST
def link_create(request):
    pk, number = request.POST.get("section"), request.POST.get("number")
    if pk:
        section = _group_or_404(int(pk), int(number or 1))
        number = int(number or 1)
    else:
        section, number = None, None
    # Если для этой секции уже есть действующая ссылка — показываем её, а не плодим новые.
    link = _active_link(section, number) or ReviewLink.objects.create(
        section=section, section_number=number, created_by=request.user
    )
    return redirect("conference:office_link", pk=link.pk)


@office_required
def link_detail(request, pk):
    link = get_object_or_404(ReviewLink, pk=pk)
    url = request.build_absolute_uri(reverse("conference:review", args=[link.token]))
    # Кириллический домен показываем по-русски (xn--… → эврика-гимназия87.рф): так понятнее, работает одинаково.
    host = request.get_host()
    try:
        url = url.replace(host, host.encode("ascii").decode("idna"), 1)
    except UnicodeError:
        pass
    return render(request, "conference/office/link.html", {"link": link, "url": url, "links": ReviewLink.objects.all()[:50]})


@office_required
@require_POST
def link_disable(request, pk):
    link = get_object_or_404(ReviewLink, pk=pk)
    link.is_active = False
    link.save(update_fields=["is_active"])
    messages.success(request, f"Ссылка «{link.scope_label}» отключена. Проверяющий больше не сможет по ней скачать работы.")
    return redirect("conference:office_link", pk=link.pk)


# --- Страница проверяющего (без входа) ---


def review(request, token):
    link = ReviewLink.objects.filter(token=token).select_related("section").first()
    if not link or not link.is_valid:
        return render(request, "conference/office/review.html", {"expired": True}, status=410 if link else 404)
    groups = link.groups()
    works = sum(len(exports.group_submissions(s, n)) for s, n in groups)
    context = {"link": link, "works_label": plural(works, "работа", "работы", "работ"), "groups": groups}
    return render(request, "conference/office/review.html", context)


def review_download(request, token):
    link = ReviewLink.objects.filter(token=token).select_related("section").first()
    if not link or not link.is_valid:
        raise Http404
    return _archive_response(link.groups())


# --- Пароли ---


@office_required
def change_password(request):
    """Сотрудник меняет свой пароль: старый, новый, ещё раз новый."""
    form = PasswordChangeForm(request.user, request.POST or None)
    form.fields["old_password"].label = "Старый пароль"
    form.fields["new_password1"].label = "Новый пароль"
    form.fields["new_password2"].label = "Новый пароль ещё раз"
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)  # не выкидывать из кабинета после смены
        messages.success(request, "Пароль изменён. В следующий раз входите с новым паролем.")
        return redirect("conference:office")
    context = {
        "form": form,
        "title": "Сменить пароль",
        "lead": "Сначала введите старый пароль, затем дважды новый.",
        "back": reverse("conference:office"),
    }
    return render(request, "conference/office/password.html", context)


def superuser_required(view):
    @office_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


@superuser_required
def staff_list(request):
    users = get_user_model().objects.filter(is_staff=True).order_by("last_name", "first_name", "username")
    return render(request, "conference/office/staff.html", {"users": users})


@superuser_required
def staff_password(request, pk):
    """Администратор сайта задаёт сотруднику новый пароль, если тот забыл старый."""
    person = get_object_or_404(get_user_model(), pk=pk, is_staff=True)
    form = SetPasswordForm(person, request.POST or None)
    form.fields["new_password1"].label = "Новый пароль"
    form.fields["new_password2"].label = "Новый пароль ещё раз"
    if request.method == "POST" and form.is_valid():
        form.save()
        if person == request.user:
            update_session_auth_hash(request, person)
        name = person.get_full_name() or person.username
        messages.success(request, f"Новый пароль для «{name}» задан. Сообщите его сотруднику лично.")
        return redirect("conference:office_staff")
    name = person.get_full_name() or person.username
    context = {
        "form": form,
        "title": f"Новый пароль: {name}",
        "lead": f"Логин — {person.username}. Старый пароль знать не нужно.",
        "back": reverse("conference:office_staff"),
    }
    return render(request, "conference/office/password.html", context)

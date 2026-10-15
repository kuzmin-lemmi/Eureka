"""Рассылка в кабинете оргкомитета: поздравление допущенных ко 2 этапу."""

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import mailing
from .audit import log_action
from .models import ActionLog, ConferenceSettings
from .office import office_required


def _site(request):
    """Адрес сайта для письма; кириллический домен показываем по-русски, а не xn--…"""
    url = request.build_absolute_uri("/")
    host = request.get_host()
    try:
        return url.replace(host, host.encode("ascii").decode("idna"), 1)
    except UnicodeError:
        return url


def _can_send(request):
    return request.user.has_perm("conference.change_submission")


def _block_reason(conf):
    if conf.is_submission_open:
        return "Рассылка доступна после закрытия приёма работ: пока приём идёт, список допущенных ещё может меняться."
    if not settings.MAIL_CONFIGURED:
        return "Почта на сервере ещё не настроена: администратору нужно указать почтовый ящик отправителя."
    return ""


@office_required
def mailing_page(request):
    conf = ConferenceSettings.load()
    stats = mailing.stats()
    first = mailing.admitted_works().order_by("pk").first()
    subject, body = mailing.render(conf, first, _site(request))
    context = {
        "stats": stats,
        "subject": subject,
        "body": body,
        "form_subject": conf.mail_admitted_subject,
        "form_body": conf.mail_admitted_body,
        "placeholders": mailing.PLACEHOLDERS,
        "sample_is_real": first is not None,
        "block_reason": _block_reason(conf),
        "can_send": _can_send(request),
        "from_address": settings.DEFAULT_FROM_EMAIL,
        "default_test_email": request.user.email,
        "send_url": reverse("conference:office_mailing_send"),
    }
    return render(request, "conference/office/mailing.html", context)


@office_required
@require_POST
def mailing_save(request):
    if not _can_send(request):
        raise PermissionDenied
    subject = request.POST.get("subject", "").strip()
    body = request.POST.get("body", "").strip()
    problem = None
    if not subject or not body:
        problem = "Тема и текст письма не могут быть пустыми."
    else:
        problem = mailing.check_template(subject) or mailing.check_template(body)
    if problem:
        messages.error(request, problem)
    else:
        conf = ConferenceSettings.load()
        conf.mail_admitted_subject, conf.mail_admitted_body = subject, body
        conf.save(update_fields=["mail_admitted_subject", "mail_admitted_body"])
        messages.success(request, "Текст письма сохранён.")
    return redirect("conference:office_mailing")


@office_required
@require_POST
def mailing_test(request):
    """Пробное письмо на указанный адрес: так видно, дойдёт ли оно и как выглядит."""
    if not _can_send(request):
        raise PermissionDenied
    if not settings.MAIL_CONFIGURED:
        messages.error(request, _block_reason(ConferenceSettings.load()))
        return redirect("conference:office_mailing")
    to = request.POST.get("to", "").strip()
    try:
        validate_email(to)
    except ValidationError:
        messages.error(request, "Укажите правильный адрес почты для пробного письма.")
        return redirect("conference:office_mailing")
    try:
        mailing.send_test(to, _site(request))
    except Exception as exc:  # noqa: BLE001 — показываем причину человеку
        messages.error(request, f"Письмо не отправлено: {type(exc).__name__}: {exc}")
    else:
        messages.success(request, f"Пробное письмо отправлено на {to}. Проверьте почту, а также папку «Спам».")
    return redirect("conference:office_mailing")


@office_required
@require_POST
def mailing_send(request):
    """Отправляет очередную пачку писем допущенным. Страница вызывает этот адрес по кругу, пока очередь не опустеет."""
    if not _can_send(request):
        raise PermissionDenied
    conf = ConferenceSettings.load()
    wants_json = request.headers.get("Accept") == "application/json"
    reason = _block_reason(conf)
    if reason:
        if wants_json:
            return JsonResponse({"error": reason}, status=409)
        messages.error(request, reason)
        return redirect("conference:office_mailing")
    sent, failed, queue, fatal = mailing.send_batch(_site(request), retry=request.POST.get("retry") == "1")
    if sent or failed:
        log_action(request, ActionLog.Action.MAIL, details=f"Поздравление с допуском: отправлено {sent}, ошибок {failed}")
    if wants_json:
        return JsonResponse({"sent": sent, "failed": failed, "queue": queue, "error": fatal, "totals": mailing.stats()})
    if fatal:
        messages.error(request, f"Отправка остановлена: {fatal}")
    else:
        messages.success(request, f"Отправлено писем: {sent}. Осталось в очереди: {queue}." + (f" Ошибок: {failed}." if failed else ""))
    return redirect("conference:office_mailing")

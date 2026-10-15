"""Рассылка писем участникам: поздравление с допуском ко 2 этапу.

Письмо одно на работу, уходит на почту участника из анкеты (почты соавтора в анкете нет).
Отправленные письма помечаются в заявке (admitted_mail_sent_at), поэтому повторный запуск
дописывает только недошедшие и никому не отправляет письмо дважды.
"""

import smtplib
from string import Formatter

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.utils import timezone

from .models import ConferenceSettings, Submission

BATCH_SIZE = 15  # писем за один запрос: хостинг не любит долгие запросы

DEFAULT_SUBJECT = "Поздравляем! Ваша работа допущена ко 2 этапу конференции «Эврика»"
DEFAULT_BODY = """Здравствуйте, {name}!

Поздравляем! Работа «{title}» (секция «{section}») допущена ко 2 этапу конференции «Эврика».

Защита работ пройдёт {dates}.
Место проведения: {venue}.

Новости и подробности — на сайте: {site}
Если появятся вопросы, пишите {contact}.

С уважением,
оргкомитет конференции «Эврика»
"""

PLACEHOLDERS = {
    "name": "ФИО участника (и соавтора)",
    "title": "название работы",
    "section": "секция",
    "conference": "полное название конференции",
    "dates": "даты проведения",
    "venue": "место проведения",
    "site": "адрес сайта",
    "contact": "куда писать с вопросами: чат поддержки в Max (если чата нет — почта)",
}


class _Blank(dict):
    def __missing__(self, key):
        return ""


def check_template(text):
    """Ошибка в тексте письма (неизвестное или незакрытое поле в фигурных скобках) или None."""
    try:
        names = {name for _, name, _, _ in Formatter().parse(text) if name}
    except ValueError:
        return "В тексте есть незакрытая или лишняя фигурная скобка."
    unknown = sorted(names - PLACEHOLDERS.keys())
    if unknown:
        return "Неизвестные поля: " + ", ".join("{" + n + "}" for n in unknown) + "."
    return None


def _contact(conf):
    """Куда писать с вопросами: в первую очередь чат поддержки в Max."""
    if conf.support_chat_url:
        return f"в чат поддержки в Max: {conf.support_chat_url}"
    if conf.contact_email:
        return f"на почту {conf.contact_email}"
    return "ответным письмом"


def _values(conf, submission, site):
    if submission is None:  # пример для проверки письма
        name, title, section = "Иванов Иван, Петрова Анна", "Название вашей работы", "Название секции"
    else:
        name = submission.full_name + (
            f", {submission.coauthor_last_name} {submission.coauthor_first_name}" if submission.coauthor_last_name else ""
        )
        title, section = submission.title, submission.section_label
    return _Blank(
        name=name, title=title, section=section, conference=conf.official_title,
        dates=conf.event_dates or "в ближайшее время (даты сообщим дополнительно)",
        venue=conf.venue or "сообщим дополнительно", site=site, contact=_contact(conf),
    )


def render(conf, submission, site):
    """(тема, текст) письма для заявки; submission=None — пример."""
    values = _values(conf, submission, site)
    subject = " ".join(conf.mail_admitted_subject.format_map(values).split())
    return subject, conf.mail_admitted_body.format_map(values).strip() + "\n"


def admitted_works():
    return Submission.objects.filter(admission=Submission.Admission.ADMITTED).select_related("section")


def stats():
    works = admitted_works()
    sent = works.filter(admitted_mail_sent_at__isnull=False).count()
    total = works.count()
    return {
        "total": total,
        "sent": sent,
        "pending": total - sent,
        "failed": works.filter(admitted_mail_sent_at__isnull=True).exclude(admitted_mail_error="").count(),
        "queue": works.filter(admitted_mail_sent_at__isnull=True, admitted_mail_error="").count(),
        "addresses": works.filter(admitted_mail_sent_at__isnull=True).values("email").distinct().count(),
    }


def _message(conf, submission, site, to):
    subject, body = render(conf, submission, site)
    headers = {}
    reply_to = [conf.contact_email] if conf.contact_email else None
    return EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [to], reply_to=reply_to, headers=headers)


def send_test(to, site):
    """Пробное письмо с примером данных. Ошибки отправки пробрасываются: их видно сразу."""
    _message(ConferenceSettings.load(), None, site, to).send()


# Ошибки, после которых нет смысла пробовать остальные письма: сервер почты недоступен или не принял вход.
_FATAL = (smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError)


def send_batch(site, limit=BATCH_SIZE, retry=False):
    """Отправляет до limit ещё не отправленных писем допущенным. Возвращает (отправлено, ошибок, в очереди, текст ошибки).

    Письма, которые не ушли, помечаются ошибкой и в этом запуске больше не берутся; retry=True
    сначала снимает эти пометки, чтобы попробовать их снова (так делает первое нажатие кнопки).
    """
    conf = ConferenceSettings.load()
    if retry:
        admitted_works().filter(admitted_mail_sent_at__isnull=True).update(admitted_mail_error="")
    sent = failed = 0
    fatal = ""
    connection = get_connection(fail_silently=False)
    try:
        for submission in admitted_works().filter(admitted_mail_sent_at__isnull=True, admitted_mail_error="").order_by("pk")[:limit]:
            # Занимаем письмо до отправки: два одновременных нажатия не пошлют его дважды.
            claimed = Submission.objects.filter(pk=submission.pk, admitted_mail_sent_at__isnull=True).update(
                admitted_mail_sent_at=timezone.now(), admitted_mail_error=""
            )
            if not claimed:
                continue
            try:
                message = _message(conf, submission, site, submission.email)
                message.connection = connection
                message.send()
                sent += 1
            except Exception as exc:  # noqa: BLE001 — любую ошибку отправки запоминаем и идём дальше
                failed += 1
                Submission.objects.filter(pk=submission.pk).update(
                    admitted_mail_sent_at=None, admitted_mail_error=f"{type(exc).__name__}: {exc}"[:200]
                )
                if isinstance(exc, _FATAL):
                    fatal = f"{type(exc).__name__}: {exc}"[:200]
                    break
    finally:
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass
    return sent, failed, stats()["queue"], fatal

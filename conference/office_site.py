"""Кабинет: направления, новости и документы — то же, что в админке, но простыми страницами."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import DocumentForm, NewsPostForm, SectionForm
from .models import Document, NewsPost, Section
from .office import office_required


def _section_places(section):
    taken = section.occupied()
    return " · ".join(f"{taken[n]}/{section.capacity}" for n in range(1, section.groups + 1))


def _yes_no(value):
    return "да" if value else "нет"


def _document_file(document):
    return " · ".join(part for part in (document.extension, document.size_display) if part)


# Раздел → модель, форма, тексты и столбцы списка: (заголовок, значение).
SITE = {
    "sections": {
        "model": Section,
        "form": SectionForm,
        "title": "Направления",
        "add": "Добавить направление",
        "new": "Новое направление",
        "empty": "Направлений пока нет.",
        "lead": "Направления и секции в анкете. Работа с соавтором занимает одно место.",
        "columns": [
            ("Порядок", lambda s: s.order),
            ("Название", lambda s: s.name),
            ("Секций", lambda s: s.groups),
            ("Мест в секции", lambda s: s.capacity),
            ("Занято", _section_places),
            ("В анкете", lambda s: _yes_no(s.is_active)),
        ],
    },
    "news": {
        "model": NewsPost,
        "form": NewsPostForm,
        "title": "Новости",
        "add": "Добавить новость",
        "new": "Новая новость",
        "empty": "Новостей пока нет.",
        "lead": "Новости на главной странице сайта. Новость с будущей датой появится в этот момент.",
        "columns": [
            ("Дата", lambda n: f"{timezone.localtime(n.published_at):%d.%m.%Y %H:%M}"),
            ("Заголовок", lambda n: n.title),
            ("Опубликована", lambda n: _yes_no(n.is_published)),
        ],
    },
    "documents": {
        "model": Document,
        "form": DocumentForm,
        "title": "Документы",
        "add": "Добавить документ",
        "new": "Новый документ",
        "empty": "Документов пока нет.",
        "lead": "Файлы в блоке «Документы» на главной: положение, приказы, программа. Бланки заявки и согласия — во вкладке «Конференция».",
        "columns": [
            ("Порядок", lambda d: d.order),
            ("Название", lambda d: d.title),
            ("Файл", _document_file),
            ("На сайте", lambda d: _yes_no(d.is_published)),
        ],
    },
}


def _config(request, kind, action):
    if kind not in SITE:
        raise Http404
    config = SITE[kind]
    if not request.user.has_perm(f"conference.{action}_{config['model']._meta.model_name}"):
        raise PermissionDenied
    return config


@office_required
def site_list(request, kind):
    config = _config(request, kind, "view")
    objects = config["model"].objects.all()
    rows = [(obj, [value(obj) for _, value in config["columns"]]) for obj in objects]
    return render(request, "conference/office/site_list.html", {
        "kind": kind, "config": config, "headers": [h for h, _ in config["columns"]], "rows": rows,
        "can_add": request.user.has_perm(f"conference.add_{config['model']._meta.model_name}"),
    })


@office_required
def site_edit(request, kind, pk=None):
    config = _config(request, kind, "change" if pk else "add")
    obj = get_object_or_404(config["model"], pk=pk) if pk else None
    form = config["form"](request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"«{saved}» сохранено.")
        return redirect("conference:office_site", kind=kind)
    file_url = None
    if isinstance(obj, Document):
        file_url = reverse("conference:download_document", args=[obj.pk])
    can_delete = obj is not None and request.user.has_perm(f"conference.delete_{config['model']._meta.model_name}")
    return render(request, "conference/office/site_form.html", {
        "kind": kind, "config": config, "form": form, "obj": obj, "file_url": file_url, "can_delete": can_delete,
    })


@office_required
@require_POST
def site_delete(request, kind, pk):
    config = _config(request, kind, "delete")
    obj = get_object_or_404(config["model"], pk=pk)
    if isinstance(obj, Section) and obj.submissions.exists():
        messages.error(
            request,
            f"В направление «{obj}» уже подали работы — удалить его нельзя. "
            "Чтобы оно не появлялось в анкете, снимите галочку «показывать в анкете».",
        )
        return redirect("conference:office_site_edit", kind=kind, pk=pk)
    obj.delete()  # файл документа удаляет сигнал post_delete
    messages.success(request, f"«{obj}» удалено.")
    return redirect("conference:office_site", kind=kind)

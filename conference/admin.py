from io import BytesIO

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from . import exports

from .models import ConferenceSettings, Document, NewsPost, ReviewLink, Section, Submission


@admin.register(ConferenceSettings)
class ConferenceSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {"fields": ("title", "tagline", "event_dates", "venue", "organizer")}),
        ("Контакты", {"fields": ("contact_email", "contact_phone")}),
        ("Приём работ", {"fields": ("submissions_open", "submissions_deadline")}),
        ("Бланки документов", {"fields": (
                "application_pdf",
                "application_template",
                "consent_pdf",
                "consent_template",
                "requirements_template",
            )}),
        ("Персональные данные", {"fields": ("privacy_policy",), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Запись одна — сразу открываем её на редактирование.
        obj = ConferenceSettings.load()
        return redirect(reverse("admin:conference_conferencesettings_change", args=[obj.pk]))


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "groups", "capacity", "places_display", "order", "is_active")
    list_editable = ("groups", "capacity", "order", "is_active")
    search_fields = ("name",)
    fields = ("name", "description", ("groups", "capacity"), ("order", "is_active"), "places_display")
    readonly_fields = ("places_display",)

    @admin.display(description="занято мест по секциям")
    def places_display(self, obj):
        if not obj.pk:
            return "—"
        taken = obj.occupied()
        return " · ".join(
            f"{obj.group_label(n)}: {taken[n]}/{obj.capacity}" for n in range(1, obj.groups + 1)
        )


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    change_list_template = "admin/conference/submission/change_list.html"

    def get_urls(self):
        wrap = self.admin_site.admin_view
        custom = [
            path("exports/", wrap(self.exports_page), name="conference_submission_exports"),
            path("export-sections/", wrap(self.export_sections), name="conference_submission_export_sections"),
            path("export/students-excel/", wrap(self.export_students_excel), name="conference_submission_students_excel"),
            path("export/students-word/", wrap(self.export_students_word), name="conference_submission_students_word"),
        ]
        return [*custom, *super().get_urls()]

    def _check_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied

    def exports_page(self, request):
        """Страница «Выгрузки»: четыре этапа, по каждому свои файлы."""
        self._check_view(request)
        stages = [
            {
                "title": "Этап 1. Все ученики по секциям",
                "text": "Строка на каждого ученика (соавтор — отдельной строкой): секция, ФИО, класс, школа, "
                        "название работы, руководитель, дата подачи и почта. Отклонённые заявки не входят.",
                "files": [
                    ("Excel", reverse("admin:conference_submission_students_excel")),
                    ("Word", reverse("admin:conference_submission_students_word")),
                ],
            },
            {"title": "Этап 2", "text": "Состав выгрузок будет определён.", "files": []},
            {"title": "Этап 3", "text": "Состав выгрузок будет определён.", "files": []},
            {"title": "Этап 4", "text": "Состав выгрузок будет определён.", "files": []},
        ]
        context = {
            **self.admin_site.each_context(request),
            "title": "Выгрузки",
            "opts": self.model._meta,
            "stages": stages,
            "sections_url": reverse("admin:conference_submission_export_sections"),
        }
        return render(request, "admin/conference/submission/exports.html", context)

    def export_sections(self, request):
        """Списки секций в Excel: сводка и по листу на секцию, без отклонённых заявок."""
        self._check_view(request)
        filename = f"Эврика — списки секций {timezone.localdate():%d.%m.%Y}.xlsx"
        return FileResponse(BytesIO(exports.build_sections_workbook()), as_attachment=True, filename=filename)

    def export_students_excel(self, request):
        self._check_view(request)
        filename = f"Эврика — все ученики по секциям {timezone.localdate():%d.%m.%Y}.xlsx"
        return FileResponse(BytesIO(exports.build_students_workbook()), as_attachment=True, filename=filename)

    def export_students_word(self, request):
        self._check_view(request)
        filename = f"Эврика — все ученики по секциям {timezone.localdate():%d.%m.%Y}.docx"
        return FileResponse(BytesIO(exports.build_students_docx()), as_attachment=True, filename=filename)

    list_display = (
        "number_display",
        "created_at",
        "full_name_display",
        "grade",
        "school",
        "section_display",
        "title",
        "status",
        "files_display",
    )
    list_display_links = ("number_display", "full_name_display")
    list_filter = ("status", "section", "section_number", "grade", "created_at", ("edited_by_participant_at", admin.EmptyFieldListFilter))
    list_editable = ("status",)
    list_select_related = ("section",)
    search_fields = (
        "last_name",
        "first_name",
        "email",
        "school",
        "district",
        "title",
        "supervisor_last_name",
        "supervisor2_last_name",
        "coauthor_last_name",
    )
    date_hierarchy = "created_at"
    readonly_fields = (
        "number_display", "created_at", "updated_at", "edited_by_participant_at",
        "file_link", "application_link", "consent_link",
    )
    fieldsets = (
        (
            "Оргкомитет",
            {
                "fields": (
                    "number_display",
                    "status",
                    "participant_message",
                    "admin_comment",
                    ("created_at", "updated_at", "edited_by_participant_at"),
                )
            },
        ),
        ("Работа", {"fields": ("title", ("section", "section_number"), "file_link")}),
        ("Документы", {"fields": ("application_link", "consent_link")}),
        ("Участник", {"fields": (("last_name", "first_name", "grade"), "snils", "school", "district", "email")}),
        ("Соавтор", {"fields": (("coauthor_last_name", "coauthor_first_name", "coauthor_grade"), "coauthor_snils")}),
        (
            "Руководитель",
            {
                "fields": (
                    ("supervisor_last_name", "supervisor_first_name", "supervisor_middle_name"),
                    ("supervisor_position", "supervisor_phone"),
                )
            },
        ),
        (
            "Второй руководитель",
            {
                "fields": (
                    ("supervisor2_last_name", "supervisor2_first_name", "supervisor2_middle_name"),
                    ("supervisor2_position", "supervisor2_phone"),
                )
            },
        ),
    )

    def has_add_permission(self, request):
        # Заявки приходят только через сайт: в админке нельзя приложить файл.
        return False

    @admin.display(description="№", ordering="pk")
    def number_display(self, obj):
        return obj.number

    @admin.display(description="секция", ordering="section")
    def section_display(self, obj):
        return obj.section_label

    @admin.display(description="участник", ordering="last_name")
    def full_name_display(self, obj):
        return obj.full_name

    def _link(self, obj, kind, file, text):
        if not obj.pk or not file:
            return "—"
        url = reverse("conference:download_submission_file", args=[obj.pk, kind])
        return format_html('<a href="{}">{}</a>', url, text)

    @admin.display(description="файл работы")
    def file_link(self, obj):
        return self._link(obj, "work", obj.file, obj.original_filename or "скачать")

    @admin.display(description="заявка")
    def application_link(self, obj):
        return self._link(obj, "application", obj.application_file, obj.application_original_filename or "скачать")

    @admin.display(description="согласие")
    def consent_link(self, obj):
        return self._link(obj, "consent", obj.consent_file, obj.consent_original_filename or "скачать")

    @admin.display(description="файлы")
    def files_display(self, obj):
        return format_html(
            "{} · {} · {}",
            self._link(obj, "work", obj.file, "работа"),
            self._link(obj, "application", obj.application_file, "заявка"),
            self._link(obj, "consent", obj.consent_file, "согласие"),
        )


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("title", "published_at", "is_published")
    list_editable = ("is_published",)
    search_fields = ("title", "text")
    date_hierarchy = "published_at"


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "description", "order", "is_published", "uploaded_at")
    list_editable = ("order", "is_published")
    search_fields = ("title", "description")


@admin.register(ReviewLink)
class ReviewLinkAdmin(admin.ModelAdmin):
    """Ссылки создают в кабинете оргкомитета (/office/); здесь — просмотр, срок и отключение."""

    list_display = ("scope_label", "created_by", "created_at", "expires_at", "is_active")
    list_editable = ("is_active",)
    readonly_fields = ("token", "section", "section_number", "created_by", "created_at")
    fields = ("section", "section_number", "token", "created_by", "created_at", "expires_at", "is_active")

    def has_add_permission(self, request):
        return False

    @admin.display(description="что открывает")
    def scope_label(self, obj):
        return obj.scope_label

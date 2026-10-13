from django.contrib import admin
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from .models import ConferenceSettings, Document, NewsPost, Section, Submission


@admin.register(ConferenceSettings)
class ConferenceSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {"fields": ("title", "tagline", "description", "event_dates", "venue", "organizer")}),
        ("Контакты", {"fields": ("contact_email", "contact_phone")}),
        ("Приём работ", {"fields": ("submissions_open", "submissions_deadline")}),
        ("Бланки документов", {"fields": ("application_template", "consent_template")}),
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
    list_filter = ("status", "section", "section_number", "grade", "created_at")
    list_editable = ("status",)
    list_select_related = ("section",)
    search_fields = (
        "last_name",
        "first_name",
        "email",
        "links_email",
        "school",
        "district",
        "title",
        "supervisor_last_name",
        "coauthor_last_name",
    )
    date_hierarchy = "created_at"
    readonly_fields = ("number_display", "created_at", "updated_at", "file_link", "application_link", "consent_link")
    fieldsets = (
        ("Оргкомитет", {"fields": ("number_display", "status", "admin_comment", ("created_at", "updated_at"))}),
        ("Работа", {"fields": ("title", ("section", "section_number"), "file_link")}),
        ("Документы", {"fields": ("application_link", "consent_link")}),
        ("Участник", {"fields": (("last_name", "first_name", "grade"), "school", "district", "email")}),
        ("Соавтор", {"fields": (("coauthor_last_name", "coauthor_first_name", "coauthor_grade"),)}),
        (
            "Руководитель",
            {
                "fields": (
                    ("supervisor_last_name", "supervisor_first_name", "supervisor_middle_name"),
                    ("supervisor_position", "supervisor_phone"),
                )
            },
        ),
        ("Связь", {"fields": ("links_email",)}),
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

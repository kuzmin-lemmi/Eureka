from django.contrib import admin
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from .models import ConferenceSettings, Section, Submission


@admin.register(ConferenceSettings)
class ConferenceSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {"fields": ("title", "tagline", "description", "event_dates", "venue", "organizer")}),
        ("Контакты", {"fields": ("contact_email", "contact_phone")}),
        ("Приём работ", {"fields": ("submissions_open", "submissions_deadline")}),
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
    list_display = ("name", "order", "is_active", "submissions_count")
    list_editable = ("order", "is_active")
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_submissions_count=Count("submissions"))

    @admin.display(description="заявок", ordering="_submissions_count")
    def submissions_count(self, obj):
        return obj._submissions_count


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "number_display",
        "created_at",
        "full_name_display",
        "grade",
        "school",
        "section",
        "title",
        "status",
        "file_link",
    )
    list_display_links = ("number_display", "full_name_display")
    list_filter = ("status", "section", "grade", "created_at")
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
    readonly_fields = ("number_display", "created_at", "updated_at", "file_link")
    fieldsets = (
        ("Оргкомитет", {"fields": ("number_display", "status", "admin_comment", ("created_at", "updated_at"))}),
        ("Работа", {"fields": ("title", "section", "file_link")}),
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

    @admin.display(description="участник", ordering="last_name")
    def full_name_display(self, obj):
        return obj.full_name

    @admin.display(description="файл")
    def file_link(self, obj):
        if not obj.pk or not obj.file:
            return "—"
        url = reverse("conference:download_submission", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.original_filename or "скачать")

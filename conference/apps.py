from django.apps import AppConfig
from django.db.models.signals import post_migrate

ORGANIZERS_GROUP = "Оргкомитет"
ORGANIZERS_PERMISSIONS = [
    "view_submission",
    "change_submission",
    "delete_submission",
    "view_section",
    "add_section",
    "change_section",
    "delete_section",
    "view_conferencesettings",
    "change_conferencesettings",
    "view_newspost",
    "add_newspost",
    "change_newspost",
    "delete_newspost",
    "view_document",
    "add_document",
    "change_document",
    "delete_document",
]


def ensure_organizers_group(sender, **kwargs):
    """Группа с правами на заявки, секции и настройки — её выдают новым администраторам."""
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.get_or_create(name=ORGANIZERS_GROUP)
    group.permissions.add(
        *Permission.objects.filter(content_type__app_label=sender.label, codename__in=ORGANIZERS_PERMISSIONS)
    )


class ConferenceConfig(AppConfig):
    name = "conference"
    verbose_name = "Конференция"

    def ready(self):
        post_migrate.connect(ensure_organizers_group, sender=self)

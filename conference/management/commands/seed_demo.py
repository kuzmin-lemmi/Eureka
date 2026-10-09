from django.core.management import call_command
from django.core.management.base import BaseCommand

from conference.models import ConferenceSettings, Section


class Command(BaseCommand):
    help = "Заполняет пустую базу описанием конференции и направлениями из списка оргкомитета."

    def handle(self, *args, **options):
        conf = ConferenceSettings.load()
        if not conf.description:
            conf.title = "Межрегиональная НПК «Эврика-2027»"
            conf.tagline = "Научно-практическая конференция исследовательских работ школьников"
            conf.description = (
                "Это демонстрационный текст — замените его в админке: «Настройки конференции»."
            )
            conf.event_dates = "апрель 2027"
            conf.venue = "Саратов"
            conf.save()
            self.stdout.write("Заполнены настройки конференции.")

        if Section.objects.exists():
            self.stdout.write("Направления уже есть — пропускаю (обновить список: manage.py load_sections).")
            return
        call_command("load_sections", stdout=self.stdout)

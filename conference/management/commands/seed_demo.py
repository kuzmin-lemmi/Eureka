from django.core.management.base import BaseCommand

from conference.models import ConferenceSettings, Section

DEMO_SECTIONS = [
    ("Математика и информатика", "Алгоритмы, программирование, прикладная математика."),
    ("Физика и техника", "Эксперименты, моделирование, инженерные проекты."),
    ("Естественные науки", "Биология, химия, экология, география."),
    ("Гуманитарные науки", "История, филология, обществознание, искусство."),
]


class Command(BaseCommand):
    help = "Заполняет пустую базу демонстрационными секциями и описанием конференции (для локальной разработки)."

    def handle(self, *args, **options):
        conf = ConferenceSettings.load()
        if not conf.description:
            conf.title = "Межрегиональная НПК «Эврика-2026»"
            conf.tagline = "Научно-практическая конференция исследовательских работ школьников"
            conf.description = (
                "Это демонстрационный текст — замените его в админке: «Настройки конференции»."
            )
            conf.event_dates = "апрель 2027"
            conf.venue = "Саратов"
            conf.save()
            self.stdout.write("Заполнены настройки конференции.")

        if Section.objects.exists():
            self.stdout.write("Секции уже есть — пропускаю.")
            return
        for order, (name, description) in enumerate(DEMO_SECTIONS, start=1):
            Section.objects.create(name=name, description=description, order=order)
        self.stdout.write(self.style.SUCCESS(f"Создано секций: {len(DEMO_SECTIONS)}."))

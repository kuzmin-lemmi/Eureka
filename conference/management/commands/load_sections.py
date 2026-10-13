from django.core.management.base import BaseCommand

from conference.models import Section

# Направления конференции и число секций в каждом (по 12 мест по умолчанию).
SECTIONS = [
    ("Навыки XXI века", "", 1),
    ("Наследие: человек, событие, время", "", 2),
    ("Семья в зеркале современного общества", "", 1),
    ("Здоровое поколение", "", 3),
    ("Искусство слова и лингвистика. Язык в современном мире", "", 2),
    ("Региональное краеведение", "", 3),
    ("Экология: проблемы ценностей и приоритетов", "", 3),
    ("Языкознание и страноведение", "Иностранные языки", 2),
    ("Азбучные истины: эпоха ЭВМ", "", 1),
    ("Ракурс: математический объект", "", 2),
    ("Язык географии – язык цивилизации", "", 1),
    ("Трудные вопросы истории. Современная трактовка", "", 1),
    ("Изучение и наблюдение природы породило науки (Цицерон)", "", 3),
]


class Command(BaseCommand):
    help = (
        "Создаёт направления конференции из списка оргкомитета и обновляет у существующих число секций. "
        "С --replace удаляет направления не из списка, если в них нет заявок."
    )

    def add_arguments(self, parser):
        parser.add_argument("--replace", action="store_true", help="удалить направления, которых нет в списке")

    def handle(self, *args, replace=False, **options):
        names = []
        for order, (name, description, groups) in enumerate(SECTIONS, start=1):
            section, created = Section.objects.get_or_create(
                name=name, defaults={"description": description, "groups": groups, "order": order}
            )
            if not created:
                section.groups, section.order = groups, order
                section.save(update_fields=["groups", "order"])
            names.append(name)
            self.stdout.write(f"{'+' if created else '='} {name}: секций {groups}")

        if replace:
            for section in Section.objects.exclude(name__in=names):
                if section.submissions.exists():
                    self.stdout.write(self.style.WARNING(f"Оставлено (есть заявки): {section.name}"))
                else:
                    section.delete()
                    self.stdout.write(f"- {section.name}")
        self.stdout.write(self.style.SUCCESS(f"Направлений в списке: {len(SECTIONS)}."))

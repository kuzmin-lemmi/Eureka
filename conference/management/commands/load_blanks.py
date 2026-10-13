from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from conference.models import ConferenceSettings

BLANKS_DIR = Path(settings.BASE_DIR) / "docs" / "blanks"
# файл в docs/blanks → поле настроек конференции
FILES = {
    "application.pdf": "application_pdf",
    "application.docx": "application_template",
    "consent.pdf": "consent_pdf",
    "consent.docx": "consent_template",
    "requirements.pdf": "requirements_template",
}


class Command(BaseCommand):
    help = (
        "Загружает бланки из docs/blanks в настройки конференции: заявку и согласие родителя (PDF и Word) и требования к работе (PDF). "
        "Прежние файлы заменяются. После этого их можно заменить и в админке."
    )

    def handle(self, *args, **options):
        conf = ConferenceSettings.load()
        for filename, field_name in FILES.items():
            source = BLANKS_DIR / filename
            if not source.exists():
                raise CommandError(f"Не найден файл {source}")
            field = getattr(conf, field_name)
            if field:
                field.delete(save=False)
            field.save(filename, ContentFile(source.read_bytes()), save=False)
            self.stdout.write(f"{field_name}: {filename}")
        conf.save()
        self.stdout.write(self.style.SUCCESS("Бланки загружены."))

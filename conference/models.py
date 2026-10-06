import uuid
from pathlib import Path

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

GRADE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(11)]


class ConferenceSettings(models.Model):
    """Общие настройки конференции. Всегда одна запись (pk=1)."""

    title = models.CharField(
        "название конференции",
        max_length=200,
        default="Межрегиональная научно-практическая конференция «Эврика»",
    )
    tagline = models.CharField("подзаголовок", max_length=300, blank=True)
    description = models.TextField("описание", blank=True, help_text="Показывается на главной странице.")
    event_dates = models.CharField("даты проведения", max_length=100, blank=True, help_text="Например: 15–16 апреля 2027")
    venue = models.CharField("место проведения", max_length=300, blank=True)
    organizer = models.CharField("организатор", max_length=300, blank=True)
    contact_email = models.EmailField("email для связи", blank=True)
    contact_phone = models.CharField("телефон для связи", max_length=50, blank=True)

    submissions_open = models.BooleanField("приём работ открыт", default=True)
    submissions_deadline = models.DateTimeField(
        "приём работ до", null=True, blank=True, help_text="Пусто — без ограничения по времени."
    )

    privacy_policy = models.TextField(
        "политика обработки персональных данных",
        blank=True,
        help_text="Текст страницы, на которую ссылается согласие в анкете. Если пусто — показывается шаблонный текст.",
    )

    class Meta:
        verbose_name = "настройки конференции"
        verbose_name_plural = "настройки конференции"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_submission_open(self):
        return self.submissions_open and (
            self.submissions_deadline is None or timezone.now() <= self.submissions_deadline
        )


class Section(models.Model):
    name = models.CharField("название", max_length=200)
    description = models.TextField("описание", blank=True)
    order = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("показывать в анкете", default=True)

    class Meta:
        verbose_name = "секция"
        verbose_name_plural = "секции"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


def submission_upload_to(instance, filename):
    # Имя файла на диске случайное: исходное хранится отдельно в original_filename.
    ext = Path(filename).suffix.lower()
    return f"submissions/{timezone.now():%Y}/{uuid.uuid4().hex}{ext}"


class Submission(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        ACCEPTED = "accepted", "Принята"
        REVISION = "revision", "На доработке"
        REJECTED = "rejected", "Отклонена"

    # Участник
    email = models.EmailField("электронная почта участника")
    district = models.CharField("муниципальный район", max_length=200)
    school = models.CharField("образовательная организация", max_length=300, help_text="Краткое название")
    last_name = models.CharField("фамилия", max_length=100)
    first_name = models.CharField("имя", max_length=100)
    grade = models.PositiveSmallIntegerField("класс", validators=GRADE_VALIDATORS)

    # Работа
    title = models.CharField("название научно-исследовательской работы", max_length=500)
    section = models.ForeignKey(
        Section, on_delete=models.PROTECT, related_name="submissions", verbose_name="межпредметное направление"
    )
    file = models.FileField("файл работы", upload_to=submission_upload_to)
    original_filename = models.CharField("исходное имя файла", max_length=255, blank=True)

    # Соавтор (необязательно)
    coauthor_first_name = models.CharField("имя соавтора", max_length=100, blank=True)
    coauthor_last_name = models.CharField("фамилия соавтора", max_length=100, blank=True)
    coauthor_grade = models.PositiveSmallIntegerField(
        "класс соавтора", null=True, blank=True, validators=GRADE_VALIDATORS
    )

    # Руководитель
    supervisor_last_name = models.CharField("фамилия руководителя", max_length=100)
    supervisor_first_name = models.CharField("имя руководителя", max_length=100)
    supervisor_middle_name = models.CharField("отчество руководителя", max_length=100, blank=True)
    supervisor_position = models.CharField("должность руководителя", max_length=200)
    supervisor_phone = models.CharField("телефон руководителя", max_length=30)

    links_email = models.EmailField(
        "почта для ссылок на тестирование и второй этап",
        help_text="На этот адрес придут ссылки на подключение к тестированию и второму этапу конференции.",
    )

    # Оргкомитет
    status = models.CharField("статус", max_length=10, choices=Status, default=Status.NEW)
    admin_comment = models.TextField("комментарий оргкомитета", blank=True)
    created_at = models.DateTimeField("подана", auto_now_add=True)
    updated_at = models.DateTimeField("изменена", auto_now=True)

    class Meta:
        verbose_name = "заявка"
        verbose_name_plural = "заявки"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} {self.full_name} — {self.title}"

    @property
    def number(self):
        return f"№ {self.pk:04d}" if self.pk else "новая"

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name}"

    @property
    def coauthor(self):
        if not self.coauthor_last_name:
            return ""
        return f"{self.coauthor_last_name} {self.coauthor_first_name}, {self.coauthor_grade} класс"

    @property
    def supervisor(self):
        return " ".join(
            part for part in (self.supervisor_last_name, self.supervisor_first_name, self.supervisor_middle_name) if part
        )

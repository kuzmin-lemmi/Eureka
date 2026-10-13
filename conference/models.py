import uuid
from pathlib import Path

from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# В конференции участвуют школьники 8–11 классов.
GRADE_MIN, GRADE_MAX = 8, 11
GRADE_VALIDATORS = [MinValueValidator(GRADE_MIN), MaxValueValidator(GRADE_MAX)]
BLANK_EXTENSIONS = ["pdf", "doc", "docx", "odt", "rtf"]


def blank_upload_to(instance, filename):
    return f"blanks/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


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

    application_template = models.FileField(
        "бланк заявки",
        upload_to=blank_upload_to,
        blank=True,
        validators=[FileExtensionValidator(BLANK_EXTENSIONS)],
        help_text="Участники скачивают его из анкеты, заполняют, подписывают и загружают скан.",
    )
    consent_template = models.FileField(
        "бланк согласия на обработку ПДн",
        upload_to=blank_upload_to,
        blank=True,
        validators=[FileExtensionValidator(BLANK_EXTENSIONS)],
        help_text="Согласие родителя (законного представителя) участника.",
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
    """Межпредметное направление. Если участников много, оно делится на несколько
    секций с одинаковым названием и номером: «Краеведение 1», «Краеведение 2»…"""

    name = models.CharField("название", max_length=200)
    description = models.TextField("описание", blank=True)
    groups = models.PositiveSmallIntegerField(
        "количество секций",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Если больше одной, в анкете появятся «Название 1», «Название 2» и т. д.",
    )
    capacity = models.PositiveSmallIntegerField(
        "мест в секции",
        default=15,
        validators=[MinValueValidator(1)],
        help_text="Участник и соавтор занимают по месту. Отклонённые заявки места не занимают.",
    )
    order = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("показывать в анкете", default=True)

    class Meta:
        verbose_name = "направление"
        verbose_name_plural = "направления (секции)"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def group_label(self, number):
        return f"{self.name} {number}" if self.groups > 1 else self.name

    def occupied(self):
        """Занятые места по номерам секций: {1: 12, 2: 3, …}."""
        taken = dict.fromkeys(range(1, self.groups + 1), 0)
        rows = (
            self.submissions.exclude(status=Submission.Status.REJECTED)
            .values_list("section_number", "coauthor_last_name")
        )
        for number, coauthor in rows:
            taken[number] = taken.get(number, 0) + (2 if coauthor else 1)
        return taken

    def free_places(self):
        """Свободные места по номерам секций (только существующие секции)."""
        taken = self.occupied()
        return {n: max(self.capacity - taken[n], 0) for n in range(1, self.groups + 1)}


def submission_upload_to(instance, filename):
    # Имя файла на диске случайное: исходное хранится отдельно в original_filename.
    ext = Path(filename).suffix.lower()
    return f"submissions/{timezone.now():%Y}/{uuid.uuid4().hex}{ext}"


def document_upload_to(instance, filename):
    ext = Path(filename).suffix.lower()
    return f"documents/{timezone.now():%Y}/{uuid.uuid4().hex}{ext}"


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
    section_number = models.PositiveSmallIntegerField(
        "номер секции", default=1, validators=[MinValueValidator(1)],
        help_text="Для направлений из нескольких секций: 1, 2, 3…",
    )
    file = models.FileField("файл работы", upload_to=submission_upload_to)
    original_filename = models.CharField("исходное имя файла", max_length=255, blank=True)

    # Подписанные документы (скан или фото). В анкете обязательны; пустыми
    # остаются только у заявок, поданных до появления этих полей.
    application_file = models.FileField("заявка", upload_to=document_upload_to, blank=True)
    application_original_filename = models.CharField("исходное имя файла заявки", max_length=255, blank=True)
    consent_file = models.FileField("согласие на обработку ПДн", upload_to=document_upload_to, blank=True)
    consent_original_filename = models.CharField("исходное имя файла согласия", max_length=255, blank=True)

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
    def section_label(self):
        return self.section.group_label(self.section_number)

    @property
    def people(self):
        return 2 if self.coauthor_last_name else 1

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

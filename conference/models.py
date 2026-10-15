import uuid
from datetime import timedelta
from pathlib import Path

from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
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

    application_pdf = models.FileField(
        "бланк заявки (PDF)",
        upload_to=blank_upload_to,
        blank=True,
        validators=[FileExtensionValidator(["pdf"])],
        help_text="Основной файл: участники скачивают его из анкеты, печатают, подписывают и загружают скан.",
    )
    application_template = models.FileField(
        "бланк заявки (Word)",
        upload_to=blank_upload_to,
        blank=True,
        validators=[FileExtensionValidator(BLANK_EXTENSIONS)],
        help_text="Необязательно: для тех, кто заполняет заявку на компьютере перед печатью.",
    )
    consent_pdf = models.FileField(
        "бланк согласия на обработку ПДн (PDF)",
        upload_to=blank_upload_to,
        blank=True,
        validators=[FileExtensionValidator(["pdf"])],
        help_text="Согласие родителя (законного представителя) участника. Основной файл.",
    )
    consent_template = models.FileField(
        "бланк согласия на обработку ПДн (Word)",
        upload_to=blank_upload_to,
        blank=True,
        validators=[FileExtensionValidator(BLANK_EXTENSIONS)],
        help_text="Необязательно: для тех, кто заполняет согласие на компьютере перед печатью.",
    )
    requirements_template = models.FileField(
        "требования к работе (PDF)",
        upload_to=blank_upload_to,
        blank=True,
        validators=[FileExtensionValidator(["pdf"])],
        help_text="Объём, структура и оформление работы. Показывается в анкете и в документах конференции.",
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

    @staticmethod
    def _links(pdf, pdf_kind, word, word_kind):
        """Ссылки на файлы бланка: [(подпись, вид в URL)], PDF первым."""
        return [(label, kind) for label, kind, file in (("PDF", pdf_kind, pdf), ("Word", word_kind, word)) if file]

    @property
    def application_links(self):
        return self._links(self.application_pdf, "application", self.application_template, "application-word")

    @property
    def consent_links(self):
        return self._links(self.consent_pdf, "consent", self.consent_template, "consent-word")

    @property
    def requirements_links(self):
        return [("PDF", "requirements")] if self.requirements_template else []

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
        default=12,
        validators=[MinValueValidator(1)],
        help_text="Сколько работ принимает секция. Работа с соавтором — одно место. Удалённая заявка место освобождает.",
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

    def occupied(self, exclude=None):
        """Занятые места (поданные работы) по номерам секций: {1: 12, 2: 3, …}. Соавтор места не занимает.
        exclude — pk заявки, которую не считать (при редактировании заявка не занимает место сама у себя)."""
        taken = dict.fromkeys(range(1, self.groups + 1), 0)
        rows = self.submissions.all()
        if exclude:
            rows = rows.exclude(pk=exclude)
        for number in rows.values_list("section_number", flat=True):
            taken[number] = taken.get(number, 0) + 1
        return taken

    def free_places(self, exclude=None):
        """Свободные места по номерам секций (только существующие секции)."""
        taken = self.occupied(exclude)
        return {n: max(self.capacity - taken[n], 0) for n in range(1, self.groups + 1)}


def submission_upload_to(instance, filename):
    # Имя файла на диске случайное: исходное хранится отдельно в original_filename.
    ext = Path(filename).suffix.lower()
    return f"submissions/{timezone.now():%Y}/{uuid.uuid4().hex}{ext}"


def document_upload_to(instance, filename):
    ext = Path(filename).suffix.lower()
    return f"documents/{timezone.now():%Y}/{uuid.uuid4().hex}{ext}"


class Submission(models.Model):
    # Пока приём открыт, у заявки нет статуса: участник может её изменить или удалить.
    # После закрытия приёма оргкомитет решает, допущена ли работа ко 2 этапу.
    class Admission(models.TextChoices):
        PENDING = "", "Не решено"
        ADMITTED = "admitted", "Допущен"
        NOT_ADMITTED = "not_admitted", "Не допущен"

    # Участник
    email = models.EmailField("электронная почта участника")
    district = models.CharField("муниципальный район", max_length=200)
    school = models.CharField(
        "образовательная организация", max_length=300, help_text="Полное название, без сокращений"
    )
    last_name = models.CharField("фамилия", max_length=100)
    first_name = models.CharField("имя", max_length=100)
    grade = models.PositiveSmallIntegerField("класс", validators=GRADE_VALIDATORS)
    snils = models.CharField("СНИЛС", max_length=14, blank=True, help_text="Формат: 123-456-789 01")

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
    coauthor_snils = models.CharField("СНИЛС соавтора", max_length=14, blank=True)
    coauthor_grade = models.PositiveSmallIntegerField(
        "класс соавтора", null=True, blank=True, validators=GRADE_VALIDATORS
    )

    # Руководитель
    supervisor_last_name = models.CharField("фамилия руководителя", max_length=100)
    supervisor_first_name = models.CharField("имя руководителя", max_length=100)
    supervisor_middle_name = models.CharField("отчество руководителя", max_length=100, blank=True)
    supervisor_position = models.CharField("должность руководителя", max_length=200)
    supervisor_phone = models.CharField("телефон руководителя", max_length=30)

    # Второй руководитель (необязательно): по Положению их допускается не более двух.
    supervisor2_last_name = models.CharField("фамилия второго руководителя", max_length=100, blank=True)
    supervisor2_first_name = models.CharField("имя второго руководителя", max_length=100, blank=True)
    supervisor2_middle_name = models.CharField("отчество второго руководителя", max_length=100, blank=True)
    supervisor2_position = models.CharField("должность второго руководителя", max_length=200, blank=True)
    supervisor2_phone = models.CharField("телефон второго руководителя", max_length=30, blank=True)

    # Оргкомитет
    admission = models.CharField(
        "допуск ко 2 этапу", max_length=12, choices=Admission, default=Admission.PENDING, blank=True
    )
    admin_comment = models.TextField("комментарий оргкомитета", blank=True, help_text="Виден только оргкомитету.")
    participant_message = models.TextField(
        "сообщение участнику",
        blank=True,
        help_text="Участник видит его в разделе «Мои заявки», например что исправить в работе.",
    )
    created_at = models.DateTimeField("подана", auto_now_add=True)
    updated_at = models.DateTimeField("изменена", auto_now=True)
    edited_by_participant_at = models.DateTimeField("изменена участником", null=True, blank=True)

    class Meta:
        verbose_name = "заявка"
        verbose_name_plural = "заявки"
        ordering = ["-created_at"]
        constraints = [
            # Один человек (по СНИЛС основного автора) — одна заявка в направлении.
            # Недопущенные не считаются: так прошли миграцию старые отклонённые заявки.
            models.UniqueConstraint(
                fields=["snils", "section"],
                condition=~models.Q(admission="not_admitted") & ~models.Q(snils=""),
                name="one_active_submission_per_snils_and_section",
                violation_error_message="Заявка этого участника в это направление уже есть.",
            )
        ]

    @property
    def is_editable(self):
        """Изменить или удалить заявку участник может, пока открыт приём работ."""
        return ConferenceSettings.load().is_submission_open

    def delete_files(self):
        for f in (self.file, self.application_file, self.consent_file):
            if f:
                f.delete(save=False)

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
    def supervisor2(self):
        return " ".join(
            part
            for part in (self.supervisor2_last_name, self.supervisor2_first_name, self.supervisor2_middle_name)
            if part
        )

    @property
    def supervisor(self):
        return " ".join(
            part for part in (self.supervisor_last_name, self.supervisor_first_name, self.supervisor_middle_name) if part
        )


class NewsPost(models.Model):
    title = models.CharField("заголовок", max_length=200)
    text = models.TextField("текст", help_text="Абзацы разделяйте пустой строкой.")
    published_at = models.DateTimeField(
        "дата публикации", default=timezone.now, help_text="Можно поставить дату в будущем: новость появится в этот момент."
    )
    is_published = models.BooleanField("опубликована", default=True)

    class Meta:
        verbose_name = "новость"
        verbose_name_plural = "новости"
        ordering = ["-published_at", "-pk"]

    def __str__(self):
        return self.title

    @classmethod
    def visible(cls):
        return cls.objects.filter(is_published=True, published_at__lte=timezone.now())


DOCUMENT_EXTENSIONS = ["pdf", "doc", "docx", "odt", "rtf", "xls", "xlsx", "ods", "ppt", "pptx", "zip", "jpg", "jpeg", "png"]


def public_document_upload_to(instance, filename):
    return f"public_documents/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Document(models.Model):
    title = models.CharField("название", max_length=200)
    description = models.CharField("пояснение", max_length=300, blank=True)
    file = models.FileField(
        "файл", upload_to=public_document_upload_to, validators=[FileExtensionValidator(DOCUMENT_EXTENSIONS)]
    )
    order = models.PositiveSmallIntegerField("порядок", default=0)
    is_published = models.BooleanField("показывать на сайте", default=True)
    uploaded_at = models.DateTimeField("загружен", auto_now_add=True)

    class Meta:
        verbose_name = "документ"
        verbose_name_plural = "документы"
        ordering = ["order", "-uploaded_at"]

    def __str__(self):
        return self.title

    @property
    def extension(self):
        return Path(self.file.name).suffix.lstrip(".").upper()

    @property
    def size_display(self):
        try:
            size = self.file.size
        except OSError:
            return ""
        if size < 1024 * 1024:
            return f"{max(1, round(size / 1024))} КБ"
        return f"{size / 1024 / 1024:.1f}".replace(".", ",") + " МБ"


REVIEW_LINK_DAYS = 30


def new_review_token():
    import secrets

    return secrets.token_urlsafe(18)


class ReviewLink(models.Model):
    """Ссылка для проверяющего: скачать архив работ секции (или всех) без входа в кабинет."""

    token = models.CharField("код ссылки", max_length=40, unique=True, default=new_review_token, editable=False)
    section = models.ForeignKey(
        Section, on_delete=models.CASCADE, null=True, blank=True, related_name="review_links",
        verbose_name="направление", help_text="Пусто — все работы.",
    )
    section_number = models.PositiveSmallIntegerField("номер секции", null=True, blank=True)
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="создал"
    )
    created_at = models.DateTimeField("создана", auto_now_add=True)
    expires_at = models.DateTimeField("действует до")
    is_active = models.BooleanField("включена", default=True)

    class Meta:
        verbose_name = "ссылка для проверяющего"
        verbose_name_plural = "ссылки для проверяющих"
        ordering = ["-created_at"]

    def __str__(self):
        return self.scope_label

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=REVIEW_LINK_DAYS)
        super().save(*args, **kwargs)

    @property
    def scope_label(self):
        if not self.section_id:
            return "Все работы"
        return self.section.group_label(self.section_number or 1)

    @property
    def is_valid(self):
        return self.is_active and timezone.now() <= self.expires_at

    def groups(self):
        """[(направление, номер секции)], которые открывает ссылка."""
        if self.section_id:
            return [(self.section, self.section_number or 1)]
        return [(s, n) for s in Section.objects.all() for n in range(1, s.groups + 1)]


@receiver(post_delete, sender=Submission)
def delete_submission_files(sender, instance, **kwargs):
    """Файлы удалённой заявки (участником, в админке или командой) убираем с диска после записи в базу."""
    transaction.on_commit(instance.delete_files)

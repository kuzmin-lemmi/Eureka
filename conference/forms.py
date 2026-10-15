import re
from pathlib import Path

from django import forms
from django.conf import settings
from django.urls import reverse
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import (
    DOCUMENT_EXTENSIONS as PUBLIC_DOCUMENT_EXTENSIONS, GRADE_MAX, GRADE_MIN, ConferenceSettings, Document, FaqItem, NewsAttachment, NewsPost, Section, Submission,
)

# Текст работы — только документы: без презентаций и видео.
ALLOWED_EXTENSIONS = (".pdf", ".doc", ".docx", ".odt", ".rtf")
# Подписанные заявка и согласие — скан или фото.
DOCUMENT_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")
GRADE_CHOICES = [("", "—")] + [(n, str(n)) for n in range(GRADE_MIN, GRADE_MAX + 1)]

# Поля, которые переносятся в анкету следующей работы того же руководителя.
REPEAT_FIELDS = (
    "school",
    "district",
    "supervisor_last_name",
    "supervisor_first_name",
    "supervisor_middle_name",
    "supervisor_position",
    "supervisor_phone",
    "supervisor2_last_name",
    "supervisor2_first_name",
    "supervisor2_middle_name",
    "supervisor2_position",
    "supervisor2_phone",
)
SUPERVISOR2_FIELDS = (
    "supervisor2_last_name",
    "supervisor2_first_name",
    "supervisor2_position",
    "supervisor2_phone",
)


def clean_snils(value):
    """Приводит СНИЛС к виду «123-456-789 01» и проверяет контрольное число (ловит опечатки)."""
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    if len(digits) != 11:
        raise forms.ValidationError("СНИЛС состоит из 11 цифр, например 123-456-789 01.")
    number, control = digits[:9], int(digits[9:])
    # Контрольное число считается только для номеров больше 001-001-998.
    if int(number) > 1001998:
        total = sum(int(d) * w for d, w in zip(number, range(9, 0, -1)))
        expected = total if total < 100 else (0 if total in (100, 101) else (total % 101) % 100)
        if expected != control:
            raise forms.ValidationError("Проверьте СНИЛС: в номере опечатка.")
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]} {digits[9:]}"


def places(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} место"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} места"
    return f"{n} мест"


class SlotSelect(forms.Select):
    """Список секций, где заполненные видны, но недоступны для выбора."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled_values = set()

    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        if str(value) in self.disabled_values:
            option["attrs"]["disabled"] = True
        return option


def slot_label(section, number, free):
    label = section.group_label(number)
    return label + (f" — свободно {places(free)}" if free else " — мест нет")


def section_slots(exclude=None):
    """[(значение «pk:номер», подпись, свободно мест, направление, номер)] для активных направлений.
    exclude — pk редактируемой заявки: её места считаются свободными."""
    slots = []
    for section in Section.objects.filter(is_active=True):
        free_by_number = section.free_places(exclude)
        # Секции направления заполняются по очереди: предлагаем первую, где ещё есть места.
        # Следующая появляется, когда предыдущая заполнена. Если заполнены все — последнюю, как «мест нет».
        number = next((n for n, free in free_by_number.items() if free), max(free_by_number))
        free = free_by_number[number]
        slots.append((f"{section.pk}:{number}", slot_label(section, number, free), free, section, number))
    return slots


def formats(extensions):
    return ", ".join(dict.fromkeys(ext.lstrip(".").upper().replace("JPEG", "JPG") for ext in extensions))


class SectionFull(Exception):
    """Секцию заняли, пока участник заполнял анкету."""


def duplicate_message(section):
    return format_html(
        "У участника с этим СНИЛС уже есть заявка в направлении «{}». Подать вторую в то же направление нельзя — "
        'изменить поданную можно в разделе <a href="{}">«Мои заявки»</a>.',
        section.name,
        reverse("conference:my"),
    )


# Настройки конференции в кабинете: (заголовок блока, поля). Порядок — как на странице.
SETTINGS_FIELDSETS = [
    ("Конференция", ["title", "tagline", "edition", "year", "description", "event_dates", "venue", "organizer"]),
    ("Контакты оргкомитета", ["contact_email", "contact_phone"]),
    ("Приём работ", ["submissions_open", "submissions_deadline"]),
    ("Бланки документов", ["application_pdf", "application_template", "consent_pdf", "consent_template", "requirements_template"]),
    ("Персональные данные", ["privacy_policy"]),
]
# Поле бланка → вид для ссылки «скачать текущий» (conference:blank).
SETTINGS_BLANK_KINDS = {
    "application_pdf": "application",
    "application_template": "application-word",
    "consent_pdf": "consent",
    "consent_template": "consent-word",
    "requirements_template": "requirements",
}


class ConferenceSettingsForm(forms.ModelForm):
    class Meta:
        model = ConferenceSettings
        fields = [name for _, names in SETTINGS_FIELDSETS for name in names]
        widgets = {
            "submissions_deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "description": forms.Textarea(attrs={"rows": 5}),
            "privacy_policy": forms.Textarea(attrs={"rows": 12}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Имена бланков до правки: при проверке формы в instance уже попадают новые файлы.
        self.old_files = {name: getattr(self.instance, name).name for name in SETTINGS_BLANK_KINDS}

    def save(self, commit=True):
        conf = super().save(commit)
        # Заменённый или удалённый бланк убираем с диска, чтобы не копились старые файлы.
        for name, path in self.old_files.items():
            if path and getattr(conf, name).name != path:
                getattr(conf, name).storage.delete(path)
        return conf


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ["name", "description", "groups", "capacity", "order", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_groups(self):
        groups = self.cleaned_data["groups"]
        if self.instance.pk:
            used = self.instance.submissions.filter(section_number__gt=groups).order_by("-section_number").first()
            if used:
                self.add_error(
                    "groups",
                    f"В секции {self.instance.group_label(used.section_number)} уже есть работы — "
                    f"секций не может быть меньше {used.section_number}.",
                )
        return groups


PHOTO_MAX_SIDE = 1600
PHOTO_MAX_MB = 25


def prepare_photo(upload):
    """Фото с телефона → JPEG не больше 1600 px, повёрнутый как надо и без EXIF."""
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps, UnidentifiedImageError

    if upload.size > PHOTO_MAX_MB * 1024 * 1024:
        raise forms.ValidationError(f"«{upload.name}» больше {PHOTO_MAX_MB} МБ.")
    try:
        image = Image.open(upload)
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError):
        raise forms.ValidationError(f"«{upload.name}» — не фото или формат не поддерживается. Загрузите JPG или PNG.")
    if image.mode != "RGB":
        background = Image.new("RGB", image.size, "white")  # прозрачный PNG — на белом фоне
        background.paste(image, mask=image.convert("RGBA").getchannel("A"))
        image = background
    image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=85, optimize=True, progressive=True)  # EXIF не сохраняется
    return ContentFile(buffer.getvalue(), name="photo.jpg")


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleDocumentField(forms.FileField):
    """Несколько документов за раз: та же проверка расширения и размера, что у работ."""

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data] if data else []
        cleaned = []
        for upload in files:
            upload = super().clean(upload, initial)
            if Path(upload.name).suffix.lower().lstrip(".") not in PUBLIC_DOCUMENT_EXTENSIONS:
                raise forms.ValidationError(f"«{upload.name}»: такой тип файла не подходит. Подойдут PDF, Word, Excel, картинки, ZIP.")
            if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
                raise forms.ValidationError(f"«{upload.name}» больше {settings.MAX_UPLOAD_MB} МБ.")
            cleaned.append(upload)
        return cleaned


class NewsPostForm(forms.ModelForm):
    remove_files = forms.ModelMultipleChoiceField(
        label="Документы новости", queryset=NewsAttachment.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple, help_text="Отметьте документы, которые нужно удалить.",
    )
    files = MultipleDocumentField(
        label="Добавить документы", required=False,
        help_text="Можно выбрать несколько сразу. Их можно будет скачать со страницы новости.",
    )

    class Meta:
        model = NewsPost
        fields = ["title", "text", "cover", "published_at", "is_published"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 10}),
            "published_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.old_cover = self.instance.cover.name if self.instance.pk else ""
        if self.instance.pk and self.instance.attachments.exists():
            self.fields["remove_files"].queryset = self.instance.attachments.all()
        else:
            del self.fields["remove_files"]

    def clean_cover(self):
        cover = self.cleaned_data.get("cover")
        return prepare_photo(cover) if isinstance(cover, UploadedFile) else cover

    def save(self, commit=True):
        post = super().save(commit)
        if self.old_cover and post.cover.name != self.old_cover:
            post.cover.storage.delete(self.old_cover)  # заменённая или удалённая картинка
        for attachment in self.cleaned_data.get("remove_files") or []:
            attachment.delete()  # файл удаляет сигнал post_delete
        for upload in self.cleaned_data.get("files") or []:
            NewsAttachment.objects.create(news=post, title=Path(upload.name).stem[:255], file=upload)
        return post


class FaqItemForm(forms.ModelForm):
    class Meta:
        model = FaqItem
        fields = ["question", "answer", "order", "is_published"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 6})}


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "description", "file", "order", "is_published"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.old_file = self.instance.file.name if self.instance.pk else ""

    def save(self, commit=True):
        document = super().save(commit)
        # Заменённый файл убираем с диска.
        if self.old_file and document.file.name != self.old_file:
            document.file.storage.delete(self.old_file)
        return document


class LookupForm(forms.Form):
    snils = forms.CharField(label="СНИЛС участника", max_length=20)
    email = forms.EmailField(
        label="Электронная почта участника", help_text="Та, что указана в анкете в блоке «Участник»."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["snils"].widget.attrs.update(
            {"inputmode": "numeric", "placeholder": "123-456-789 01", "autocomplete": "off", "data-snils": ""}
        )
        self.fields["email"].widget.attrs.update({"placeholder": "name@example.ru", "autocomplete": "email"})

    def clean_snils(self):
        return clean_snils(self.cleaned_data["snils"])


class SubmissionChecks:
    """Проверки полей заявки — общие для анкеты участника и формы в кабинете."""

    @staticmethod
    def _check_phone(value):
        phone = value.strip()
        if phone and (not re.fullmatch(r"[\d\s()+\-]+", phone) or len(re.sub(r"\D", "", phone)) < 10):
            raise forms.ValidationError("Укажите телефон полностью, например +7 900 000-00-00.")
        return phone

    def clean_snils(self):
        return clean_snils(self.cleaned_data["snils"])

    def clean_coauthor_snils(self):
        return clean_snils(self.cleaned_data["coauthor_snils"])

    def clean_supervisor_phone(self):
        return self._check_phone(self.cleaned_data["supervisor_phone"])

    def clean_supervisor2_phone(self):
        return self._check_phone(self.cleaned_data["supervisor2_phone"])

    def _check_file(self, name, extensions, what):
        file = self.cleaned_data[name]
        if not isinstance(file, UploadedFile):
            return file  # при редактировании файл не меняли
        if Path(file.name).suffix.lower() not in extensions:
            raise forms.ValidationError(f"Недопустимый формат. Загрузите {what} в {formats(extensions)}.")
        if file.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"Файл больше {settings.MAX_UPLOAD_MB} МБ.")
        return file

    def clean_file(self):
        return self._check_file("file", ALLOWED_EXTENSIONS, "текст работы")

    def clean_application_file(self):
        return self._check_file("application_file", DOCUMENT_EXTENSIONS, "заявку")

    def clean_consent_file(self):
        return self._check_file("consent_file", DOCUMENT_EXTENSIONS, "согласие")


class SubmissionForm(SubmissionChecks, forms.ModelForm):
    # Поле скрыто от людей через CSS; боты его заполняют, и такие заявки не сохраняются.
    website = forms.CharField(required=False, label="Не заполняйте это поле")
    consent = forms.BooleanField(required=True)
    section_slot = forms.ChoiceField(label="Секция", widget=SlotSelect)

    class Meta:
        model = Submission
        fields = [
            "email",
            "district",
            "school",
            "last_name",
            "first_name",
            "grade",
            "snils",
            "title",
            "coauthor_last_name",
            "coauthor_first_name",
            "coauthor_grade",
            "coauthor_snils",
            "supervisor_last_name",
            "supervisor_first_name",
            "supervisor_middle_name",
            "supervisor_position",
            "supervisor_phone",
            "supervisor2_last_name",
            "supervisor2_first_name",
            "supervisor2_middle_name",
            "supervisor2_position",
            "supervisor2_phone",
            "file",
            "application_file",
            "consent_file",
        ]
        labels = {
            "email": "Электронная почта участника",
            "district": "Муниципальный район",
            "school": "Полное название образовательной организации",
            "title": "Название научно-исследовательской работы",
            "file": "Текст работы",
            "application_file": "Заявка на участие",
            "consent_file": "Согласие на обработку персональных данных",
            "coauthor_last_name": "Фамилия соавтора",
            "coauthor_first_name": "Имя соавтора",
            "coauthor_grade": "Класс соавтора",
            "coauthor_snils": "СНИЛС соавтора",
            "supervisor_last_name": "Фамилия",
            "supervisor_first_name": "Имя",
            "supervisor_middle_name": "Отчество",
            "supervisor_position": "Должность",
            "supervisor_phone": "Контактный телефон",
            "supervisor2_last_name": "Фамилия",
            "supervisor2_first_name": "Имя",
            "supervisor2_middle_name": "Отчество",
            "supervisor2_position": "Должность",
            "supervisor2_phone": "Контактный телефон",
        }
        help_texts = {
            "snils": "Формат: 123-456-789 01",
            "coauthor_snils": "Формат: 123-456-789 01",
            "school": "Как в уставе (в соответствии с ЕГРЮЛ), без сокращений",
            "district": "Например: Ленинский район г. Саратова",
        }
        widgets = {
            "grade": forms.Select(choices=GRADE_CHOICES),
            "coauthor_grade": forms.Select(choices=GRADE_CHOICES),
            "file": forms.FileInput,
            "application_file": forms.FileInput,
            "consent_file": forms.FileInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        conf = ConferenceSettings.load()
        max_mb = settings.MAX_UPLOAD_MB
        self.editing = bool(self.instance.pk)

        slots = section_slots(exclude=self.instance.pk)
        if self.editing:
            # Текущая секция заявки остаётся в списке, даже если по очереди сейчас открыта другая.
            current = f"{self.instance.section_id}:{self.instance.section_number}"
            if current not in {value for value, *_ in slots}:
                section, number = self.instance.section, self.instance.section_number
                free = section.free_places(self.instance.pk).get(number, 0)
                slots.append((current, slot_label(section, number, free), free, section, number))
            self.initial.setdefault("section_slot", current)
        self.slots = {value: (free, section, number) for value, _, free, section, number in slots}
        slot_field = self.fields["section_slot"]
        slot_field.choices = [("", "— выберите секцию —")] + [(value, label) for value, label, *_ in slots]
        slot_field.widget.disabled_values = {v for v, (free, *_) in self.slots.items() if not free}
        slot_field.help_text = "Число мест в секции ограничено. Секции одного направления открываются по очереди: следующая появляется, когда предыдущая заполнена."
        slot_field.error_messages["invalid_choice"] = (
            "Эта секция уже заполнена или недоступна. Выберите секцию из списка заново."
        )

        work_help = f"{formats(ALLOWED_EXTENSIONS)}, до {max_mb} МБ. Презентации и видео не принимаются."
        self.fields["file"].help_text = work_help
        if conf.requirements_links:
            self.fields["file"].help_text = format_html(
                '<a href="{}" class="blank-link">Требования к работе</a> · {}',
                reverse("conference:blank", args=[conf.requirements_links[0][1]]),
                work_help,
            )
        self.fields["file"].widget.attrs.update({"accept": ",".join(ALLOWED_EXTENSIONS), "data-max-mb": max_mb})

        scan_help = f"Скан или фото с подписью: {formats(DOCUMENT_EXTENSIONS)}, до {max_mb} МБ. Несколько страниц — соберите в один PDF."
        for name, links in (
            ("application_file", conf.application_links),
            ("consent_file", conf.consent_links),
        ):
            field = self.fields[name]
            field.required = True
            field.widget.attrs.update({"accept": ",".join(DOCUMENT_EXTENSIONS), "data-max-mb": max_mb})
            field.help_text = scan_help
            if links:
                anchors = format_html_join(
                    " · ",
                    '<a href="{}" class="blank-link">Скачать бланк ({})</a>',
                    ((reverse("conference:blank", args=[kind]), label) for label, kind in links),
                )
                field.help_text = format_html("{} · {}", anchors, scan_help)

        self.fields["website"].widget.attrs.update({"tabindex": "-1", "autocomplete": "off"})
        self.fields["email"].widget.attrs.update({"placeholder": "name@example.ru", "autocomplete": "off"})
        self.fields["snils"].required = True
        for name in ("snils", "coauthor_snils"):
            self.fields[name].widget.attrs.update(
                {"inputmode": "numeric", "placeholder": "123-456-789 01", "autocomplete": "off", "data-snils": ""}
            )
        for name in ("supervisor_phone", "supervisor2_phone"):
            self.fields[name].widget.attrs.update(
                {"type": "tel", "inputmode": "tel", "placeholder": "+7 (900) 000-00-00", "data-phone": ""}
            )
        if self.editing:
            # Файлы уже загружены: новый нужен, только если его хотят заменить. Согласие дано при подаче.
            for name, original in (
                ("file", self.instance.original_filename),
                ("application_file", self.instance.application_original_filename),
                ("consent_file", self.instance.consent_original_filename),
            ):
                field = self.fields[name]
                field.required = False
                field.help_text = format_html(
                    "Сейчас загружен: <b>{}</b>. Выберите новый файл, только если нужно заменить. {}",
                    original or "файл",
                    field.help_text,
                )
            self.fields["consent"].required = False
        self.fields["consent"].label = format_html(
            "Подтверждаю согласие родителя (законного представителя) участника на обработку персональных данных "
            'в соответствии с <a href="{}" target="_blank">политикой</a>',
            reverse("conference:privacy"),
        )

    @property
    def is_spam(self):
        return bool(self.cleaned_data.get("website"))

    @property
    def has_sections(self):
        return bool(self.slots)

    @property
    def has_free(self):
        return any(free for free, *_ in self.slots.values())

    def clean(self):
        cleaned = super().clean()
        slot = cleaned.get("section_slot")
        if slot:
            free, section, number = self.slots[slot]
            if not free:
                self.add_error("section_slot", "Эта секция уже заполнена — выберите другую.")
            else:
                self.instance.section, self.instance.section_number = section, number
                snils = cleaned.get("snils")
                duplicate = (
                    Submission.objects.filter(snils=snils, section=section)
                    .exclude(admission=Submission.Admission.NOT_ADMITTED)
                    .exclude(pk=self.instance.pk)
                )
                if snils and duplicate.exists():
                    self.add_error("section_slot", duplicate_message(section))
        # Соавтор необязателен, но если он указан — нужны все три поля.
        coauthor_fields = ("coauthor_last_name", "coauthor_first_name", "coauthor_grade", "coauthor_snils")
        if any(cleaned.get(name) for name in coauthor_fields):
            for name in coauthor_fields:
                if not cleaned.get(name) and name not in self.errors:
                    self.add_error(name, "Заполните, если у работы есть соавтор.")
        # Второй руководитель необязателен, но если он указан — нужны ФИО (без отчества), должность и телефон.
        if any(cleaned.get(name) for name in (*SUPERVISOR2_FIELDS, "supervisor2_middle_name")):
            for name in SUPERVISOR2_FIELDS:
                if not cleaned.get(name) and name not in self.errors:
                    self.add_error(name, "Заполните, если у работы два руководителя.")
        return cleaned

    def save(self, commit=True):
        if commit:
            with transaction.atomic():
                # Повторная проверка мест прямо перед записью: пока заполняли анкету,
                # секцию могли занять другие.
                section = Section.objects.select_for_update().get(pk=self.instance.section_id)
                if not section.free_places(self.instance.pk).get(self.instance.section_number, 0):
                    raise SectionFull
                return self._save()
        return self._save(commit=False)

    def _save(self, commit=True):
        submission = super().save(commit=False)
        for name, original in (
            ("file", "original_filename"),
            ("application_file", "application_original_filename"),
            ("consent_file", "consent_original_filename"),
        ):
            if isinstance(self.cleaned_data[name], UploadedFile):
                setattr(submission, original, Path(self.cleaned_data[name].name).name[:255])
        if self.editing:
            submission.edited_by_participant_at = timezone.now()
        if commit:
            submission.save()
        return submission

    @property
    def has_supervisor2(self):
        names = (*SUPERVISOR2_FIELDS, "supervisor2_middle_name")
        return any(self[name].value() or self[name].errors for name in names)

    @property
    def has_coauthor(self):
        names = ("coauthor_last_name", "coauthor_first_name", "coauthor_grade", "coauthor_snils")
        return any(self[name].value() or self[name].errors for name in names)


# Кабинет: правка данных заявки сотрудником (без выбора секции — перенос отдельной формой).
OFFICE_SUBMISSION_FIELDSETS = [
    ("Участник", ["last_name", "first_name", "grade", "snils", "email", "school", "district"]),
    ("Работа", ["title", "file", "application_file", "consent_file"]),
    ("Соавтор", ["coauthor_last_name", "coauthor_first_name", "coauthor_grade", "coauthor_snils"]),
    ("Руководитель", ["supervisor_last_name", "supervisor_first_name", "supervisor_middle_name",
                      "supervisor_position", "supervisor_phone"]),
    ("Второй руководитель", ["supervisor2_last_name", "supervisor2_first_name", "supervisor2_middle_name",
                             "supervisor2_position", "supervisor2_phone"]),
    ("Оргкомитет", ["participant_message", "admin_comment"]),
]
SUBMISSION_FILE_FIELDS = {
    "file": ("original_filename", "work"),
    "application_file": ("application_original_filename", "application"),
    "consent_file": ("consent_original_filename", "consent"),
}


class OfficeSubmissionForm(SubmissionChecks, forms.ModelForm):
    class Meta:
        model = Submission
        fields = [name for _, names in OFFICE_SUBMISSION_FIELDSETS for name in names]
        widgets = {
            "participant_message": forms.Textarea(attrs={"rows": 3}),
            "admin_comment": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"email": "Электронная почта участника", "school": "Образовательная организация"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["snils"].required = True
        # Загруженный файл можно заменить, но не удалить: работа без файла не нужна.
        for name in SUBMISSION_FILE_FIELDS:
            self.fields[name].required = bool(getattr(self.instance, name))
        self.old_files = {name: getattr(self.instance, name).name for name in SUBMISSION_FILE_FIELDS}

    def clean(self):
        cleaned = super().clean()
        coauthor_fields = ("coauthor_last_name", "coauthor_first_name", "coauthor_grade", "coauthor_snils")
        if any(cleaned.get(name) for name in coauthor_fields):
            for name in coauthor_fields:
                if not cleaned.get(name) and name not in self.errors:
                    self.add_error(name, "Заполните, если у работы есть соавтор.")
        return cleaned

    def save(self, commit=True):
        submission = super().save(commit=False)
        for name, (original, _) in SUBMISSION_FILE_FIELDS.items():
            if isinstance(self.cleaned_data.get(name), UploadedFile):
                setattr(submission, original, Path(self.cleaned_data[name].name).name[:255])
        if commit:
            submission.save()
            for name, old in self.old_files.items():
                if old and getattr(submission, name).name != old:
                    getattr(submission, name).storage.delete(old)  # заменённый файл
        return submission


class MoveSubmissionForm(forms.Form):
    """Перенос работы в другую секцию. Заполненная секция не запрещена — решает оргкомитет."""

    slot = forms.ChoiceField(label="Перенести в секцию")

    def __init__(self, *args, submission, **kwargs):
        super().__init__(*args, **kwargs)
        self.submission = submission
        choices = []
        for section in Section.objects.all():
            taken = section.occupied(exclude=submission.pk)
            for number in range(1, section.groups + 1):
                label = f"{section.group_label(number)} — занято {taken[number]} из {section.capacity}"
                if not section.is_active:
                    label += " (скрыта в анкете)"
                choices.append((f"{section.pk}:{number}", label))
        self.fields["slot"].choices = choices
        self.fields["slot"].initial = f"{submission.section_id}:{submission.section_number}"

    def clean_slot(self):
        section_id, number = (int(part) for part in self.cleaned_data["slot"].split(":"))
        section = Section.objects.get(pk=section_id)
        snils = self.submission.snils
        if (
            section_id != self.submission.section_id
            and snils
            and Submission.objects.filter(snils=snils, section=section)
            .exclude(admission=Submission.Admission.NOT_ADMITTED)
            .exclude(pk=self.submission.pk)
            .exists()
        ):
            raise forms.ValidationError(f"У этого участника уже есть работа в направлении «{section}».")
        return section, number

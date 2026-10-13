import re
from pathlib import Path

from django import forms
from django.conf import settings
from django.urls import reverse
from django.db import transaction
from django.utils.html import format_html, format_html_join

from .models import GRADE_MAX, GRADE_MIN, ConferenceSettings, Section, Submission

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


def section_slots():
    """[(значение «pk:номер», подпись, свободно мест, направление, номер)] для активных направлений."""
    slots = []
    for section in Section.objects.filter(is_active=True):
        free_by_number = section.free_places()
        # Секции направления заполняются по очереди: предлагаем первую, где ещё есть места.
        # Следующая появляется, когда предыдущая заполнена. Если заполнены все — последнюю, как «мест нет».
        number = next((n for n, free in free_by_number.items() if free), max(free_by_number))
        free = free_by_number[number]
        label = section.group_label(number)
        label += f" — свободно {places(free)}" if free else " — мест нет"
        slots.append((f"{section.pk}:{number}", label, free, section, number))
    return slots


def formats(extensions):
    return ", ".join(dict.fromkeys(ext.lstrip(".").upper().replace("JPEG", "JPG") for ext in extensions))


class SectionFull(Exception):
    """Секцию заняли, пока участник заполнял анкету."""


class SubmissionForm(forms.ModelForm):
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
            "title",
            "coauthor_last_name",
            "coauthor_first_name",
            "coauthor_grade",
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
            "links_email",
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
            "links_email": "Почта для ссылок на тестирование и второй этап",
        }
        help_texts = {
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

        slots = section_slots()
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
        for name in ("email", "links_email"):
            self.fields[name].widget.attrs.update({"placeholder": "name@example.ru", "autocomplete": "off"})
        for name in ("supervisor_phone", "supervisor2_phone"):
            self.fields[name].widget.attrs.update(
                {"type": "tel", "inputmode": "tel", "placeholder": "+7 (900) 000-00-00", "data-phone": ""}
            )
        self.fields["consent"].label = format_html(
            "Подтверждаю согласие родителя (законного представителя) участника на обработку персональных данных "
            'в соответствии с <a href="{}" target="_blank">политикой</a>',
            reverse("conference:privacy"),
        )

    @property
    def is_spam(self):
        return bool(self.cleaned_data.get("website"))

    @staticmethod
    def _check_phone(value):
        phone = value.strip()
        if phone and (not re.fullmatch(r"[\d\s()+\-]+", phone) or len(re.sub(r"\D", "", phone)) < 10):
            raise forms.ValidationError("Укажите телефон полностью, например +7 900 000-00-00.")
        return phone

    def clean_supervisor_phone(self):
        return self._check_phone(self.cleaned_data["supervisor_phone"])

    def clean_supervisor2_phone(self):
        return self._check_phone(self.cleaned_data["supervisor2_phone"])

    def _check_file(self, name, extensions, what):
        file = self.cleaned_data[name]
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
            need = 2 if cleaned.get("coauthor_last_name") else 1
            if need > free:
                self.add_error(
                    "section_slot",
                    "Эта секция уже заполнена — выберите другую."
                    if not free
                    else f"В секции осталось {places(free)}, а с соавтором нужно два. Подайте работу без соавтора или выберите другую секцию.",
                )
            else:
                self.instance.section, self.instance.section_number = section, number
        # Соавтор необязателен, но если он указан — нужны все три поля.
        coauthor_fields = ("coauthor_last_name", "coauthor_first_name", "coauthor_grade")
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
                if section.free_places().get(self.instance.section_number, 0) < (
                    2 if self.cleaned_data.get("coauthor_last_name") else 1
                ):
                    raise SectionFull
                return self._save()
        return self._save(commit=False)

    def _save(self, commit=True):
        submission = super().save(commit=False)
        submission.original_filename = Path(self.cleaned_data["file"].name).name[:255]
        submission.application_original_filename = Path(self.cleaned_data["application_file"].name).name[:255]
        submission.consent_original_filename = Path(self.cleaned_data["consent_file"].name).name[:255]
        if commit:
            submission.save()
        return submission

    @property
    def has_supervisor2(self):
        names = (*SUPERVISOR2_FIELDS, "supervisor2_middle_name")
        return any(self[name].value() or self[name].errors for name in names)

    @property
    def has_coauthor(self):
        names = ("coauthor_last_name", "coauthor_first_name", "coauthor_grade")
        return any(self[name].value() or self[name].errors for name in names)

import re
from pathlib import Path

from django import forms
from django.conf import settings
from django.urls import reverse
from django.utils.html import format_html

from .models import Section, Submission

# Только текстовые документы: без презентаций и видео.
ALLOWED_EXTENSIONS = (".pdf", ".doc", ".docx", ".odt", ".rtf")
GRADE_CHOICES = [("", "—")] + [(n, str(n)) for n in range(1, 12)]


class SubmissionForm(forms.ModelForm):
    # Поле скрыто от людей через CSS; боты его заполняют, и такие заявки не сохраняются.
    website = forms.CharField(required=False, label="Не заполняйте это поле")
    consent = forms.BooleanField(required=True)

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
            "section",
            "coauthor_last_name",
            "coauthor_first_name",
            "coauthor_grade",
            "supervisor_last_name",
            "supervisor_first_name",
            "supervisor_middle_name",
            "supervisor_position",
            "supervisor_phone",
            "links_email",
            "file",
        ]
        labels = {
            "email": "Электронная почта участника",
            "district": "Муниципальный район",
            "school": "Образовательная организация",
            "title": "Название научно-исследовательской работы",
            "section": "Межпредметное направление (секция)",
            "coauthor_last_name": "Фамилия соавтора",
            "coauthor_first_name": "Имя соавтора",
            "coauthor_grade": "Класс соавтора",
            "supervisor_last_name": "Фамилия",
            "supervisor_first_name": "Имя",
            "supervisor_middle_name": "Отчество",
            "supervisor_position": "Должность",
            "supervisor_phone": "Контактный телефон",
            "links_email": "Почта для ссылок на тестирование и второй этап",
        }
        help_texts = {
            "school": "Краткое название, например: МАОУ «Гимназия № 87»",
            "district": "Например: Ленинский район г. Саратова",
        }
        widgets = {
            "grade": forms.Select(choices=GRADE_CHOICES),
            "coauthor_grade": forms.Select(choices=GRADE_CHOICES),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["section"].queryset = Section.objects.filter(is_active=True)
        self.fields["section"].empty_label = "— выберите направление —"
        self.fields["file"].help_text = (
            f"Текст работы в формате {', '.join(ext.lstrip('.').upper() for ext in ALLOWED_EXTENSIONS)}, "
            f"до {settings.MAX_UPLOAD_MB} МБ. Презентации и видео не принимаются."
        )
        self.fields["file"].widget.attrs.update(
            {"accept": ",".join(ALLOWED_EXTENSIONS), "data-max-mb": settings.MAX_UPLOAD_MB}
        )
        self.fields["website"].widget.attrs.update({"tabindex": "-1", "autocomplete": "off"})
        for name in ("email", "links_email"):
            self.fields[name].widget.attrs["placeholder"] = "name@example.ru"
        self.fields["supervisor_phone"].widget.attrs.update({"type": "tel", "placeholder": "+7 900 000-00-00"})
        self.fields["consent"].label = format_html(
            "Подтверждаю согласие родителя (законного представителя) участника на обработку персональных данных "
            'в соответствии с <a href="{}" target="_blank">политикой</a>',
            reverse("conference:privacy"),
        )

    @property
    def is_spam(self):
        return bool(self.cleaned_data.get("website"))

    def clean_supervisor_phone(self):
        phone = self.cleaned_data["supervisor_phone"].strip()
        if not re.fullmatch(r"[\d\s()+\-]+", phone) or len(re.sub(r"\D", "", phone)) < 10:
            raise forms.ValidationError("Укажите телефон полностью, например +7 900 000-00-00.")
        return phone

    def clean_file(self):
        file = self.cleaned_data["file"]
        if Path(file.name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                "Недопустимый формат. Загрузите текст работы в PDF, DOC, DOCX, ODT или RTF."
            )
        if file.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"Файл больше {settings.MAX_UPLOAD_MB} МБ.")
        return file

    def clean(self):
        cleaned = super().clean()
        # Соавтор необязателен, но если он указан — нужны все три поля.
        coauthor_fields = ("coauthor_last_name", "coauthor_first_name", "coauthor_grade")
        if any(cleaned.get(name) for name in coauthor_fields):
            for name in coauthor_fields:
                if not cleaned.get(name) and name not in self.errors:
                    self.add_error(name, "Заполните, если у работы есть соавтор.")
        return cleaned

    def save(self, commit=True):
        submission = super().save(commit=False)
        submission.original_filename = Path(self.cleaned_data["file"].name).name[:255]
        if commit:
            submission.save()
        return submission

"""Статусы заявки («Новая», «Принята», «На доработке», «Отклонена») заменены допуском ко 2 этапу."""

import django.core.validators
from django.db import migrations, models

STATUS_TO_ADMISSION = {"accepted": "admitted", "rejected": "not_admitted"}


def forwards(apps, schema_editor):
    Submission = apps.get_model("conference", "Submission")
    for status, admission in STATUS_TO_ADMISSION.items():
        Submission.objects.filter(status=status).update(admission=admission)


def backwards(apps, schema_editor):
    Submission = apps.get_model("conference", "Submission")
    for status, admission in STATUS_TO_ADMISSION.items():
        Submission.objects.filter(admission=admission).update(status=status)


class Migration(migrations.Migration):
    dependencies = [
        ("conference", "0013_remove_links_email"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="submission",
            name="one_active_submission_per_snils_and_section",
        ),
        migrations.AddField(
            model_name="submission",
            name="admission",
            field=models.CharField(
                blank=True,
                choices=[("", "Не решено"), ("admitted", "Допущен"), ("not_admitted", "Не допущен")],
                default="",
                max_length=12,
                verbose_name="допуск ко 2 этапу",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name="submission",
            name="status",
        ),
        migrations.AddConstraint(
            model_name="submission",
            constraint=models.UniqueConstraint(
                condition=models.Q(("admission", "not_admitted"), _negated=True) & models.Q(("snils", ""), _negated=True),
                fields=("snils", "section"),
                name="one_active_submission_per_snils_and_section",
                violation_error_message="Заявка этого участника в это направление уже есть.",
            ),
        ),
        migrations.AlterField(
            model_name="section",
            name="capacity",
            field=models.PositiveSmallIntegerField(
                default=12,
                help_text="Участник и соавтор занимают по месту. Удалённая участником заявка место освобождает.",
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="мест в секции",
            ),
        ),
    ]

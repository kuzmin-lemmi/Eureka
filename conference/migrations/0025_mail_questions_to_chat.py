from django.db import migrations

OLD = "Если появятся вопросы, напишите нам: {contact}"
NEW = "Если появятся вопросы, пишите {contact}."


def forward(apps, schema_editor):
    ConferenceSettings = apps.get_model("conference", "ConferenceSettings")
    for conf in ConferenceSettings.objects.all():
        if OLD in conf.mail_admitted_body:
            conf.mail_admitted_body = conf.mail_admitted_body.replace(OLD, NEW)
            conf.save(update_fields=["mail_admitted_body"])


class Migration(migrations.Migration):
    dependencies = [("conference", "0024_mailing")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]

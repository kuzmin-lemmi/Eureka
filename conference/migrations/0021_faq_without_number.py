from django.db import migrations

OLD = (
    "После отправки сайт покажет номер заявки, например № 0001. Все поданные работы видны в разделе «Мои заявки» — "
    "войти можно по СНИЛС участника и почте, указанной в анкете."
)
NEW = (
    "После отправки сайт покажет «Работа отправлена!», а работа сразу появится в разделе «Мои заявки» — "
    "войти можно по СНИЛС участника и почте, указанной в анкете."
)


def forwards(apps, schema_editor):
    apps.get_model("conference", "FaqItem").objects.filter(answer=OLD).update(answer=NEW)


def backwards(apps, schema_editor):
    apps.get_model("conference", "FaqItem").objects.filter(answer=NEW).update(answer=OLD)


class Migration(migrations.Migration):
    dependencies = [("conference", "0020_faq")]
    operations = [migrations.RunPython(forwards, backwards)]

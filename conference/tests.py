import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .apps import ORGANIZERS_GROUP
from .models import ConferenceSettings, Section, Submission

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT, MAX_UPLOAD_MB=1)
class SubmissionTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.section = Section.objects.create(name="Естественные науки")

    def post(self, **overrides):
        data = {
            "email": "pupil@example.ru",
            "district": "Ленинский район",
            "school": "Гимназия № 87",
            "last_name": "Иванова",
            "first_name": "Мария",
            "grade": "7",
            "title": "Маятник Фуко в домашних условиях",
            "section": self.section.pk,
            "supervisor_last_name": "Петрова",
            "supervisor_first_name": "Анна",
            "supervisor_position": "учитель физики",
            "supervisor_phone": "+7 900 123-45-67",
            "links_email": "parent@example.ru",
            "file": SimpleUploadedFile("работа.docx", b"PK test", content_type="application/octet-stream"),
            "consent": "on",
            **overrides,
        }
        return self.client.post(reverse("conference:submit"), data)

    def test_valid_submission_is_saved(self):
        response = self.post()
        self.assertRedirects(response, reverse("conference:thanks"))
        submission = Submission.objects.get()
        self.assertEqual(submission.status, Submission.Status.NEW)
        self.assertEqual(submission.grade, 7)
        self.assertEqual(submission.original_filename, "работа.docx")
        self.assertNotIn("работа", submission.file.name)
        self.assertEqual(submission.coauthor, "")

        thanks = self.client.get(reverse("conference:thanks"))
        self.assertContains(thanks, submission.number)

    def test_presentation_rejected(self):
        self.post(file=SimpleUploadedFile("slides.pptx", b"PK"))
        self.assertFalse(Submission.objects.exists())

    def test_video_rejected(self):
        response = self.post(file=SimpleUploadedFile("video.mp4", b"\x00"))
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, "Недопустимый формат")

    def test_too_large_file_rejected(self):
        response = self.post(file=SimpleUploadedFile("big.pdf", b"0" * (1024 * 1024 + 1)))
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, "Файл больше 1 МБ")

    def test_grade_out_of_range_rejected(self):
        self.post(grade="12")
        self.assertFalse(Submission.objects.exists())

    def test_partial_coauthor_rejected(self):
        response = self.post(coauthor_last_name="Сидоров")
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, "Заполните, если у работы есть соавтор.", count=2)

    def test_full_coauthor_saved(self):
        self.post(coauthor_last_name="Сидоров", coauthor_first_name="Пётр", coauthor_grade="8")
        self.assertEqual(Submission.objects.get().coauthor, "Сидоров Пётр, 8 класс")

    def test_supervisor_middle_name_optional(self):
        self.post(supervisor_middle_name="")
        self.assertEqual(Submission.objects.get().supervisor, "Петрова Анна")

    def test_bad_supervisor_phone_rejected(self):
        self.post(supervisor_phone="123")
        self.assertFalse(Submission.objects.exists())

    def test_consent_required(self):
        self.post(consent="")
        self.assertFalse(Submission.objects.exists())

    def test_inactive_section_not_allowed(self):
        hidden = Section.objects.create(name="Скрытая", is_active=False)
        self.post(section=hidden.pk)
        self.assertFalse(Submission.objects.exists())

    def test_closed_after_deadline(self):
        conf = ConferenceSettings.load()
        conf.submissions_deadline = timezone.now() - timedelta(minutes=1)
        conf.save()
        response = self.post()
        self.assertContains(response, "Приём работ закрыт")
        self.assertFalse(Submission.objects.exists())

    def test_honeypot_discards_spam(self):
        response = self.post(website="http://spam.example")
        self.assertRedirects(response, reverse("conference:thanks"))
        self.assertFalse(Submission.objects.exists())

    def test_file_download_requires_staff(self):
        self.post()
        url = reverse("conference:download_submission", args=[Submission.objects.get().pk])

        self.assertEqual(self.client.get(url).status_code, 302)

        staff = User.objects.create_user("org", password="pass", is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])


class OrganizersTests(TestCase):
    def test_organizer_can_manage_submissions_but_not_users(self):
        organizer = User.objects.create_user("org", password="pass", is_staff=True)
        organizer.groups.add(Group.objects.get(name=ORGANIZERS_GROUP))
        self.client.force_login(organizer)

        self.assertEqual(self.client.get(reverse("admin:conference_submission_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:conference_section_add")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:auth_user_changelist")).status_code, 403)


class PagesTests(TestCase):
    def test_home_shows_active_sections_only(self):
        Section.objects.create(name="Биология")
        Section.objects.create(name="Секретная", is_active=False)
        response = self.client.get(reverse("conference:home"))
        self.assertContains(response, "Биология")
        self.assertNotContains(response, "Секретная")

    def test_settings_admin_opens_single_record(self):
        admin = User.objects.create_superuser("admin", password="pass")
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:conference_conferencesettings_changelist"))
        self.assertRedirects(response, reverse("admin:conference_conferencesettings_change", args=[1]))

import os
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .apps import ORGANIZERS_GROUP
from .models import ConferenceSettings, Document, NewsPost, Section, Submission

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
            "grade": "9",
            "title": "Маятник Фуко в домашних условиях",
            "section_slot": f"{self.section.pk}:1",
            "supervisor_last_name": "Петрова",
            "supervisor_first_name": "Анна",
            "supervisor_position": "учитель физики",
            "supervisor_phone": "+7 900 123-45-67",
            "links_email": "parent@example.ru",
            "file": SimpleUploadedFile("работа.docx", b"PK test", content_type="application/octet-stream"),
            "application_file": SimpleUploadedFile("заявка.pdf", b"%PDF-1.4"),
            "consent_file": SimpleUploadedFile("IMG_0001.JPG", b"JPEG test"),
            "consent": "on",
            **overrides,
        }
        return self.client.post(reverse("conference:submit"), data)

    def test_valid_submission_is_saved(self):
        response = self.post()
        self.assertRedirects(response, reverse("conference:thanks"))
        submission = Submission.objects.get()
        self.assertEqual(submission.status, Submission.Status.NEW)
        self.assertEqual(submission.grade, 9)
        self.assertEqual(submission.original_filename, "работа.docx")
        self.assertNotIn("работа", submission.file.name)
        self.assertEqual(submission.coauthor, "")
        self.assertEqual(submission.application_original_filename, "заявка.pdf")
        self.assertEqual(submission.consent_original_filename, "IMG_0001.JPG")
        self.assertTrue(submission.consent_file.name.startswith("documents/"))

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

    def test_documents_required(self):
        self.post(application_file="", consent_file="")
        self.assertFalse(Submission.objects.exists())

    def test_document_must_be_scan(self):
        response = self.post(consent_file=SimpleUploadedFile("согласие.docx", b"PK"))
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, "Загрузите согласие в PDF, JPG, PNG")

    def test_more_prefills_school_and_supervisor(self):
        self.post()
        response = self.client.get(reverse("conference:submit") + "?more=1")
        self.assertContains(response, 'value="Гимназия № 87"')
        self.assertContains(response, 'value="Петрова"')
        self.assertNotContains(response, 'value="Иванова"')
        # Без ?more анкета пустая.
        self.assertNotContains(self.client.get(reverse("conference:submit")), 'value="Петрова"')

    def test_section_groups_are_numbered(self):
        self.section.groups = 3
        self.section.save()
        response = self.client.get(reverse("conference:submit"))
        self.assertContains(response, "Естественные науки 2 — свободно 15 мест")
        self.post(section_slot=f"{self.section.pk}:3")
        submission = Submission.objects.get()
        self.assertEqual(submission.section_number, 3)
        self.assertEqual(submission.section_label, "Естественные науки 3")

    def test_group_number_out_of_range_rejected(self):
        self.post(section_slot=f"{self.section.pk}:2")
        self.assertFalse(Submission.objects.exists())

    def test_full_section_is_disabled_and_rejected(self):
        self.section.capacity = 1
        self.section.save()
        self.post()
        self.assertEqual(Submission.objects.count(), 1)

        response = self.client.get(reverse("conference:submit"))
        self.assertContains(response, "Естественные науки — мест нет")
        self.assertContains(response, "disabled")

        response = self.post(last_name="Петров")
        self.assertContains(response, "Эта секция уже заполнена")
        self.assertEqual(Submission.objects.count(), 1)

    def test_coauthor_takes_a_place(self):
        self.section.capacity = 2
        self.section.save()
        self.post(coauthor_last_name="Сидоров", coauthor_first_name="Пётр", coauthor_grade="8")
        self.assertEqual(self.section.free_places(), {1: 0})

        self.section.capacity = 3
        self.section.save()
        response = self.post(coauthor_last_name="Орлов", coauthor_first_name="Иван", coauthor_grade="8")
        self.assertContains(response, "осталось 1 место")
        self.assertEqual(Submission.objects.count(), 1)

    def test_rejected_submission_frees_place(self):
        self.section.capacity = 1
        self.section.save()
        self.post()
        Submission.objects.update(status=Submission.Status.REJECTED)
        self.post(last_name="Петров")
        self.assertEqual(Submission.objects.count(), 2)

    def test_grade_out_of_range_rejected(self):
        for grade in ("7", "12"):
            self.post(grade=grade)
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
        self.post(section_slot=f"{hidden.pk}:1")
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

        pk = Submission.objects.get().pk
        consent_url = reverse("conference:download_submission_file", args=[pk, "consent"])
        response = self.client.get(consent_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"{pk:04d}", response["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("conference:download_submission_file", args=[pk, "x"])).status_code, 404)

        self.client.logout()
        self.assertEqual(self.client.get(consent_url).status_code, 302)

    def test_blank_is_public(self):
        self.assertEqual(self.client.get(reverse("conference:blank", args=["consent"])).status_code, 404)
        conf = ConferenceSettings.load()
        conf.consent_template = SimpleUploadedFile("согласие.docx", b"PK blank")
        conf.save()
        response = self.client.get(reverse("conference:blank", args=["consent"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertContains(self.client.get(reverse("conference:submit")), reverse("conference:blank", args=["consent"]))


class OrganizersTests(TestCase):
    def test_organizer_can_manage_submissions_but_not_users(self):
        organizer = User.objects.create_user("org", password="pass", is_staff=True)
        organizer.groups.add(Group.objects.get(name=ORGANIZERS_GROUP))
        self.client.force_login(organizer)

        self.assertEqual(self.client.get(reverse("admin:conference_submission_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:conference_section_add")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:auth_user_changelist")).status_code, 403)


class LoadSectionsTests(TestCase):
    def test_load_sections_creates_list_and_replaces_demo(self):
        from django.core.management import call_command

        Section.objects.create(name="Демо")
        call_command("load_sections", "--replace", stdout=open(os.devnull, "w"))
        self.assertFalse(Section.objects.filter(name="Демо").exists())
        self.assertEqual(Section.objects.get(name="Региональное краеведение").groups, 3)
        self.assertEqual(Section.objects.count(), 13)


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


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class NewsAndDocumentsTests(TestCase):
    def test_news_list_shows_only_published_and_past(self):
        NewsPost.objects.create(title="Открыта", text="Текст")
        NewsPost.objects.create(title="Черновик", text="Текст", is_published=False)
        NewsPost.objects.create(title="Завтра", text="Текст", published_at=timezone.now() + timedelta(days=1))
        response = self.client.get(reverse("conference:news"))
        self.assertContains(response, "Открыта")
        self.assertNotContains(response, "Черновик")
        self.assertNotContains(response, "Завтра")

    def test_hidden_news_detail_is_404(self):
        post = NewsPost.objects.create(title="Черновик", text="Текст", is_published=False)
        self.assertEqual(self.client.get(reverse("conference:news_detail", args=[post.pk])).status_code, 404)

    def test_news_detail_shows_text(self):
        post = NewsPost.objects.create(title="Итоги", text="Первый абзац\n\nВторой абзац")
        response = self.client.get(reverse("conference:news_detail", args=[post.pk]))
        self.assertContains(response, "Второй абзац")

    def test_empty_pages_have_placeholder(self):
        self.assertContains(self.client.get(reverse("conference:news")), "Новостей пока нет")
        self.assertContains(self.client.get(reverse("conference:documents")), "Документы пока не опубликованы")

    def test_document_is_listed_and_downloadable(self):
        doc = Document.objects.create(title="Положение", file=SimpleUploadedFile("pol.pdf", b"%PDF-1.4"))
        self.assertContains(self.client.get(reverse("conference:documents")), "Положение")
        response = self.client.get(reverse("conference:download_document", args=[doc.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_unpublished_document_hidden(self):
        doc = Document.objects.create(title="Секрет", file=SimpleUploadedFile("s.pdf", b"x"), is_published=False)
        self.assertNotContains(self.client.get(reverse("conference:documents")), "Секрет")
        self.assertEqual(self.client.get(reverse("conference:download_document", args=[doc.pk])).status_code, 404)

    def test_organizer_can_publish_news_and_documents(self):
        organizer = User.objects.create_user("org2", password="pass", is_staff=True)
        organizer.groups.add(Group.objects.get(name=ORGANIZERS_GROUP))
        self.client.force_login(organizer)
        self.assertEqual(self.client.get(reverse("admin:conference_newspost_add")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:conference_document_add")).status_code, 200)

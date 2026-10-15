from django.urls import path

from . import export_tables, office, office_exports, office_log, office_mailing, office_site, office_submissions, views

app_name = "conference"

urlpatterns = [
    path("", views.home, name="home"),
    path("submit/", views.submit, name="submit"),
    path("thanks/", views.thanks, name="thanks"),
    path("privacy/", views.privacy, name="privacy"),
    path("my/", views.my, name="my"),
    path("my/logout/", views.my_logout, name="my_logout"),
    path("my/<int:pk>/edit/", views.my_edit, name="my_edit"),
    path("my/<int:pk>/delete/", views.my_delete, name="my_delete"),
    # Кабинет оргкомитета
    path("office/", office.dashboard, name="office"),
    path("office/login/", office.OfficeLoginView.as_view(), name="office_login"),
    path("office/logout/", office.office_logout, name="office_logout"),
    path("office/password/", office.change_password, name="office_password"),
    path("office/staff/", office.staff_list, name="office_staff"),
    path("office/staff/<int:pk>/password/", office.staff_password, name="office_staff_password"),
    path("office/section/<int:pk>/<int:number>/", office.section_detail, name="office_section"),
    path("office/mailing/", office_mailing.mailing_page, name="office_mailing"),
    path("office/mailing/save/", office_mailing.mailing_save, name="office_mailing_save"),
    path("office/mailing/test/", office_mailing.mailing_test, name="office_mailing_test"),
    path("office/mailing/send/", office_mailing.mailing_send, name="office_mailing_send"),
    path("office/log/", office_log.log_list, name="office_log"),
    path("office/search/", office_submissions.search, name="office_search"),
    path("office/submission/<int:pk>/", office_submissions.submission_edit, name="office_submission"),
    path("office/submission/<int:pk>/admission/", office.set_admission, name="office_admission"),
    path("office/submission/<int:pk>/award/", office.set_award, name="office_award"),
    path("office/settings/", office.conference_settings, name="office_settings"),
    path("office/site/<slug:kind>/", office_site.site_list, name="office_site"),
    path("office/site/<slug:kind>/new/", office_site.site_edit, name="office_site_add"),
    path("office/site/<slug:kind>/<int:pk>/", office_site.site_edit, name="office_site_edit"),
    path("office/site/<slug:kind>/<int:pk>/delete/", office_site.site_delete, name="office_site_delete"),
    path("office/intake/", office.switch_intake, name="office_intake"),
    path("office/export/word/", office_exports.export_word, name="office_word"),
    path("office/export/excel/", office_exports.export_excel, name="office_excel"),
    path("office/export/participants/", office_exports.export_participants, name="office_participants"),
    path("office/export/archive/", office_exports.export_archive, name="office_archive"),
    path("office/export/custom/", office_exports.export_custom, name="office_custom"),
    path("office/section/<int:pk>/<int:number>/word/", office_exports.export_word, name="office_section_word"),
    path("office/section/<int:pk>/<int:number>/excel/", office_exports.export_excel, name="office_section_excel"),
    path("office/section/<int:pk>/<int:number>/archive/", office_exports.export_archive, name="office_section_archive"),
    *[
        path(f"office/export/{slug}-{fmt}/", office_exports.export_preset, {"slug": slug, "fmt": fmt}, name=f"office_{slug}_{fmt}")
        for slug in export_tables.PRESETS
        for fmt in export_tables.FORMATS
    ],
    path("office/links/new/", office.link_create, name="office_link_create"),
    path("office/links/<int:pk>/", office.link_detail, name="office_link"),
    path("office/links/<int:pk>/disable/", office.link_disable, name="office_link_disable"),
    # Ссылка для проверяющего — без входа
    path("check/<str:token>/", office.review, name="review"),
    path("check/<str:token>/download/", office.review_download, name="review_download"),
    path("news/", views.news_list, name="news"),
    path("news/<int:pk>/", views.news_detail, name="news_detail"),
    path("files/news-cover/<int:pk>/", views.news_cover, name="news_cover"),
    path("files/news-file/<int:pk>/", views.news_file, name="news_file"),
    path("documents/", views.documents_redirect, name="documents"),
    path("files/document/<int:pk>/", views.download_document, name="download_document"),
    path("files/blank/<slug:kind>/", views.blank, name="blank"),
    path("files/submission/<int:pk>/", views.download_submission, name="download_submission"),
    path("files/submission/<int:pk>/<slug:kind>/", views.download_submission, name="download_submission_file"),
]

from django.urls import path

from . import office, views

app_name = "conference"

urlpatterns = [
    path("", views.home, name="home"),
    path("submit/", views.submit, name="submit"),
    path("thanks/", views.thanks, name="thanks"),
    path("privacy/", views.privacy, name="privacy"),
    path("my/", views.my, name="my"),
    path("my/logout/", views.my_logout, name="my_logout"),
    path("my/<int:pk>/edit/", views.my_edit, name="my_edit"),
    # Кабинет оргкомитета
    path("office/", office.dashboard, name="office"),
    path("office/login/", office.OfficeLoginView.as_view(), name="office_login"),
    path("office/logout/", office.office_logout, name="office_logout"),
    path("office/section/<int:pk>/<int:number>/", office.section_detail, name="office_section"),
    path("office/export/word/", office.export_word, name="office_word"),
    path("office/export/excel/", office.export_excel, name="office_excel"),
    path("office/export/participants/", office.export_participants, name="office_participants"),
    path("office/export/archive/", office.export_archive, name="office_archive"),
    path("office/section/<int:pk>/<int:number>/word/", office.export_word, name="office_section_word"),
    path("office/section/<int:pk>/<int:number>/excel/", office.export_excel, name="office_section_excel"),
    path("office/section/<int:pk>/<int:number>/archive/", office.export_archive, name="office_section_archive"),
    path("office/links/new/", office.link_create, name="office_link_create"),
    path("office/links/<int:pk>/", office.link_detail, name="office_link"),
    path("office/links/<int:pk>/disable/", office.link_disable, name="office_link_disable"),
    # Ссылка для проверяющего — без входа
    path("check/<str:token>/", office.review, name="review"),
    path("check/<str:token>/download/", office.review_download, name="review_download"),
    path("news/", views.news_redirect, name="news"),
    path("documents/", views.documents_redirect, name="documents"),
    path("files/document/<int:pk>/", views.download_document, name="download_document"),
    path("files/blank/<slug:kind>/", views.blank, name="blank"),
    path("files/submission/<int:pk>/", views.download_submission, name="download_submission"),
    path("files/submission/<int:pk>/<slug:kind>/", views.download_submission, name="download_submission_file"),
]

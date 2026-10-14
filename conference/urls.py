from django.urls import path

from . import views

app_name = "conference"

urlpatterns = [
    path("", views.home, name="home"),
    path("submit/", views.submit, name="submit"),
    path("thanks/", views.thanks, name="thanks"),
    path("privacy/", views.privacy, name="privacy"),
    path("my/", views.my, name="my"),
    path("my/logout/", views.my_logout, name="my_logout"),
    path("my/<int:pk>/edit/", views.my_edit, name="my_edit"),
    path("news/", views.news_redirect, name="news"),
    path("documents/", views.documents_redirect, name="documents"),
    path("files/document/<int:pk>/", views.download_document, name="download_document"),
    path("files/blank/<slug:kind>/", views.blank, name="blank"),
    path("files/submission/<int:pk>/", views.download_submission, name="download_submission"),
    path("files/submission/<int:pk>/<slug:kind>/", views.download_submission, name="download_submission_file"),
]

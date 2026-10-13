from django.urls import path

from . import views

app_name = "conference"

urlpatterns = [
    path("", views.home, name="home"),
    path("submit/", views.submit, name="submit"),
    path("thanks/", views.thanks, name="thanks"),
    path("privacy/", views.privacy, name="privacy"),
    path("news/", views.news_list, name="news"),
    path("news/<int:pk>/", views.news_detail, name="news_detail"),
    path("documents/", views.documents, name="documents"),
    path("files/document/<int:pk>/", views.download_document, name="download_document"),
    path("files/blank/<slug:kind>/", views.blank, name="blank"),
    path("files/submission/<int:pk>/", views.download_submission, name="download_submission"),
    path("files/submission/<int:pk>/<slug:kind>/", views.download_submission, name="download_submission_file"),
]

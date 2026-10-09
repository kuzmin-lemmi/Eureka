from django.urls import path

from . import views

app_name = "conference"

urlpatterns = [
    path("", views.home, name="home"),
    path("submit/", views.submit, name="submit"),
    path("thanks/", views.thanks, name="thanks"),
    path("privacy/", views.privacy, name="privacy"),
    path("files/blank/<slug:kind>/", views.blank, name="blank"),
    path("files/submission/<int:pk>/", views.download_submission, name="download_submission"),
    path("files/submission/<int:pk>/<slug:kind>/", views.download_submission, name="download_submission_file"),
]

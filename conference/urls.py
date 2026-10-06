from django.urls import path

from . import views

app_name = "conference"

urlpatterns = [
    path("", views.home, name="home"),
    path("submit/", views.submit, name="submit"),
    path("thanks/", views.thanks, name="thanks"),
    path("privacy/", views.privacy, name="privacy"),
    path("files/submission/<int:pk>/", views.download_submission, name="download_submission"),
]

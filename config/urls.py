from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Эврика — оргкомитет"
admin.site.site_title = "Эврика"
admin.site.index_title = "Управление конференцией"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("conference.urls")),
]

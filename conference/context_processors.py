from django.conf import settings

from .models import ConferenceSettings


def conference(request):
    return {"conf": ConferenceSettings.load(), "max_upload_mb": settings.MAX_UPLOAD_MB}

from django.conf import settings

from .models import GRADE_MAX, GRADE_MIN, ConferenceSettings


def conference(request):
    return {
        "conf": ConferenceSettings.load(),
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "grade_min": GRADE_MIN,
        "grade_max": GRADE_MAX,
    }

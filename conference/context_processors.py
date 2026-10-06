from .models import ConferenceSettings


def conference(request):
    return {"conf": ConferenceSettings.load()}

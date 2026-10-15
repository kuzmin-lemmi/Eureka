"""Журнал действий оргкомитета: кто и когда поменял допуск, итог, секцию."""

from django.shortcuts import render

from .models import ActionLog, Submission
from .office import office_required

LOG_LIMIT = 300


@office_required
def log_list(request):
    entries = ActionLog.objects.select_related("submission")
    submission = None
    pk = request.GET.get("s", "")
    if pk.isdigit():
        submission = Submission.objects.filter(pk=int(pk)).select_related("section").first()
        entries = entries.filter(submission_id=int(pk))
    action = request.GET.get("action", "")
    if action in ActionLog.Action.values:
        entries = entries.filter(action=action)
    context = {
        "entries": entries[:LOG_LIMIT],
        "limit": LOG_LIMIT,
        "submission": submission,
        "action": action,
        "actions": ActionLog.Action.choices,
    }
    return render(request, "conference/office/log.html", context)

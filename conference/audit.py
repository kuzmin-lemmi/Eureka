"""Журнал действий оргкомитета (см. ActionLog)."""

from .models import ActionLog


def log_action(request, action, submission=None, details=""):
    user = request.user if request.user.is_authenticated else None
    label = ""
    if submission is not None:
        label = f"{submission.number} {submission.full_name}, {submission.section_label}"
    ActionLog.objects.create(
        user=user,
        user_name=(user.get_full_name() or user.username) if user else "",
        action=action,
        submission=submission,
        submission_label=label,
        details=details,
    )

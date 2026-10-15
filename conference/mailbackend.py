"""Почтовый бэкенд через системный sendmail.

На виртуальном хостинге (Beget) отдельный почтовый ящик и пароль не нужны: письма уходят программой sendmail,
которая есть на сервере. Если нужен свой SMTP-ящик, задайте EMAIL_HOST в .env — тогда используется он.
"""

import os
import shutil
import subprocess
from email.utils import parseaddr

from django.core.mail.backends.base import BaseEmailBackend

SENDMAIL_PATHS = ("/usr/sbin/sendmail", "/usr/local/bin/sendmail", "/usr/lib/sendmail")


def find_sendmail():
    return shutil.which("sendmail") or next((p for p in SENDMAIL_PATHS if os.path.exists(p)), None)


class SendmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        program = find_sendmail()
        if not program:
            if self.fail_silently:
                return 0
            raise RuntimeError("На сервере не найдена программа sendmail.")
        sent = 0
        for message in email_messages:
            recipients = message.recipients()
            if not recipients:
                continue
            envelope_from = parseaddr(message.from_email)[1]
            command = [program, "-i", *(["-f", envelope_from] if envelope_from else []), "--", *recipients]
            try:
                result = subprocess.run(
                    command, input=message.message().as_bytes(), capture_output=True, timeout=30, check=False
                )
                if result.returncode != 0:
                    detail = result.stderr.decode("utf-8", "replace").strip()[:150]
                    raise RuntimeError(f"sendmail вернул код {result.returncode}. {detail}".strip())
            except Exception:
                if not self.fail_silently:
                    raise
                continue
            sent += 1
        return sent

"""Точка входа для Passenger на виртуальном хостинге Beget.

Лежит в каталоге сайта (рядом с public_html), код проекта — в подкаталоге app/.
Копируется туда скриптом deploy/beget/install.sh.
"""

import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
sys.path.insert(0, APP_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()

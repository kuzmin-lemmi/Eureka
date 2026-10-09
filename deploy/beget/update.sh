#!/usr/bin/env bash
# Обновление сайта на Beget после изменений в репозитории:
#   bash ~/<каталог сайта>/app/deploy/beget/update.sh
set -euo pipefail

SITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$SITE_DIR"
export PATH="$HOME/.local/bin:$PATH"
export UV_PYTHON_INSTALL_DIR="$SITE_DIR/python" UV_CACHE_DIR="$SITE_DIR/.uv-cache" UV_LINK_MODE=copy

git -C app pull --ff-only
uv pip install --python venv/bin/python -r app/requirements.txt
(cd app && ../venv/bin/python manage.py migrate --noinput \
        && ../venv/bin/python manage.py collectstatic --noinput -v 0)
cp app/deploy/beget/passenger_wsgi.py passenger_wsgi.py
mkdir -p tmp && touch tmp/restart.txt
echo "Сайт обновлён и перезапущен."

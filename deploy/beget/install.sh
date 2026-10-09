#!/usr/bin/env bash
# Первая установка сайта на виртуальный хостинг Beget (Passenger, без Docker).
# Запуск в терминале Beget:
#   curl -fsSL https://raw.githubusercontent.com/kuzmin-lemmi/Eureka/main/deploy/beget/install.sh | bash
# Повторный запуск безопасен: существующие .env, база и файлы не трогаются.
set -euo pipefail

DOMAIN="${DOMAIN:-xn---87-5cdbjj7aedcr4ao1b0pvb.xn--p1ai}"   # эврика-гимназия87.рф
REPO="${REPO:-https://github.com/kuzmin-lemmi/Eureka.git}"
SITE_DIR="${SITE_DIR:-$HOME/$DOMAIN}"
PYTHON_VERSION="3.12"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

if [ ! -d "$SITE_DIR/public_html" ]; then
  echo "Не найден каталог сайта $SITE_DIR/public_html."
  echo "Создайте сайт в панели Beget («Сайты») и привяжите к нему домен. Каталоги сайтов сейчас:"
  find "$HOME" -maxdepth 2 -type d -name public_html -printf '  %h\n' 2>/dev/null || true
  echo "Если сайт лежит в другом каталоге, запустите так: SITE_DIR=~/имя_каталога bash install.sh"
  exit 1
fi
cd "$SITE_DIR"

say "uv и Python $PYTHON_VERSION"
export PATH="$HOME/.local/bin:$PATH"
# Сайт работает от отдельного пользователя Beget, которому доступен только каталог сайта,
# поэтому Python ставится туда, а не в ~/.local.
export UV_PYTHON_INSTALL_DIR="$SITE_DIR/python"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
fi
uv python install "$PYTHON_VERSION"

say "Код проекта в $SITE_DIR/app"
if [ -d app/.git ]; then
  git -C app pull --ff-only
else
  git clone "$REPO" app
fi

say "Виртуальное окружение и зависимости"
case "$(readlink -f venv/bin/python 2>/dev/null)" in
  "$SITE_DIR"/python/*) ;;
  *) rm -rf venv; uv venv --python "$PYTHON_VERSION" --managed-python venv ;;
esac
uv pip install --python venv/bin/python -r app/requirements.txt

say "Настройки (.env)"
if [ ! -f app/.env ]; then
  SECRET=$(venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))")
  cat > app/.env <<EOF
DJANGO_SECRET_KEY=$SECRET
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=$DOMAIN,www.$DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN,https://www.$DOMAIN
DATA_DIR=$SITE_DIR/data
TIME_ZONE=Europe/Moscow
MAX_UPLOAD_MB=20
EOF
  chmod 600 app/.env
  echo "Создан app/.env с новым секретным ключом."
else
  echo "app/.env уже есть — оставляю как есть."
fi

say "База, демо-секции и статика"
(cd app && ../venv/bin/python manage.py migrate --noinput \
        && ../venv/bin/python manage.py seed_demo \
        && ../venv/bin/python manage.py collectstatic --noinput -v 0)

say "Подключение к Passenger"
cp app/deploy/beget/passenger_wsgi.py passenger_wsgi.py
# Заглушка Beget перекрыла бы главную страницу.
for f in public_html/index.html public_html/index.php; do
  if [ -f "$f" ]; then mv "$f" "$f.bak"; echo "Заглушка $f переименована в $f.bak"; fi
done
cat > public_html/.htaccess <<EOF
PassengerEnabled On
PassengerPython $SITE_DIR/venv/bin/python
EOF
mkdir -p tmp && touch tmp/restart.txt

say "Готово"
cat <<EOF
Сайт: https://эврика-гимназия87.рф

Осталось:
  1. В панели Beget выпустить бесплатный SSL-сертификат для домена и включить переадресацию на HTTPS
     (без HTTPS вход в админку не сработает: cookie защищены).
  2. Создать администратора:
       cd $SITE_DIR/app && ../venv/bin/python manage.py createsuperuser
Обновление после изменений в репозитории:
       bash $SITE_DIR/app/deploy/beget/update.sh
EOF

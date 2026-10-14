# Эврика — заметки для разработки

Django-сайт приёма работ на конференцию школьников «Эврика». Подробности для людей — в README.md.

## Команды (Windows, из корня проекта)

```powershell
.\.venv\Scripts\python manage.py runserver      # http://localhost:8000, админка /admin/
.\.venv\Scripts\python manage.py test           # тесты: conference/tests.py
.\.venv\Scripts\python manage.py makemigrations # после правки models.py; миграции коммитить
.\.venv\Scripts\python manage.py seed_demo      # описание конференции и направления в пустую базу
.\.venv\Scripts\python manage.py load_sections  # список направлений оргкомитета (--replace удалит лишние без заявок)
.\.venv\Scripts\python manage.py load_blanks    # бланки из docs/blanks в настройки конференции
```

В `.claude/launch.json` есть конфигурации `eureka` (runserver :8000) и `design` (http.server :8001 для макетов `design/variants.html` и `design/home-layouts.html`).
`design/audit.js` — скрипт для консоли браузера: ищет элементы, вылезающие за экран (проверять на 375 px).

## Устройство

- `config/settings.py` — всё, что различается между dev и сервером, берётся из `.env` (образец: `.env.example`).
  Локально достаточно `DJANGO_DEBUG=1`. База и загруженные файлы лежат в `DATA_DIR` (по умолчанию `data/`, в git не попадает).
- `conference/models.py` — `ConferenceSettings` (одна запись, `ConferenceSettings.load()`, там же бланки),
  `Section` (направление: `groups` секций по `capacity` мест, в анкете «Название 1», «Название 2»…),
  `Submission` (заявка: `section` + `section_number`), `NewsPost` и `Document` (блоки на главной).
  Участники — 8–11 класс (`GRADE_MIN`/`GRADE_MAX`). Места считаются по людям: соавтор занимает место, отклонённые не занимают.
- `conference/forms.py` — анкета `SubmissionForm`: выбор секции со свободными местами (`section_slots`, повторная
  проверка мест при сохранении, SQLite в режиме IMMEDIATE), проверка файлов (`MAX_UPLOAD_MB`), СНИЛС, антиспам.
- `docs/blanks/` — бланки из приказа (заявка, согласие родителя, требования к работе); на сервер попадают через `load_blanks`.
- `conference/views.py` — публичные страницы; `download_submission` отдаёт работу, заявку и согласие только сотрудникам,
  `blank` — пустые бланки всем. Файлы заявок никогда не раздаются через `MEDIA_URL` напрямую — это сохранять.
- `conference/static/conference/app.js` — улучшения анкеты (поля загрузки, маска телефона, проверка, прогресс,
  черновик в localStorage). Форма обязана работать и без JS: всё проверяет сервер.
- `conference/admin.py` — админка оргкомитета. Группа «Оргкомитет» (`apps.ORGANIZERS_GROUP`) создаётся в `apps.py`.
- Вёрстка: `conference/templates/conference/`, `conference/static/conference/` (свои шрифты, без CDN).

## Соглашения

- Интерфейс, комментарии, тексты коммитов — на русском.
- Окончания строк LF (`.gitattributes`).
- Персональные данные (СНИЛС, телефоны, сканы) видны только в админке — не выводить их на публичные страницы и в логи.

## Прод

Сайт работает на виртуальном хостинге Beget: https://эврика-гимназия87.рф (Passenger, без Docker).
Каталог на сервере `~/eureka-gymnasium87`: код в `app/`, база и файлы в `data/`, Python 3.12 в `python/`, `.env` в `app/`.
Выкладка: закоммитить и отправить в `main`, затем на сервере `bash ~/eureka-gymnasium87/app/deploy/beget/update.sh`
(git pull, зависимости, миграции, статика, перезапуск). Скрипты — `deploy/beget/`.
Docker + gunicorn + Caddy (`Dockerfile`, `docker-compose.yml`, `Caddyfile`) — запасной вариант для VPS.

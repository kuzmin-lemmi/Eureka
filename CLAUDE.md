# Эврика — заметки для разработки

Django-сайт приёма работ на конференцию школьников «Эврика». Подробности для людей — в README.md.

## Команды (Windows, из корня проекта)

```powershell
.\.venv\Scripts\python manage.py runserver      # http://localhost:8000, админка /admin/
.\.venv\Scripts\python manage.py test           # тесты: conference/tests.py
.\.venv\Scripts\python manage.py makemigrations # после правки models.py; миграции коммитить
.\.venv\Scripts\python manage.py seed_demo      # демо-секции и текст в пустую базу
```

В `.claude/launch.json` есть конфигурации `eureka` (runserver :8000) и `design` (http.server :8001 для макетов `design/variants.html` и `design/home-layouts.html`).

## Устройство

- `config/settings.py` — всё, что различается между dev и сервером, берётся из `.env` (образец: `.env.example`).
  Локально достаточно `DJANGO_DEBUG=1`. База и загруженные файлы лежат в `DATA_DIR` (по умолчанию `data/`, в git не попадает).
- `conference/models.py` — `ConferenceSettings` (одна запись, `ConferenceSettings.load()`), `Section`, `Submission`.
- `conference/forms.py` — анкета `SubmissionForm`: проверка расширения и размера файла (`MAX_UPLOAD_MB`), антиспам.
- `conference/views.py` — публичные страницы; `download_submission` отдаёт работу, заявку и согласие только сотрудникам,
  `blank` — пустые бланки всем. Файлы заявок никогда не раздаются через `MEDIA_URL` напрямую — это сохранять.
- `conference/static/conference/app.js` — улучшения анкеты (поля загрузки, маска телефона, проверка, прогресс,
  черновик в localStorage). Форма обязана работать и без JS: всё проверяет сервер.
- `conference/admin.py` — админка оргкомитета. Группа «Оргкомитет» (`apps.ORGANIZERS_GROUP`) создаётся в `apps.py`.
- Вёрстка: `conference/templates/conference/`, `conference/static/conference/` (свои шрифты, без CDN).

## Соглашения

- Интерфейс, комментарии, тексты коммитов — на русском.
- Окончания строк LF (`.gitattributes`).
- Прод: Docker + gunicorn + Caddy (`Dockerfile`, `docker-compose.yml`, `Caddyfile`); миграции применяются при старте контейнера.

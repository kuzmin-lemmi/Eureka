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
  Участники — 8–11 класс (`GRADE_MIN`/`GRADE_MAX`). Места считаются по работам: работа с соавтором — одно место.
  Статусов у заявки нет: пока приём открыт, участник может изменить или удалить её («Мои заявки»; файлы удаляет
  сигнал `post_delete`). После закрытия приёма (кнопка в кабинете) оргкомитет отмечает `admission`: допущен / не допущен
  ко 2 этапу; выгрузка этапа 2 берёт только допущенных.
- `conference/forms.py` — анкета `SubmissionForm`: выбор секции со свободными местами (`section_slots`, повторная
  проверка мест при сохранении, SQLite в режиме IMMEDIATE), проверка файлов (`MAX_UPLOAD_MB`), СНИЛС, антиспам.
- `docs/blanks/` — бланки из приказа (заявка, согласие родителя, требования к работе); на сервер попадают через `load_blanks`.
- `conference/views.py` — публичные страницы; `download_submission` отдаёт работу, заявку и согласие только сотрудникам,
  `blank` — пустые бланки всем. Файлы заявок никогда не раздаются через `MEDIA_URL` напрямую — это сохранять.
- `conference/static/conference/app.js` — улучшения анкеты (поля загрузки, маска телефона, проверка, прогресс,
  черновик в localStorage). Форма обязана работать и без JS: всё проверяет сервер.
- `conference/office.py` + `templates/conference/office/` — «Кабинет оргкомитета» (`/office/`): простой интерфейс
  для сотрудников без опыта (вход по ссылке в подвале, заполненность секций, выгрузки, ссылки для проверяющих,
  все настройки конференции — `/office/settings/`, форма `ConferenceSettingsForm`, право `change_conferencesettings`;
  направления, новости, частые вопросы и документы — `office_site.py`, `/office/site/<sections|news|faq|documents>/`).
  Номер и год конференции (`edition`, `year`) подставляются во все выгрузки через `official_title` / `full_name`.
  Доступ: `is_staff` + право `view_submission` (группа «Оргкомитет»). Крупный шрифт — класс `office` на body.
- `conference/exports.py` — выгрузки: Excel (секции, все участники, список для проверяющего), Word (python-docx),
  ZIP с работами потоком (`stream_archive`, без сборки в памяти). СНИЛС не выгружается; проверяющему — без контактов.
- `ReviewLink` — ссылка `/check/<token>/` на архив секции или всех работ без входа, 30 дней, можно отключить.
- `conference/admin.py` — расширенная админка (для администратора сайта). Группа «Оргкомитет» (`apps.ORGANIZERS_GROUP`) создаётся в `apps.py`.
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

### Доступ по SSH

Владелец работает с двух компьютеров, у каждого свой ключ (оба в `authorized_keys` на сервере, оба нужны — не удалять):
`claude-eureka-beget` — ключ `~/.ssh/eureka_beget`, `claude-eureka-deploy` — ключ второго компьютера.
На каждом компьютере в `~/.ssh/config` должен быть псевдоним `eureka-beget` со своим ключом. Пароли не нужны и в чат не запрашиваются.

Если `ssh eureka-beget` не работает (`Could not resolve hostname`), значит на этом компьютере нет псевдонима.
Найти свой ключ (`grep -l claude-eureka ~/.ssh/*.pub`) и дописать в `~/.ssh/config`, подставив путь к нему:

```
Host eureka-beget
    HostName kuzmingv.beget.tech
    User kuzmingv
    IdentityFile ~/.ssh/<ключ_этого_компьютера>
    IdentitiesOnly yes
    BatchMode yes
    ConnectTimeout 15
```

Если ключа на компьютере нет — не создавать молча: сгенерировать новый (`ssh-keygen -t ed25519 -N "" -C claude-eureka-<имя>`),
показать владельцу публичную часть и попросить добавить её в `~/.ssh/authorized_keys` на сервере.

```bash
ssh eureka-beget 'cd ~/eureka-gymnasium87/app && git log --oneline -1'           # проверка связи
ssh eureka-beget 'bash ~/eureka-gymnasium87/app/deploy/beget/update.sh'          # выкладка
ssh eureka-beget 'cd ~/eureka-gymnasium87/app && ../venv/bin/python manage.py check'
```

Многострочный Python на сервере — через stdin: `ssh eureka-beget 'cd ~/eureka-gymnasium87/app && ../venv/bin/python manage.py shell' < script.py`.
Баннер `post-quantum key exchange` в выводе ssh — безобидное предупреждение, его можно отфильтровать.

Правила работы с боевым сервером:
- Смотреть (логи, `git log`, `manage.py check`, чтение базы) — можно без спроса.
- Всё, что меняет сайт или данные (выкладка, миграции, `load_blanks`, правка `.env`, удаление файлов, изменение
  записей в базе) — только после явного «да» владельца в чате. Перед миграциями — копия базы:
  `cp data/db.sqlite3 data/db.sqlite3.bak-ГГГГММДД`.
- Работать только в `~/eureka-gymnasium87`: это общий аккаунт хостинга, другие каталоги не открывать.
- Персональные данные участников (СНИЛС, телефоны, сканы) не выводить в чат: для проверок — количества и номера заявок.

Учётные записи с паролями и суперпользователей на сервере создаёт владелец, не Claude.

Тестовые заявки для обучения оргкомитета: `manage.py test_submissions` (создать) / `--delete` (удалить только их).
Сейчас на сервере они есть — перед открытием приёма работ удалить.

# TWAS Label site

Минимальный веб-кабинет живёт отдельно от Telegram-бота и использует ту же PostgreSQL-базу.

## Что уже есть

- `GET /cabinet` — минимальный личный кабинет.
- `GET /api/me?tgid=<telegram_id>` — профиль пользователя из таблицы `label`.
- `GET /api/user_releases?user_id=<telegram_id>` — релизы пользователя.
- `GET /user_releases?user_id=<telegram_id>` — совместимость со старым фронтендом.

## Локальный запуск

```bash
cd /home/dolepp/label/site
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export POSTGRES_DB=label
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD='...'
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432

python api.py
```

После запуска открыть:

```text
http://127.0.0.1:5000/cabinet
```

Для быстрого входа можно передать Telegram ID:

```text
http://127.0.0.1:5000/cabinet?tgid=<telegram_id>
```

## Важно

Секреты платежей, токен бота и пароль PostgreSQL не должны храниться в HTML.
Для них используются переменные окружения из `.env.example`.

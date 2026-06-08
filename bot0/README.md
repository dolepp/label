# TWAS Label Bot - Модульная структура

## 📁 Структура проекта

```
bot0/
├── main.py              # 🚀 Точка входа, запуск бота
├── config.py            # ⚙️ Конфигурация, токены, настройки
├── label.py             # 👓 СТАРЫЙ монолитный файл (временно сохранён)
├── handlers/            # 🛠️ Папка с обработчиками
│   ├── __init__.py
│   ├── drafts.py        # Список и удаление черновиков
│   ├── finance.py       # Финансовая сводка профиля
│   ├── orders.py        # История заказов
│   ├── profile.py       # Профиль и редактирование
│   ├── promos.py        # Пользовательская активация промокодов
│   ├── reports.py       # Пользовательские запросы отчетов
│   ├── reviews.py       # Отзывы
│   └── support.py       # Поддержка и заявки
├── core/                # ⚙️ Новая конфигурация
│   └── config.py
├── db/                  # 🗄️ Новый слой БД
│   ├── pool.py
│   └── repositories/
│       ├── drafts.py
│       ├── finance.py
│       ├── orders.py
│       ├── profile.py
│       ├── promos.py
│       ├── reports.py
│       ├── reviews.py
│       ├── support.py
│       └── users.py
├── keyboards/           # ⌨️ Клавиатуры и инлайн-кнопки
│   ├── __init__.py
│   ├── reply.py         # Обычные клавиатуры
│   └── inline.py        # Инлайн-клавиатуры
├── utils/               # 🛠️ Вспомогательные функции
│   ├── __init__.py
│   └── database.py      # Работа с БД
└── services/            # 👼 Бизнес-логика, внешние API
    └── __init__.py
```

## 🚀 Запуск

### Текущий совместимый способ:
```bash
python3.11 main.py
```

Сейчас `main.py` импортирует `label.py` как обычный модуль и запускает legacy polling.
Это сохраняет совместимость без опасного `exec()`.

### Старый способ:
```bash
python3.11 run.py  # или label.py
```

## ✅ Статус миграции

✅ Создана структура папок  
✅ Создан `config.py` с настройками  
✅ Создан `utils/database.py` (базовая версия)  
✅ Созданы `keyboards/reply.py` и `keyboards/inline.py`  
✅ Создан `main.py` для запуска  

🔄 В процессе:
- Разбивка обработчиков на модули в `handlers/`
- Извлечение всех функций БД в `utils/database.py`
- Извлечение бизнес-логики в `services/`

## 💾 Бэкап

Оригинальная версия сохранена в: `../bot0_backup_20260131_101521/`

## 👉 Следующие шаги

1. Постепенно переносить обработчики из `label.py` в `handlers/`
2. Тестировать после каждого переноса
3. После полной миграции удалить `label.py`

## ⚠️ Важно

`label.py` остаётся production-монолитом до полного переноса.
Постепенно переносите функции в модули и проверяйте каждый блок отдельно.

## 💾 База данных

PostgreSQL восстановлен из последнего plain SQL backup:
`../db_backup/postgres_backup_20260113_120114_plain.sql`.

Локальный `.env` в этой папке указывает `bot0` на отдельную базу `label`.

Проверка:
```bash
/home/dolepp/label/bot0/venv/bin/python -c "from utils.database import init_db_pool; print(init_db_pool())"
```

## 📋 План миграции

Детальный план разбиения монолита: `docs/MIGRATION_PLAN.md`.

## 🧪 Автотесты

Запуск:
```bash
./scripts/run_tests.sh
```

Сейчас тесты используют стандартный `unittest`, без установки дополнительных
пакетов. Скрипт сначала компилирует Python-файлы, затем запускает:

- unit-тесты форматтеров и текстовых функций;
- тест регистрации модульных handlers на fake bot без Telegram polling;
- read-only smoke-тесты repositories против локальной PostgreSQL БД `label`.

## 🧩 Модульные обработчики

`handlers/common.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_COMMON=1`.

Общий модуль владеет служебным no-op callback `separator`, который используется
как визуальный разделитель в нескольких legacy и modular клавиатурах.

`utils/security.py` содержит общие helper-функции `escape_html`,
`escape_markdown` и `validate_file_upload`. `label.py` импортирует эти имена
напрямую, поэтому старый код продолжает работать без изменения вызовов.

`handlers/reviews.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_REVIEWS=1`.

Legacy review handlers в `label.py` оставлены как fallback, но при этом флаге
не матчятся, поэтому новым владельцем callback-префиксов отзывов становится
модульный handler.

Запуск:
```bash
ENABLE_MODULAR_REVIEWS=1 python3.11 main.py
```

`handlers/profile.py` тоже вынесен и включён через `.env`:
`ENABLE_MODULAR_PROFILE=1`.

Модульный профиль сейчас владеет ядром профиля: просмотр, `profile_data`,
возврат в профиль, редактирование имени артиста, канала, ФИО и email. Остальные подразделы
профиля (`Мои релизы`, `Мои отчеты`, `Черновики`, платежи) выносятся
отдельными модулями.

`handlers/support.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_SUPPORT=1`.

Модульная поддержка владеет кнопками `❓ Помощь/вопросы`, `📞 Поддержка`,
командой `/support`, шаблонными заявками, списком `🆘 Мои заявки`,
админским списком заявок и callback смены статуса. Данные пишутся в
PostgreSQL-таблицу `support_requests`, а legacy support handlers в `label.py`
закрыты флагом `LEGACY_SUPPORT_ENABLED`.

`handlers/reports.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_REPORTS=1`.

Модульные отчеты сейчас владеют пользовательским flow: `📊 Мои отчеты`,
`request_new_report`, `confirm_report_request`, `cancel_report_*`,
`view_latest_report`, `download_report_*` и callback `my_reports`. Админская
обработка запросов, генерация XLSX и загрузка файлов пока остаются в
legacy-монолите.

`handlers/contracts.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_CONTRACTS=1`.

Модульные пользовательские договоры владеют callback `my_contracts`,
`view_user_contract_*` и `download_contract_*`, читая данные из
`db/repositories/contracts.py`. Создание договора, админское изменение статусов,
прикрепление файлов и завершение договора остаются в legacy.

`handlers/orders.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ORDERS=1`.

Модульные заказы владеют кнопками `🛒 Мои заказы`, `🛍 Мои заказы` и callback
`profile_orders` / `all_orders`. В отличие от legacy-варианта, список берётся
из PostgreSQL-таблицы `orders`, поэтому история заказов сохраняется после
перезапуска бота.

`handlers/drafts.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_DRAFTS=1`.

Модульные черновики владеют кнопкой `📋 Черновики`, callback `profile_drafts`
и удалением черновиков через подтверждение. Callback `draft_load_*` пока
остаётся в legacy-монолите, потому что он продолжает старый distribution flow.

`handlers/promos.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_PROMOS=1`.

Модульные промокоды владеют пользовательской активацией `🎟 Ввести промокод`
и callback `promo_from_profile`. Балансовые промокоды пополняют `label.balance`
и пишут в `promo_code_usage`; скидочные промокоды сохраняются в
`user_discount_promos` для дальнейшей оплаты дистрибуции. Админское управление
промокодами и callbacks применения скидки в distribution пока остаются в
legacy-монолите.

`handlers/finance.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_FINANCE=1`.

Модульные финансы владеют callback `profile_finance`: показывают баланс,
количество заказов, завершённые/ожидающие/отменённые заказы и сумму оплаченных
заказов. Пополнение баланса и платежные callbacks пока остаются в legacy.

`handlers/referrals.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_REFERRALS=1`.

Модульная реферальная часть владеет кнопкой `👥 Пригласи друга`, callback
`profile_referral`, `referral_stats` и `copy_referral_*`. Обработка регистрации
по `/start REF_CODE`, начисление бонусов и уведомление пригласившего пока
остаются в legacy-монолите, потому что связаны со стартовым flow.

`handlers/releases.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_RELEASES=1`.

Модульные релизы владеют списком `📀 Мои релизы`, callback `profile_releases`,
`all_releases` и возвратом `back_to_my_releases`. Детальные карточки релиза,
вложения, редактирование, изменение статусов и админские действия пока
остаются в legacy-монолите.

`handlers/release_details.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_RELEASE_DETAILS=1`.

Модульные детали релизов владеют read-only callback `album_detail_*`,
`my_release_detail_*`, `album_detail_*_admin` и `my_release_detail_*_admin`.
В админском режиме карточка показывает владельца, дату создания, полный набор
основных полей и наличие файлов. Записи статуса, UPC и ссылок остаются в
legacy callbacks. Контракт релиза использует явный callback
`view_release_contract_*`, чтобы не конфликтовать с пользовательскими
договорами. Lookup `file_id` для `view_cover_*`, `view_audio_*` и
`view_release_contract_*` вынесен в `db/repositories/release_files.py`; сама
отправка файлов пока остается в legacy handler.

`handlers/release_edit.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_RELEASE_EDIT_MENU=1`.

Модульное меню редактирования владеет callback `edit_release_<id>` и проверяет
права/статус релиза. Запись изменения названия через `edit_release_name_*`
остаётся в legacy; остальные поля пока отвечают alert вместо молчаливого no-op.

`handlers/release_links.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_RELEASE_LINKS=1`.

Модульный слой ссылок владеет read-only callbacks `manage_platform_links_*` и
`view_platform_links_*`. Добавление, редактирование и удаление информации о
площадках остаются в legacy.

`handlers/release_status.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_RELEASE_STATUS_MENU=1`.

Модульные статусные меню владеют read-only callbacks `change_status_*` и
`album_status_update_*`. Подтверждение статуса, запись в БД и уведомления
пользователей остаются в legacy callbacks `status_update_*` и
`album_status_confirm_*`.

`handlers/bookings.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_BOOKINGS=1`.

Модульные записи владеют callback `profile_bookings` и `all_bookings`.
В текущей базе таблицы `bookings` нет, поэтому модуль безопасно показывает
пустое состояние вместо ошибки подключения или ошибки SQL.

`handlers/info.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_INFO=1`.

Модульный информационный слой владеет кнопками `🎵 Наши услуги`,
`🌐 Открыть приложение` и callback
`services_back` / `back_to_main`, а также командами `/main`, `/app` и
`/webapp`. Общий legacy dispatcher главного меню больше не перехватывает эти
кнопки при включённом флаге.

`handlers/admin_contracts.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_CONTRACTS=1`.

Модульные админские договоры владеют callback `admin_contracts`,
`admin_view_contract_*` и `view_contract_file_*`. Пользовательская карточка
договора теперь использует legacy callback `view_user_contract_*`; старый
двусмысленный `view_contract_*` оставлен одним compatibility-диспетчером для
уже отправленных сообщений. Кнопки изменения статуса, отклонения,
прикрепления файла и завершения договора пока ведут в legacy callbacks.

`handlers/admin_finance.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_FINANCE=1`.

Модульная админская финансовая статистика владеет callback `admin_finance` и
`finance_stats`, читает агрегаты по завершённым заказам через
`db/repositories/admin_finance.py`. Создание платежей, пополнение баланса и
ручные финансовые операции остаются в legacy.

`handlers/admin_promos.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_PROMOS=1`.

Модульные админские промокоды владеют read-only/menu callback `finance_promo`
и `promo_stats`. Создание, редактирование и удаление промокодов остаются в
legacy.

`handlers/admin_releases.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_RELEASES=1`.

Модульный entrypoint управления релизами владеет read-only callback
`admin_releases`: показывает список пользователей и ведёт в `user_releases_*`.
Детальные карточки, вложения, статусы, UPC и ссылки остаются в legacy.

`handlers/admin_reports.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_REPORTS=1`.

Модульный админский список запросов отчетов владеет callback
`admin_report_requests`, читает `report_requests` через
`db/repositories/admin_reports.py` и ведёт карточки в legacy callback
`admin_view_report_*`. Изменение статусов, прикрепление XLSX и отправка файлов
пользователям пока остаются в legacy.

`handlers/web_auth.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_WEB_AUTH=1`.

Модульная веб-авторизация владеет командами `/код` и `/webauth`, генерирует
одноразовый код через `db/repositories/auth.py` и сохраняет его в
PostgreSQL-таблицу `auth_codes`.

`keyboards/reply.py` обновлён под текущую структуру меню и используется
модульными handlers для главного меню, профильного меню, редактирования
профиля и cancel-клавиатуры.

`handlers/diagnostics.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_DIAGNOSTICS=1`.

Модульная диагностика владеет командами `/healthcheck`, `/diag` и
`/diagnostics`. Проверки Telegram API, канала, PostgreSQL и YooKassa выполняются
только при явном вызове команды администратором.

`handlers/topups.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_TOPUPS=1`.

Модульное пополнение владеет UI выбора суммы и способа оплаты:
`💳 Пополнить баланс`, `topup_*`, `topup_custom`, `topup_back`,
`topup_from_profile`, `topup_pay_*`, `yookassa_pay_*`, `crypto_pay_*`.
Создание YooKassa/Crypto Bot платежей пока делегируется legacy-функциям, а
callbacks остальных провайдеров `stars_pay_*`, `ton_pay_*` остаются в legacy.

`handlers/admin_stats.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_STATS=1`.

Модульная админская статистика владеет callback `admin_stats` и читает сводку
через `db/repositories/admin_stats.py`. Отсутствующая таблица `studio_bookings`
обрабатывается как `0`, без ошибки для админа.

`handlers/admin_menu.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_MENU=1`.

Модульное админское меню владеет `/admin` и `admin_back`. Совместимое поведение
legacy сохранено: постоянные админы синхронизируются в таблицу `label`, а первый
заход не-админа создаёт запись без прав.

`handlers/admin_services.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_SERVICES=1`.

Модульные админские сервисные меню владеют `admin_services`,
`admin_templates` и `admin_service_settings`. Загрузка договора
`admin_upload_contract` и запись файла остаются в legacy.

`handlers/admin_users.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_USERS=1`.

Модульный список пользователей владеет callback `admin_users` и только читает
таблицу `label`. Кнопки управления ролями, просмотра запросов, карточек
пользователя, договоров и отчетов пока ведут в legacy callbacks.

`handlers/admin_user_roles.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_USER_ROLES=1`.

Модульное меню ролей владеет read-only callback `user_role_*`. Сами
переключатели `toggle_admin_*`, `toggle_artist_*`, `toggle_owner_*` и
`toggle_creator_*` пока остаются в legacy и выполняют запись в БД там же.

`handlers/admin_user_info.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_USER_INFO=1`.

Модульная карточка пользователя владеет read-only callback `user_info_*`:
читает профиль, роли, баланс, контакты и количество релизов. Кнопки релизов
пользователя и дальнейших админских действий пока остаются в legacy callbacks.

`handlers/admin_user_reports.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_USER_REPORTS=1`.

Модульный список отчетов конкретного пользователя владеет read-only callback
`user_reports_*`. Детальная карточка `view_report_*`, изменение статусов,
прикрепление XLSX и отправка файлов остаются в legacy.

`handlers/admin_user_releases.py` вынесен и включён через `.env`:
`ENABLE_MODULAR_ADMIN_USER_RELEASES=1`.

Модульный админский список релизов пользователя владеет callback
`user_releases_*`: читает альбомы и синглы, а детали релиза, вложения,
изменение статусов, UPC и ссылок остаются в legacy release callbacks.

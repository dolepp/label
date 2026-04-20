# bot0 migration plan

## Current state

- `label.py` is the production monolith and must stay runnable during migration.
- `main.py` is now a compatibility launcher. It imports `label.py` as a module and avoids `exec()`.
- `run.py` is the old launcher and still works.
- `.env` points the bot to the restored PostgreSQL database `label`.
- `handlers/`, `services/`, `keyboards/`, and `utils/` already exist, but only part of the future structure is populated.
- `core/config.py` is the canonical settings module for new code. `config.py` remains a compatibility wrapper.
- `db/pool.py` is the canonical DB pool for new repositories. `utils/database.py` remains for legacy compatibility.
- `handlers/common.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_COMMON=1`.
- Legacy `separator` routing is guarded by `LEGACY_COMMON_ENABLED`.
- `utils/security.py` now owns shared `escape_html`, `escape_markdown`, and `validate_file_upload`; `label.py` imports the same names for compatibility.
- `handlers/reviews.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_REVIEWS=1`.
- Legacy review handlers in `label.py` are guarded by `LEGACY_REVIEWS_ENABLED` and do not match while modular reviews are enabled.
- `handlers/profile.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_PROFILE=1`.
- Legacy profile core handlers in `label.py` are guarded by `LEGACY_PROFILE_ENABLED`. The modular profile layer owns profile view/editing and `profile_data`; subsections that touch reports, drafts, payments and releases are being moved separately.
- `handlers/support.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_SUPPORT=1`.
- Legacy support handlers in `label.py` are guarded by `LEGACY_SUPPORT_ENABLED`. The modular support flow owns support/help buttons, `/support`, support template callbacks, user request history, admin support list/detail, and status updates backed by PostgreSQL.
- `handlers/reports.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_REPORTS=1`.
- Legacy user report handlers in `label.py` are guarded by `LEGACY_REPORTS_ENABLED`. Admin report processing, XLSX generation, and file upload still remain in legacy code.
- `handlers/contracts.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_CONTRACTS=1`.
- Legacy user contract list/detail/download handlers in `label.py` are guarded by `LEGACY_CONTRACTS_ENABLED`. Contract creation, admin status changes, file attachment, and completion remain in legacy code.
- `handlers/orders.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ORDERS=1`.
- Legacy order history handlers in `label.py` are guarded by `LEGACY_ORDERS_ENABLED`. The modular order history reads PostgreSQL `orders` instead of in-memory design order state.
- `handlers/drafts.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_DRAFTS=1`.
- Legacy draft list handlers in `label.py` are guarded by `LEGACY_DRAFTS_ENABLED`. Draft loading still remains in legacy code because it resumes the old distribution state machine.
- `handlers/promos.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_PROMOS=1`.
- Legacy user promo activation in `label.py` is guarded by `LEGACY_PROMOS_ENABLED`. Admin promo management and distribution discount application still remain in legacy code.
- `handlers/finance.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_FINANCE=1`.
- Legacy `profile_finance` in `label.py` is guarded by `LEGACY_FINANCE_ENABLED`. Payment and top-up callbacks still remain in legacy code.
- `handlers/referrals.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_REFERRALS=1`.
- Legacy referral profile handlers in `label.py` are guarded by `LEGACY_REFERRALS_ENABLED`. Referral registration from `/start REF_CODE`, bonus accounting and notifications still remain in legacy code.
- `handlers/releases.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_RELEASES=1`.
- Legacy user release list handlers in `label.py` are guarded by `LEGACY_RELEASES_ENABLED`. Release detail cards, attachments, editing, status changes and admin release tools still remain in legacy code.
- `handlers/release_details.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_RELEASE_DETAILS=1`.
- Legacy `album_detail_*` and `my_release_detail_*` routing is guarded by `LEGACY_RELEASE_DETAILS_ENABLED`. The modular detail layer is read-only; attachments, editing, status, UPC and link actions remain in legacy code.
- Release contract file callbacks now use `view_release_contract_*`; user contract detail callbacks now use `view_user_contract_*`. The old ambiguous `view_contract_*` callback remains as a single compatibility dispatcher for already sent messages.
- `db/repositories/release_files.py` owns release file id lookups for `view_cover_*`, `view_audio_*`, and `view_release_contract_*`; media delivery still remains in the legacy handler.
- `handlers/release_edit.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_RELEASE_EDIT_MENU=1`.
- Legacy `edit_release_<id>` routing is guarded by `LEGACY_RELEASE_EDIT_MENU_ENABLED`. Actual `edit_release_name_*` writes remain in legacy; unsupported edit fields now return an explicit alert.
- `handlers/release_links.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_RELEASE_LINKS=1`.
- Legacy `manage_platform_links_*` and `view_platform_links_*` routing is guarded by `LEGACY_RELEASE_LINKS_ENABLED`. Adding, editing and deleting platform information remains in legacy code.
- `handlers/release_status.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_RELEASE_STATUS_MENU=1`.
- Legacy `change_status_*` and `album_status_update_*` routing is guarded by `LEGACY_RELEASE_STATUS_MENU_ENABLED`. Status writes and notifications remain in legacy `status_update_*` and `album_status_confirm_*` callbacks.
- `handlers/bookings.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_BOOKINGS=1`.
- Legacy profile bookings handler in `label.py` is guarded by `LEGACY_BOOKINGS_ENABLED`. The current restored database has no `bookings` table, so the modular handler returns an empty state safely.
- `handlers/info.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_INFO=1`.
- The legacy main menu dispatcher no longer captures services, WebApp, user stats and about buttons while modular info is enabled. `/main`, `/app`, `/webapp`, `services_back` and `back_to_main` are also handled by the modular info layer. Service execution callbacks still remain in legacy code.
- `handlers/admin_contracts.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_CONTRACTS=1`.
- Legacy `admin_contracts` and `admin_view_contract_*` routing are guarded by `LEGACY_ADMIN_CONTRACTS_ENABLED`. The modular contract layer owns list/detail screens and admin `view_contract_file_*` delivery; contract status changes and file attachment remain in legacy code.
- `handlers/admin_finance.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_FINANCE=1`.
- Legacy `admin_finance` routing and `finance_stats` are guarded by `LEGACY_ADMIN_FINANCE_ENABLED`. Payment creation, balance top-ups and manual finance commands still remain in legacy code.
- `handlers/admin_promos.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_PROMOS=1`.
- Legacy `finance_promo` and `promo_stats` are guarded by `LEGACY_ADMIN_PROMOS_ENABLED`. Promo creation and deletion still remain in legacy code.
- `handlers/admin_releases.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_RELEASES=1`.
- Legacy `admin_releases` routing is guarded by `LEGACY_ADMIN_RELEASES_ENABLED`. The modular release admin entry is read-only and routes to `user_releases_*`; release details and writes remain in legacy code.
- `handlers/admin_reports.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_REPORTS=1`.
- Legacy `admin_report_requests` routing is guarded by `LEGACY_ADMIN_REPORTS_ENABLED`. The modular admin reports layer owns only the read-only report request list; status changes, XLSX attachment and user notifications remain in legacy code.
- `handlers/web_auth.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_WEB_AUTH=1`.
- Legacy `/код` and `/webauth` commands are guarded by `LEGACY_WEB_AUTH_ENABLED`. Codes are persisted through `db/repositories/auth.py`.
- `keyboards/reply.py` now contains the shared modular main/profile/edit/cancel reply keyboards used by extracted handlers.
- `handlers/diagnostics.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_DIAGNOSTICS=1`.
- Legacy `/healthcheck`, `/diag`, and `/diagnostics` are guarded by `LEGACY_DIAGNOSTICS_ENABLED`. Runtime checks live in `services/diagnostics.py`.
- `handlers/topups.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_TOPUPS=1`.
- Legacy top-up menu and `topup_pay_*` amount-confirmation handlers are guarded by `LEGACY_TOPUPS_ENABLED`. Payment provider creation callbacks still remain in legacy code.
- `handlers/admin_stats.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_STATS=1`.
- Legacy `admin_stats` routing is guarded by `LEGACY_ADMIN_STATS_ENABLED`. Missing `studio_bookings` is treated as zero.
- `handlers/admin_menu.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_MENU=1`.
- Legacy `/admin` and `admin_back` are guarded by `LEGACY_ADMIN_MENU_ENABLED`. Admin access compatibility writes live in `db/repositories/admins.py`.
- `handlers/admin_services.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_SERVICES=1`.
- Legacy `admin_services`, `admin_templates`, and `admin_service_settings` are guarded by `LEGACY_ADMIN_SERVICES_ENABLED`. Contract upload remains in legacy code.
- `handlers/admin_users.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_USERS=1`.
- Legacy `admin_users` routing is guarded by `LEGACY_ADMIN_USERS_ENABLED`. The modular admin user list is read-only; role toggles, user details, report views, contracts and report file handling still remain in legacy code.
- `handlers/admin_user_info.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_USER_INFO=1`.
- Legacy `user_info_*` routing is guarded by `LEGACY_ADMIN_USER_INFO_ENABLED`. The modular user detail card is read-only; user releases and deeper admin actions still remain in legacy code.
- `handlers/admin_user_reports.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_USER_REPORTS=1`.
- Legacy `user_reports_*` routing is guarded by `LEGACY_ADMIN_USER_REPORTS_ENABLED`. The modular per-user report list is read-only; `view_report_*`, status changes, XLSX attachment and delivery remain in legacy code.
- `handlers/admin_user_releases.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_USER_RELEASES=1`.
- Legacy `user_releases_*` routing is guarded by `LEGACY_ADMIN_USER_RELEASES_ENABLED`. The modular admin release list is read-only; release detail cards, attachments, status, UPC and link editing remain in legacy code.
- `handlers/admin_user_roles.py` is extracted and enabled by `.env` with `ENABLE_MODULAR_ADMIN_USER_ROLES=1`.
- Legacy `user_role_*` routing is guarded by `LEGACY_ADMIN_USER_ROLES_ENABLED`. The modular role screen is read-only; `toggle_*` writes and their refresh still remain in legacy code.

## Target structure

```text
bot0/
  main.py
  config.py                 # legacy compatibility wrapper
  label.py
  core/
    config.py
  db/
    pool.py
    migrations.py
    repositories/
      drafts.py
      finance.py
      users.py
      promos.py
      releases.py
      orders.py
      payments.py
      reviews.py
      support.py
      reports.py
      contracts.py
      drafts.py
      referrals.py
  handlers/
    start.py
    profile.py
    drafts.py
    finance.py
    orders.py
    promos.py
    releases.py
    distribution.py
    services.py
    payments.py
    reviews.py
    support.py
    reports.py
    admin.py
    finance.py
    reports.py
    contracts.py
  services/
    notifications.py
    payments_yookassa.py
    payments_crypto.py
    distribution.py
    reports.py
    contracts.py
    referrals.py
    files.py
  keyboards/
    main.py
    profile.py
    admin.py
    distribution.py
    payments.py
  state/
    distribution_form.py
    support_form.py
```

## Migration rules

1. Move one feature area at a time.
2. Keep `label.py` as the fallback until the moved feature has been smoke-tested.
3. Move database access before moving large handlers. Handlers should call repositories or services, not inline SQL.
4. Keep callback prefixes owned by exactly one module.
5. Do not start multiple polling processes with the same bot token.
6. After every move, verify imports and DB connectivity before starting polling.
7. Enable modular handlers with feature flags until the matching legacy handlers are removed from `label.py`.

## First extraction order

1. Read-only helpers: formatting, escaping, file validation, admin checks. Escaping and upload validation are now in `utils/security.py`.
2. Common no-op callbacks. Done behind `ENABLE_MODULAR_COMMON=1`.
3. Reviews repository and reviews flow. Done behind `ENABLE_MODULAR_REVIEWS=1`.
4. Profile repository and profile core flow. Done behind `ENABLE_MODULAR_PROFILE=1`; subsections remain legacy.
5. Support repository and support flow. Done behind `ENABLE_MODULAR_SUPPORT=1`.
6. User reports flow. Done behind `ENABLE_MODULAR_REPORTS=1`; admin report processing remains legacy.
7. User contracts list/detail/download. Done behind `ENABLE_MODULAR_CONTRACTS=1`; creation/admin writes remain legacy.
8. Order history. Done behind `ENABLE_MODULAR_ORDERS=1`.
9. Draft list and delete flow. Done behind `ENABLE_MODULAR_DRAFTS=1`; draft loading remains legacy.
10. User promo activation. Done behind `ENABLE_MODULAR_PROMOS=1`; admin promo management and distribution apply remain legacy.
11. Profile finance summary. Done behind `ENABLE_MODULAR_FINANCE=1`; top-up/payment callbacks remain legacy.
12. Referral profile screens. Done behind `ENABLE_MODULAR_REFERRALS=1`; `/start REF_CODE` registration remains legacy.
13. User release list. Done behind `ENABLE_MODULAR_RELEASES=1`; editing/admin actions remain legacy.
14. Release detail cards. Done behind `ENABLE_MODULAR_RELEASE_DETAILS=1`; attachments/editing/status/UPC/link actions remain legacy.
15. Release edit menu. Done behind `ENABLE_MODULAR_RELEASE_EDIT_MENU=1`; field writes remain legacy.
16. Release platform link view. Done behind `ENABLE_MODULAR_RELEASE_LINKS=1`; add/edit/delete remain legacy.
17. Release status selection menus. Done behind `ENABLE_MODULAR_RELEASE_STATUS_MENU=1`; writes/notifications remain legacy.
18. Profile bookings. Done behind `ENABLE_MODULAR_BOOKINGS=1`; booking creation is not implemented in the restored schema.
19. Top-level informational menu. Done behind `ENABLE_MODULAR_INFO=1`; service execution callbacks remain legacy.
20. Admin contract list/detail and admin file view. Done behind `ENABLE_MODULAR_ADMIN_CONTRACTS=1`; status/file attachment actions remain legacy.
21. Admin finance statistics. Done behind `ENABLE_MODULAR_ADMIN_FINANCE=1`; write/payment flows remain legacy.
22. Admin promo menu/statistics. Done behind `ENABLE_MODULAR_ADMIN_PROMOS=1`; creation/deletion remain legacy.
23. Admin releases entry. Done behind `ENABLE_MODULAR_ADMIN_RELEASES=1`; release details/actions remain legacy.
24. Admin report request list. Done behind `ENABLE_MODULAR_ADMIN_REPORTS=1`; status/file actions remain legacy.
25. Web authorization codes. Done behind `ENABLE_MODULAR_WEB_AUTH=1`.
26. Admin diagnostics command. Done behind `ENABLE_MODULAR_DIAGNOSTICS=1`.
27. Top-up menu UI and `topup_pay_*` amount confirmation. Done behind `ENABLE_MODULAR_TOPUPS=1`; provider payment creation remains legacy.
28. Admin statistics dashboard. Done behind `ENABLE_MODULAR_ADMIN_STATS=1`.
29. Admin menu entry/back navigation. Done behind `ENABLE_MODULAR_ADMIN_MENU=1`.
30. Admin service settings menus. Done behind `ENABLE_MODULAR_ADMIN_SERVICES=1`; contract upload remains legacy.
31. Admin user list. Done behind `ENABLE_MODULAR_ADMIN_USERS=1`; role toggles and detailed admin user actions remain legacy.
32. Admin user detail card. Done behind `ENABLE_MODULAR_ADMIN_USER_INFO=1`; user release/admin detail actions remain legacy.
33. Admin per-user report list. Done behind `ENABLE_MODULAR_ADMIN_USER_REPORTS=1`; report details/actions remain legacy.
34. Admin per-user release list. Done behind `ENABLE_MODULAR_ADMIN_USER_RELEASES=1`; release details/actions remain legacy.
35. Admin user role menu. Done behind `ENABLE_MODULAR_ADMIN_USER_ROLES=1`; role toggles remain legacy.
36. Payment provider callbacks.
37. Release attachments, field writes, UPC/link writes and admin reports.
38. Distribution, because it is the largest and has the most state.

## Verification commands

```bash
cd /home/dolepp/label/bot0
/home/dolepp/label/bot0/venv/bin/python -m py_compile main.py config.py utils/database.py
/home/dolepp/label/bot0/venv/bin/python -c "from config import DB_CONFIG; print(DB_CONFIG)"
/home/dolepp/label/bot0/venv/bin/python -c "from utils.database import init_db_pool; print(init_db_pool())"
/home/dolepp/label/bot0/venv/bin/python -c "from db.pool import init_pool; print(init_pool())"
```

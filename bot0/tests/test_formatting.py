from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from db.repositories.drafts import format_draft_datetime
from db.repositories.bookings import format_booking_date
from db.repositories.auth import generate_numeric_code
from db.repositories.orders import format_amount, format_order_datetime
from db.repositories.releases import format_release_date
from handlers.admin_finance import _finance_overview_text, _finance_stats_text
from handlers.admin_contracts import _admin_contract_detail_text, _admin_contracts_text, _format_contract_button
from handlers.admin_menu import _admin_panel_markup
from handlers.admin_promos import _promo_stats_text
from handlers.admin_releases import _admin_releases_text
from handlers.admin_reports import _admin_reports_text, _format_report_button
from handlers.admin_services import _admin_services_markup
from handlers.admin_stats import _admin_stats_text
from handlers.admin_user_info import _admin_user_info_text
from handlers.admin_user_releases import _admin_user_releases_text
from handlers.admin_user_reports import _user_reports_text
from handlers.admin_user_roles import _user_role_text
from handlers.admin_users import _admin_users_text, _display_name
from handlers.contracts import (
    _contract_detail_text,
    _contracts_list_text,
    _format_contract_button as _format_user_contract_button,
)
from handlers.finance import _finance_text
from handlers.info import _stats_text as _info_stats_text
from handlers.orders import _order_line
from handlers.profile import _profile_data_text
from handlers.promos import _reply_for_result
from handlers.referrals import _stats_text as _referral_stats_text, _text
from handlers.release_details import _album_detail_text, _release_detail_text
from handlers.release_edit import _edit_release_markup
from handlers.release_links import _platform_links_text
from handlers.release_status import _album_status_selection_markup, _status_selection_markup
from handlers.topups import _parse_amount
from handlers.web_auth import _auth_text
from keyboards.reply import MAIN_MENU_BUTTONS, PROFILE_MENU_ROWS
from services.diagnostics import diagnostics_text
from utils.security import escape_html, escape_markdown, validate_file_upload


class FormattingTests(unittest.TestCase):
    def test_order_amount_formatting(self):
        self.assertEqual(format_amount(Decimal("100.00")), "100₽")
        self.assertEqual(format_amount(Decimal("100.50")), "100.50₽")

    def test_datetime_formatting(self):
        value = datetime(2026, 1, 9, 18, 18)
        self.assertEqual(format_order_datetime(value), "09.01.2026 18:18")
        self.assertEqual(format_draft_datetime(value), "09.01.2026")
        self.assertEqual(format_release_date(value), "09.01.2026")
        self.assertEqual(format_booking_date(value), "09.01.2026")

    def test_auth_code_helpers(self):
        code = generate_numeric_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        self.assertIn("123456", _auth_text("123456"))

    def test_topup_amount_parser(self):
        self.assertEqual(_parse_amount("1 500₽"), 1500)
        self.assertIsNone(_parse_amount("нет"))

    def test_security_helpers(self):
        self.assertEqual(escape_html("<tag & value>"), "&lt;tag &amp; value&gt;")
        self.assertEqual(escape_markdown("a_b!"), "a\\_b\\!")

        message = SimpleNamespace(
            document=SimpleNamespace(file_id="file-1", file_name="report.xlsx", file_size=1024),
            photo=None,
            audio=None,
            video=None,
        )
        self.assertEqual(validate_file_upload(message, [".xlsx"], 1), (True, "", "file-1"))
        ok, error, file_id = validate_file_upload(message, [".pdf"], 1)
        self.assertFalse(ok)
        self.assertIn("Неподдерживаемый формат", error)
        self.assertIsNone(file_id)

    def test_reply_keyboard_constants_cover_current_menu(self):
        self.assertIn("🎵 Наши услуги", MAIN_MENU_BUTTONS)
        self.assertIn("👤 Мой профиль", MAIN_MENU_BUTTONS)
        self.assertTrue(any("👥 Пригласи друга" in row for row in PROFILE_MENU_ROWS))

    def test_diagnostics_text_contains_overall_status(self):
        text = diagnostics_text([{"name": "PostgreSQL", "ok": True, "details": "ok"}], True, datetime(2026, 1, 9, 18, 18))
        self.assertIn("09.01.2026 18:18:00", text)
        self.assertIn("✅ PostgreSQL: ok", text)
        self.assertIn("Все системы работают", text)

    def test_order_line_contains_core_fields(self):
        line = _order_line(
            1,
            {
                "id": 47,
                "service_type": "topup",
                "amount": Decimal("100.00"),
                "status": "pending",
                "created_date": datetime(2026, 1, 9, 18, 18),
            },
        )
        self.assertIn("Заказ #47", line)
        self.assertIn("Пополнение баланса", line)
        self.assertIn("⏳ ожидает", line)

    def test_finance_text_contains_summary(self):
        text = _finance_text(
            {
                "balance": Decimal("140668.00"),
                "total_orders": 22,
                "completed_orders": 5,
                "pending_orders": 0,
                "cancelled_orders": 17,
                "completed_sum": Decimal("1000.00"),
            }
        )
        self.assertIn("Баланс", text)
        self.assertIn("140 668.00₽", text)
        self.assertIn("Всего заказов: 22", text)

    def test_admin_finance_stats_text_contains_breakdown(self):
        text = _finance_stats_text(
            {
                "total_revenue": Decimal("1000.00"),
                "monthly_revenue": Decimal("300.00"),
                "today_revenue": Decimal("100.00"),
            }
        )
        self.assertIn("Общий доход: 1,000.00₽", text)
        self.assertIn("Доля Артёма (15%): 150.00₽", text)
        self.assertIn("Доход за сегодня: 100.00₽", text)

    def test_admin_finance_overview_text_contains_totals(self):
        text = _finance_overview_text({"total_revenue": Decimal("1000.00"), "today_revenue": Decimal("50.00")})
        self.assertIn("Общий доход: 1,000.00₽", text)
        self.assertIn("Доход за сегодня: 50.00₽", text)

    def test_info_stats_text_contains_summary(self):
        text = _info_stats_text({"releases_count": 4, "balance": Decimal("1500.00"), "completed_orders": 2})
        self.assertIn("Релизов: 4", text)
        self.assertIn("1,500.00₽", text)
        self.assertIn("Завершенных заказов: 2", text)

    def test_profile_data_text_contains_core_fields(self):
        text = _profile_data_text(
            {"name": "Artist", "kanal": "@channel", "fio": "Name", "email": "a@example.com", "balance": Decimal("10")}
        )
        self.assertIn("Имя артиста: Artist", text)
        self.assertIn("Email: a@example.com", text)
        self.assertIn("10.00₽", text)

    def test_promo_reply_messages(self):
        self.assertIn("не найден", _reply_for_result({"status": "not_found"}))
        self.assertIn("зачислено", _reply_for_result({"status": "balance_activated", "amount": Decimal("100")}))
        self.assertIn("скидку", _reply_for_result({"status": "discount_activated", "discount": Decimal("14")}))

    def test_admin_promo_stats_text_contains_counts(self):
        text = _promo_stats_text(
            {
                "total": 7,
                "active": 5,
                "expired": 1,
                "limited_usage": 2,
                "total_amount": Decimal("1000.00"),
                "used_amount": Decimal("300.00"),
            }
        )
        self.assertIn("Всего промокодов: 7", text)
        self.assertIn("Активных: 5", text)
        self.assertIn("Общая сумма всех: 1000.00₽", text)

    def test_admin_stats_text_contains_counts(self):
        text = _admin_stats_text(
            {
                "total_users": 10,
                "total_releases": 4,
                "total_bookings": 0,
                "total_revenue": Decimal("1234.00"),
                "total_reviews": 3,
                "new_users_week": 2,
            }
        )
        self.assertIn("Всего пользователей: 10", text)
        self.assertIn("Общий оборот: 1,234.00₽", text)

    def test_admin_panel_markup_is_buildable(self):
        markup = _admin_panel_markup()
        self.assertIsNotNone(markup)

    def test_admin_services_markup_is_buildable(self):
        markup = _admin_services_markup()
        self.assertIsNotNone(markup)

    def test_admin_users_text_and_display_name(self):
        users = [{"telegram_id": 10, "tg": "artist", "name": "Artist"}]
        self.assertEqual(_display_name(users[0]), "Artist (@artist)")
        self.assertIn("Список всех пользователей (1)", _admin_users_text(users))

    def test_admin_reports_text_and_button(self):
        reports = [
            {
                "id": 7,
                "status": "pending",
                "created_at": datetime(2026, 1, 9, 18, 18),
                "user_name": "Artist",
                "user_id": 10,
                "release_name": "Single",
            }
        ]
        self.assertIn("Запросы отчетов (1)", _admin_reports_text(reports))
        self.assertIn("Ожидающие обработки: 1", _admin_reports_text(reports))
        self.assertIn("Artist - Single", _format_report_button(reports[0]))

    def test_admin_contracts_text_and_detail(self):
        contracts = [
            {
                "id": 4,
                "user_id": 10,
                "contract_number": "CN-1",
                "contract_type": "beat",
                "status": "pending",
                "created_at": datetime(2026, 1, 9, 18, 18),
                "completed_at": None,
                "contract_file_id": None,
                "user_name": "Artist",
                "username": "artist",
            }
        ]
        self.assertIn("Управление договорами (1)", _admin_contracts_text(contracts))
        self.assertIn("Ожидающие обработки: 1", _admin_contracts_text(contracts))
        self.assertIn("Artist - CN-1", _format_contract_button(contracts[0]))
        self.assertIn("Детали договора #4", _admin_contract_detail_text(contracts[0]))

    def test_user_contract_texts(self):
        contract = {
            "id": 7,
            "contract_number": "CNT-7",
            "contract_type": "license",
            "status": "completed",
            "created_at": datetime(2026, 1, 9, 18, 18),
            "completed_at": datetime(2026, 1, 10, 18, 18),
            "contract_file_id": "file-id",
        }
        self.assertIn("Ваши договоры", _contracts_list_text([contract]))
        self.assertIn("пока нет договоров", _contracts_list_text([]))
        self.assertIn("CNT-7", _format_user_contract_button(contract))
        self.assertIn("Детали договора #7", _contract_detail_text(contract))

    def test_admin_user_role_text(self):
        text = _user_role_text(
            {
                "telegram_id": 10,
                "name": "Artist",
                "tg": "artist",
                "admin": 1,
                "artist": 0,
                "owner": 0,
                "creator": 1,
            }
        )
        self.assertIn("Пользователь: Artist (@artist)", text)
        self.assertIn("Администратор: Да", text)
        self.assertIn("Creator: Да", text)

    def test_admin_user_info_text(self):
        text = _admin_user_info_text(
            {
                "telegram_id": 10,
                "name": "Artist",
                "tg": "artist",
                "admin": 1,
                "artist": 1,
                "owner": 0,
                "creator": 0,
                "balance": Decimal("12.50"),
                "created_date": datetime(2026, 1, 9, 18, 18),
                "email": "a@example.com",
                "fio": "Artist Name",
                "phone": "+100",
                "releases_count": 2,
            }
        )
        self.assertIn("Информация о пользователе", text)
        self.assertIn("Баланс: 12.50₽", text)
        self.assertIn("Количество релизов: 2", text)

    def test_admin_user_reports_text(self):
        user = {"telegram_id": 10, "name": "Artist", "tg": "artist"}
        reports = [
            {
                "id": 1,
                "release_type": "single",
                "request_type": "royalty",
                "status": "pending",
                "created_at": datetime(2026, 1, 9, 18, 18),
                "notes": "note",
            }
        ]
        text = _user_reports_text(user, reports)
        self.assertIn("Запросы отчетов пользователя Artist (@artist)", text)
        self.assertIn("<b>royalty</b> - single", text)
        self.assertIn("note", text)

    def test_admin_user_releases_text(self):
        self.assertIn("нет релизов", _admin_user_releases_text({"albums": [], "singles": []}))
        self.assertEqual(
            _admin_user_releases_text({"albums": [{"id": 1}], "singles": []}),
            "📀 Релизы пользователя:",
        )

    def test_admin_releases_text(self):
        self.assertIn("Управление релизами", _admin_releases_text([{"telegram_id": 1}]))
        self.assertIn("нет зарегистрированных", _admin_releases_text([]))

    def test_release_detail_texts(self):
        album_text = _album_detail_text(
            {
                "release_name": "Album",
                "release_date": datetime(2026, 1, 9),
                "status": "Релиз",
                "upc_code": "123",
            }
        )
        release_text = _release_detail_text(
            {
                "release_name": "Single",
                "release_type": "single",
                "artist_name": "Artist",
                "producer": None,
                "genre": "Pop",
                "release_date": datetime(2026, 1, 9),
                "performer_name": "Performer",
                "music_author": "Author",
                "explicit_content": False,
                "yandex_soon": True,
                "create_links": True,
                "tiktok_commercial": False,
                "tiktok_full_version": True,
                "preview_start": 30,
                "status": "В обработке",
                "upc_code": None,
            }
        )
        self.assertIn("Альбом: Album", album_text)
        self.assertIn("UPC код: 123", album_text)
        self.assertIn("Детали релиза: Single", release_text)
        self.assertIn("Секунды TikTok: 30 сек", release_text)

    def test_release_link_text(self):
        self.assertIn("Информация не добавлена", _platform_links_text({}))
        self.assertIn("Spotify: https://example.com", _platform_links_text({"Spotify": "https://example.com"}))

    def test_release_status_markups_are_buildable(self):
        self.assertIsNotNone(_status_selection_markup(1))
        self.assertIsNotNone(_album_status_selection_markup(1))

    def test_release_edit_markup_is_buildable(self):
        self.assertIsNotNone(_edit_release_markup(1))

    def test_referral_text_contains_link_and_stats(self):
        summary = {
            "referral_code": "REF1398275867",
            "referral_count": 3,
            "referral_earnings": Decimal("300.00"),
            "total_referrals": 4,
            "active_referrals": 2,
        }
        text = _text(summary)
        stats = _referral_stats_text(summary)

        self.assertIn("https://t.me/twaslabel_bot?start=REF1398275867", text)
        self.assertIn("Приглашено друзей: 3", text)
        self.assertIn("Заработано: 300₽", text)
        self.assertIn("Всего приглашено: 4", stats)
        self.assertIn("Активных: 2", stats)


if __name__ == "__main__":
    unittest.main()

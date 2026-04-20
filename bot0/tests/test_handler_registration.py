from __future__ import annotations

import unittest

from handlers import register_optional_handlers

from tests.fakes import (
    FakeBot,
    count_command_handlers,
    count_matching_callback_handlers,
    count_matching_message_handlers,
    make_call,
)


class HandlerRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.bot = FakeBot()
        register_optional_handlers(self.bot)

    def test_profile_buttons_are_registered(self):
        self.assertEqual(count_matching_message_handlers(self.bot, "👤 Мой профиль"), 1)
        self.assertEqual(count_matching_message_handlers(self.bot, "✏️ Редактировать профиль"), 1)

    def test_modular_commands_are_registered_once(self):
        for command in ("main", "app", "webapp", "admin", "код", "webauth", "healthcheck", "diag", "diagnostics"):
            with self.subTest(command=command):
                self.assertEqual(count_command_handlers(self.bot, command), 1)

    def test_feature_buttons_are_registered_once(self):
        for text in (
            "⭐️ Отзывы",
            "❓ Помощь/вопросы",
            "📞 Поддержка",
            "📊 Мои отчеты",
            "🛒 Мои заказы",
            "📋 Черновики",
            "🎟 Ввести промокод",
            "👥 Пригласи друга",
            "📀 Мои релизы",
            "◀️ Назад к моим релизам",
            "🎵 Наши услуги",
            "🌐 Открыть приложение",
            "📊 Статистика",
            "ℹ️ О нас",
            "💳 Пополнить баланс",
        ):
            with self.subTest(text=text):
                self.assertEqual(count_matching_message_handlers(self.bot, text), 1)

    def test_modular_callbacks_are_registered_once(self):
        for data in (
            "profile_finance",
            "separator",
            "profile_orders",
            "all_orders",
            "profile_drafts",
            "draft_delete_prompt_1",
            "draft_delete_confirm_1",
            "promo_from_profile",
            "profile_referral",
            "referral_stats",
            "copy_referral_REF1398275867",
            "profile_releases",
            "all_releases",
            "back_to_my_releases",
            "album_detail_1",
            "my_release_detail_1",
            "album_detail_1_admin",
            "my_release_detail_1_admin",
            "manage_platform_links_1",
            "view_platform_links_1",
            "change_status_1",
            "album_status_update_1",
            "edit_release_1",
            "edit_artist_name_1",
            "profile_bookings",
            "all_bookings",
            "services_back",
            "back_to_main",
            "admin_back",
            "admin_stats",
            "admin_finance",
            "admin_releases",
            "admin_services",
            "admin_templates",
            "admin_service_settings",
            "admin_users",
            "admin_report_requests",
            "admin_contracts",
            "admin_view_contract_1",
            "view_contract_file_1",
            "user_info_1",
            "user_reports_1",
            "user_releases_1",
            "user_role_1",
            "finance_stats",
            "finance_promo",
            "promo_stats",
            "profile_data",
            "topup_500",
            "topup_custom",
            "topup_pay_500",
            "topup_back",
            "topup_from_profile",
            "request_new_report",
            "confirm_report_request",
            "cancel_report_1",
            "view_latest_report",
            "download_report_1",
            "my_contracts",
            "view_user_contract_1",
            "download_contract_1",
            "support_template:moderation",
            "support_status:1:принят",
            "admin_support",
        ):
            with self.subTest(data=data):
                self.assertEqual(count_matching_callback_handlers(self.bot, data), 1)

    def test_topup_pay_callback_shows_provider_methods(self):
        call = make_call("topup_pay_500")
        matching_handlers = [
            handler["function"]
            for handler in self.bot.callback_query_handlers
            if handler.get("filters", {}).get("func") and handler["filters"]["func"](call)
        ]

        self.assertEqual(len(matching_handlers), 1)
        matching_handlers[0](call)

        self.assertEqual(len(self.bot.callback_answers), 1)
        self.assertEqual(len(self.bot.edited_messages), 1)
        self.assertIn("500₽", self.bot.edited_messages[0]["text"])
        self.assertIn("Выберите способ оплаты", self.bot.edited_messages[0]["text"])


if __name__ == "__main__":
    unittest.main()

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
        for command in ("cancel", "main", "app", "webapp", "admin", "код", "webauth", "finance", "healthcheck", "diag", "diagnostics", "test_cover"):
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
            "🔍 Подробности релиза: Test",
            "📝 Запросить обновление статуса",
            "◀️ Назад к моим релизам",
            "🎵 Наши услуги",
            "🌐 Открыть приложение",
            "💳 Пополнить баланс",
            "💾 Сохранить черновик",
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
            "request_update_1",
            "preview_cover",
            "preview_audio",
            "preview_contract",
            "preview_track_0",
            "show_attachments_1",
            "show_attachments_1_admin",
            "view_cover_1",
            "view_audio_1",
            "view_release_contract_1",
            "admin_view_release_1",
            "manage_platform_links_1",
            "view_platform_links_1",
            "change_status_1",
            "status_update_1_принят",
            "releases_change_status",
            "releases_approve",
            "releases_reject",
            "album_status_update_1",
            "album_status_confirm_1_Релиз",
            "change_upc_1",
            "album_upc_update_1",
            "add_platform_link_1",
            "quick_link_menu_1",
            "edit_platform_links_1",
            "edit_platform_1_Spotify",
            "delete_platform_links_1",
            "edit_release_1",
            "edit_artist_name_1",
            "profile_bookings",
            "all_bookings",
            "services_back",
            "back_to_main",
            "admin_back",
            "admin_broadcast",
            "broadcast_level_artist",
            "broadcast_create",
            "admin_stats",
            "admin_finance",
            "admin_releases",
            "releases_all",
            "releases_artists",
            "artist_Test",
            "artist_releases_Test",
            "admin_services",
            "design_status:REQ:готов",
            "admin_templates",
            "admin_service_settings",
            "admin_upload_contract",
            "admin_users",
            "admin_report_requests",
            "admin_send_report_1",
            "request_report_single_1",
            "start_report_1",
            "attach_report_1",
            "complete_report_1",
            "view_report_1",
            "attach_xlsx_report_1",
            "confirm_report_upload_1",
            "admin_process_pending_reports",
            "admin_view_report_1",
            "admin_start_report_1",
            "admin_reject_report_1",
            "accept_report_1",
            "reject_report_1",
            "admin_contracts",
            "admin_view_contract_1",
            "view_contract_file_1",
            "view_contract_1",
            "start_contract_1",
            "reject_contract_1",
            "attach_contract_1",
            "complete_contract_1",
            "user_info_1",
            "user_detail_1",
            "release_detail_1",
            "user_reports_1",
            "user_releases_1",
            "user_role_1",
            "toggle_admin_1",
            "toggle_artist_1",
            "toggle_owner_1",
            "toggle_steezy_1",
            "toggle_bibi_1",
            "toggle_shvepz_1",
            "toggle_creator_1",
            "finance_stats",
            "finance_promo",
            "promo_create",
            "promo_create_balance",
            "promo_create_discount",
            "promo_create_limited",
            "promo_create_timed",
            "promo_create_unlimited",
            "promo_create_discount_limited",
            "promo_create_discount_timed",
            "promo_create_discount_unlimited",
            "promo_stats",
            "promo_delete",
            "delete_promo_CODE",
            "profile_data",
            "pay_cover",
            "check_payment_123",
            "topup_500",
            "topup_custom",
            "topup_pay_500",
            "yookassa_pay_500",
            "crypto_pay_500",
            "stars_pay_500",
            "ton_pay_500",
            "check_crypto_123",
            "pay_stars_stars_1_123",
            "check_stars_stars_1_123",
            "copy_ton_EQabc",
            "check_ton_ton_1_123",
            "cancel_topup",
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
            "service_distribution",
            "service_cover",
            "service_motion",
            "service_videoshot",
            "service_release_for_artist",
            "distribution_disagree",
            "distribution_agree",
            "distribution_pay_1299",
            "distribution_start",
            "distribution_prev",
            "distribution_next",
            "distribution_edit",
            "distribution_complete",
            "use_promo_distribution",
            "apply_promo_dist_TEST",
            "idist_start",
            "idist_prev",
            "idist_next",
            "idist_edit",
            "idist_yes_explicit_content",
            "idist_no_explicit_content",
            "idist_cancel_all",
            "idist_save_draft",
            "idist_save_and_cancel",
            "idist_delete_and_cancel",
            "idist_preview",
            "idist_edit_back",
            "idist_submit_free",
            "idist_pay",
            "draft_load_1",
            "edit_release_name_1",
        ):
            with self.subTest(data=data):
                self.assertEqual(count_matching_callback_handlers(self.bot, data), 1)


    def test_legacy_distribution_step_chain_is_not_in_monolith(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        legacy_handler_text = (root / "handlers" / "legacy_distribution.py").read_text(encoding="utf-8")

        import ast

        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        for name in (
            "ask_release_type",
            "show_release_preview",
            "save_release_data_for_user",
            "DistributionForm",
            "handle_distribution_pay",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, labels)

        self.assertIn("steps.show_release_preview", legacy_handler_text)
        self.assertIn("steps.save_release_data_for_user", legacy_handler_text)
        self.assertNotIn("legacy.show_release_preview", legacy_handler_text)
        self.assertNotIn("legacy.save_release_data_for_user", legacy_handler_text)


    def test_start_and_subscription_are_not_in_monolith(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, ast.FunctionDef)
        }
        for name in ("start", "callback_check_subscription", "check_channel_subscription", "check_subscription"):
            with self.subTest(name=name):
                self.assertNotIn(name, labels)

        for node in ast.parse(label_text).body:
            if isinstance(node, ast.FunctionDef):
                decorators = [ast.unparse(dec) for dec in node.decorator_list]
                self.assertNotIn("bot.message_handler(commands=['start'])", decorators)
                self.assertNotIn("bot.callback_query_handler(func=lambda call: call.data == 'check_subscription')", decorators)







    def test_runtime_helpers_are_only_thin_compat_wrappers_in_label(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        tree = ast.parse(label_text)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        max_lines = {
            "handle_referral_registration": 4,
        }
        for name in (
            "get_pg_connection",
            "return_pg_connection",
            "init_db_pool",
            "is_admin",
            "get_all_admins",
            "is_profile_complete",
            "get_user_balance_safe",
            "change_user_balance",
            "notify_referrer_about_visit",
            "handle_referral_registration",
            "start_bot_with_retry",
            "ensure_user_storage",
            "notify_admins",
            "handle_distribution_payment",
            "handle_successful_payment",
            "handle_design_payment",
            "handle_service_release_for_artist",
            "process_artist_user_id",
            "modify_distribution_for_artist_release",
            "generate_request_id",
            "get_display_username",
            "notify_admins_design",
        ):
            with self.subTest(name=name):
                self.assertIn(name, functions)
                line_count = functions[name].end_lineno - functions[name].lineno + 1
                self.assertLessEqual(line_count, max_lines.get(name, 2))



    def test_service_payment_entrypoints_are_detached_from_label_in_main(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        main_text = (root / "main.py").read_text(encoding="utf-8")
        self.assertIn("payment_callbacks.handle_design_payment", main_text)
        self.assertIn("payment_callbacks.handle_successful_payment", main_text)
        self.assertIn("service_artist_release.handle_service_release_for_artist", main_text)
        self.assertIn("service_artist_release.configure", main_text)
        self.assertIn("user_storage.ensure_user_storage", main_text)



    def test_runtime_helpers_are_detached_from_label_in_main(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        main_text = (root / "main.py").read_text(encoding="utf-8")
        for forbidden in (
            "label.get_pg_connection",
            "label.return_pg_connection",
            "label.init_db_pool",
            "label.is_admin",
            "label.get_all_admins",
            "label.is_profile_complete",
            "label.get_user_balance_safe",
            "label.change_user_balance",
            "label.handle_referral_registration",
            "label.notify_referrer_about_visit",
            "label.start_bot_with_retry",
            "label.ensure_user_storage",
            "label.handle_design_payment",
            "label.handle_successful_payment",
            "label.handle_service_release_for_artist",
            "label.process_artist_user_id",
            "label.modify_distribution_for_artist_release",
            "label.generate_request_id",
            "label.get_display_username",
            "label.notify_admins_design",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, main_text)



    def test_report_handlers_do_not_issue_sql_directly(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        forbidden_calls = {"execute", "cursor", "commit", "rollback"}
        for relative_path in ("handlers/admin_report_flow.py", "handlers/admin_send_reports.py"):
            with self.subTest(path=relative_path):
                module_text = (root / relative_path).read_text(encoding="utf-8")
                tree = ast.parse(module_text)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute) and node.attr in forbidden_calls:
                        self.fail(f"{relative_path} should use repositories, found .{node.attr}")
                for forbidden_text in ("SELECT ", "UPDATE ", "INSERT ", "DELETE "):
                    self.assertNotIn(forbidden_text, module_text)

    def test_report_flow_handlers_are_not_in_monolith(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, ast.FunctionDef)
        }
        for name in (
            "handle_report_request",
            "handle_start_report",
            "handle_attach_report",
            "process_report_file",
            "handle_complete_report",
            "handle_view_report",
            "handle_attach_xlsx_report",
            "process_xlsx_report_file",
            "process_report_file_upload",
            "handle_confirm_report_upload",
            "handle_admin_report_file_upload",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, labels)

        blocked_decorators = (
            "bot.callback_query_handler(func=lambda call: call.data.startswith('request_report_'))",
            "bot.callback_query_handler(func=lambda call: call.data.startswith('start_report_'))",
            "bot.callback_query_handler(func=lambda call: call.data.startswith('attach_report_'))",
            "bot.callback_query_handler(func=lambda call: call.data.startswith('complete_report_'))",
            "bot.callback_query_handler(func=lambda call: call.data.startswith('view_report_'))",
            "bot.callback_query_handler(func=lambda call: call.data.startswith('attach_xlsx_report_'))",
            "bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_report_upload_'))",
        )
        for node in ast.parse(label_text).body:
            if isinstance(node, ast.FunctionDef):
                decorators = [ast.unparse(dec) for dec in node.decorator_list]
                for decorator in blocked_decorators:
                    self.assertNotIn(decorator, decorators)

    def test_admin_send_report_handler_is_not_in_monolith(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, ast.FunctionDef)
        }
        for name in ("handle_admin_send_report", "create_detailed_xlsx_report", "send_xlsx_report"):
            with self.subTest(name=name):
                self.assertNotIn(name, labels)

        for node in ast.parse(label_text).body:
            if isinstance(node, ast.FunctionDef):
                decorators = [ast.unparse(dec) for dec in node.decorator_list]
                self.assertNotIn("bot.callback_query_handler(func=lambda call: call.data.startswith('admin_send_report_'))", decorators)

    def test_cover_document_handler_is_not_in_monolith(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertNotIn("handle_cover_test", labels)
        for node in ast.parse(label_text).body:
            if isinstance(node, ast.FunctionDef):
                decorators = [ast.unparse(dec) for dec in node.decorator_list]
                self.assertNotIn("bot.message_handler(content_types=['photo', 'document'])", decorators)

    def test_design_admin_handlers_are_not_in_monolith(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, ast.FunctionDef)
        }
        for name in (
            "handle_design_status_change",
            "handle_admin_order_detail",
            "show_order_detail",
            "build_design_status_markup",
            "format_design_request_text",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, labels)

        for node in ast.parse(label_text).body:
            if isinstance(node, ast.FunctionDef):
                decorators = [ast.unparse(dec) for dec in node.decorator_list]
                self.assertNotIn("bot.callback_query_handler(func=lambda call: call.data.startswith('design_status:'))", decorators)
                self.assertNotIn("bot.callback_query_handler(func=lambda call: call.data.startswith('order_detail_'))", decorators)

    def test_design_brief_handlers_are_not_in_monolith(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, ast.FunctionDef)
        }
        for name in ("handle_design_brief_request", "prompt_design_brief", "process_design_brief"):
            with self.subTest(name=name):
                self.assertNotIn(name, labels)

        for node in ast.parse(label_text).body:
            if isinstance(node, ast.FunctionDef):
                decorators = [ast.unparse(dec) for dec in node.decorator_list]
                self.assertNotIn("bot.callback_query_handler(func=lambda call: call.data.startswith('design_brief_'))", decorators)

    def test_service_selection_handlers_are_not_in_monolith(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, ast.FunctionDef)
        }
        for name in ("handle_service_selection", "show_distribution_form", "show_design_service"):
            with self.subTest(name=name):
                self.assertNotIn(name, labels)

        for node in ast.parse(label_text).body:
            if isinstance(node, ast.FunctionDef):
                decorators = [ast.unparse(dec) for dec in node.decorator_list]
                self.assertNotIn("bot.callback_query_handler(func=lambda call: call.data.startswith('service_'))", decorators)

    def test_service_payment_handlers_are_not_in_monolith(self):
        import ast

        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        label_text = (root / "label.py").read_text(encoding="utf-8")
        labels = {
            node.name
            for node in ast.parse(label_text).body
            if isinstance(node, ast.FunctionDef)
        }
        for name in ("handle_payment", "create_payment", "check_payment_status"):
            with self.subTest(name=name):
                self.assertNotIn(name, labels)

        for node in ast.parse(label_text).body:
            if isinstance(node, ast.FunctionDef):
                decorators = [ast.unparse(dec) for dec in node.decorator_list]
                self.assertNotIn("bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))", decorators)
                self.assertNotIn("bot.callback_query_handler(func=lambda call: call.data.startswith('check_payment_'))", decorators)

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

    def test_yookassa_callback_delegates_to_payment_handler(self):
        calls = []
        bot = FakeBot()
        register_optional_handlers(bot, topup_payment_handlers={"yookassa": calls.append})
        call = make_call("yookassa_pay_500")
        matching_handlers = [
            handler["function"]
            for handler in bot.callback_query_handlers
            if handler.get("filters", {}).get("func") and handler["filters"]["func"](call)
        ]

        self.assertEqual(len(matching_handlers), 1)
        matching_handlers[0](call)

        self.assertEqual(calls, [call])

    def test_yookassa_callback_reports_missing_provider(self):
        call = make_call("yookassa_pay_500")
        matching_handlers = [
            handler["function"]
            for handler in self.bot.callback_query_handlers
            if handler.get("filters", {}).get("func") and handler["filters"]["func"](call)
        ]

        self.assertEqual(len(matching_handlers), 1)
        matching_handlers[0](call)

        self.assertEqual(len(self.bot.callback_answers), 1)
        self.assertIn("недоступен", self.bot.callback_answers[0]["text"])
        self.assertTrue(self.bot.callback_answers[0]["kwargs"].get("show_alert"))

    def test_crypto_callback_delegates_to_payment_handler(self):
        calls = []
        bot = FakeBot()
        register_optional_handlers(bot, topup_payment_handlers={"crypto": calls.append})
        call = make_call("crypto_pay_500")
        matching_handlers = [
            handler["function"]
            for handler in bot.callback_query_handlers
            if handler.get("filters", {}).get("func") and handler["filters"]["func"](call)
        ]

        self.assertEqual(len(matching_handlers), 1)
        matching_handlers[0](call)

        self.assertEqual(calls, [call])

    def test_crypto_callback_reports_missing_provider(self):
        call = make_call("crypto_pay_500")
        matching_handlers = [
            handler["function"]
            for handler in self.bot.callback_query_handlers
            if handler.get("filters", {}).get("func") and handler["filters"]["func"](call)
        ]

        self.assertEqual(len(matching_handlers), 1)
        matching_handlers[0](call)

        self.assertEqual(len(self.bot.callback_answers), 1)
        self.assertIn("недоступен", self.bot.callback_answers[0]["text"])
        self.assertTrue(self.bot.callback_answers[0]["kwargs"].get("show_alert"))


if __name__ == "__main__":
    unittest.main()

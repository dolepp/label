#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the current monolithic bot.

The project is being migrated from label.py to modules gradually. Until a
feature is fully moved and verified, startup must go through the legacy module
without exec(), so __name__ guards inside label.py keep their normal behavior.
"""
import logging
import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def configure_telegram_timeouts() -> None:
    try:
        import telebot.apihelper

        telebot.apihelper.READ_TIMEOUT = 30
        telebot.apihelper.CONNECT_TIMEOUT = 10
    except Exception as exc:
        logger.warning("Could not configure Telegram API timeouts: %s", exc)


def start_bot() -> None:
    import label

    configure_telegram_timeouts()
    try:
        from handlers import register_optional_handlers
        from handlers.admin_report_flow import process_xlsx_report_file as modular_process_xlsx_report_file
        from keyboards.reply import create_main_menu
        from db.repositories.referrals import handle_referral_registration
        from services import bot_runner, payment_callbacks, referral_notifications, runtime_helpers, service_artist_release, user_storage

        referral_notifications.configure(label.bot)
        user_storage.configure(label.bot)
        payment_callbacks.configure(
            bot=label.bot,
            get_pg_connection=runtime_helpers.get_pg_connection,
            return_pg_connection=runtime_helpers.return_pg_connection,
            get_user_balance_safe=runtime_helpers.get_user_balance_safe,
            change_user_balance=runtime_helpers.change_user_balance,
            ensure_user_storage=user_storage.ensure_user_storage,
            notify_admins_design=getattr(label, "notify_admins_design", None),
            get_display_username=getattr(label, "get_display_username", None),
            generate_request_id=getattr(label, "generate_request_id", None),
            DESIGN_BRIEF_REQUESTS=getattr(label, "DESIGN_BRIEF_REQUESTS", []),
            SERVICE_LABELS=getattr(label, "SERVICE_LABELS", {}),
        )
        service_artist_release.configure(
            bot=label.bot,
            is_admin=runtime_helpers.is_admin,
            process_artist_user_id=getattr(label, "process_artist_user_id", None),
        )

        register_optional_handlers(
            label.bot,
            topup_payment_context={
                "get_pg_connection": runtime_helpers.get_pg_connection,
                "return_pg_connection": runtime_helpers.return_pg_connection,
                "logger": logger,
                "yookassa_available": getattr(label, "YOOKASSA_AVAILABLE", False),
                "yookassa_configuration": getattr(label, "Configuration", None),
                "yookassa_payment": getattr(label, "Payment", None),
                "crypto_bot_token": getattr(label, "CRYPTO_BOT_TOKEN", ""),
            },
            legacy_distribution_context={
                "get_pg_connection": runtime_helpers.get_pg_connection,
                "return_pg_connection": runtime_helpers.return_pg_connection,
                "create_main_menu": create_main_menu,
                "is_profile_complete": runtime_helpers.is_profile_complete,
                "is_admin": runtime_helpers.is_admin,
                "BOT_TOKEN": getattr(label, "BOT_TOKEN", ""),
            },
            onboarding_context={
                "get_pg_connection": runtime_helpers.get_pg_connection,
                "return_pg_connection": runtime_helpers.return_pg_connection,
                "handle_referral_registration": handle_referral_registration,
                "notify_referrer_about_visit": referral_notifications.notify_referrer_about_visit,
                "CHANNEL_USERNAME": getattr(label, "CHANNEL_USERNAME", "@twaslabel"),
            },
            service_payment_context={
                "get_pg_connection": runtime_helpers.get_pg_connection,
                "return_pg_connection": runtime_helpers.return_pg_connection,
                "get_user_balance_safe": runtime_helpers.get_user_balance_safe,
                "change_user_balance": runtime_helpers.change_user_balance,
                "ensure_user_storage": user_storage.ensure_user_storage,
                "handle_design_payment": payment_callbacks.handle_design_payment,
                "handle_successful_payment": payment_callbacks.handle_successful_payment,
                "Payment": getattr(label, "Payment", None),
                "DESIGN_BRIEF_TEMPLATES": getattr(label, "DESIGN_BRIEF_TEMPLATES", {}),
            },
            service_selection_context={
                "handle_service_release_for_artist": service_artist_release.handle_service_release_for_artist,
            },
            design_brief_context={
                "DESIGN_BRIEF_TEMPLATES": getattr(label, "DESIGN_BRIEF_TEMPLATES", {}),
                "ensure_user_storage": user_storage.ensure_user_storage,
                "is_cancel_message": runtime_helpers.is_cancel_message,
            },
            design_admin_context={
                "DESIGN_ORDER_STATUSES": getattr(label, "DESIGN_ORDER_STATUSES", []),
                "DESIGN_BRIEF_TEMPLATES": getattr(label, "DESIGN_BRIEF_TEMPLATES", {}),
                "DESIGN_BRIEF_REQUESTS": getattr(label, "DESIGN_BRIEF_REQUESTS", []),
            },
            diagnostics_context={
                "process_xlsx_report_file": modular_process_xlsx_report_file,
            },
            admin_report_flow_context={
                "is_admin": runtime_helpers.is_admin,
                "has_access_level": runtime_helpers.has_access_level,
                "get_all_admins": runtime_helpers.get_all_admins,
            },
        )
    except Exception as exc:
        logger.error("Could not register optional modular handlers: %s", exc)
        raise

    bot_runner.start_bot_with_retry(
        label.bot,
        get_connection=runtime_helpers.get_pg_connection,
        return_connection=runtime_helpers.return_pg_connection,
    )


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("TWAS Label Bot - legacy-compatible launcher")
    logger.info("=" * 50)
    start_bot()

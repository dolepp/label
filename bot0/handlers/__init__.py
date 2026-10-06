"""Handler registration helpers for modular bot code."""
from __future__ import annotations


def register_optional_handlers(
    bot,
    topup_payment_handlers: dict | None = None,
    topup_payment_context: dict | None = None,
    legacy_distribution_context: dict | None = None,
    onboarding_context: dict | None = None,
    service_payment_context: dict | None = None,
    service_selection_context: dict | None = None,
    design_brief_context: dict | None = None,
    design_admin_context: dict | None = None,
    diagnostics_context: dict | None = None,
    admin_send_report_context: dict | None = None,
    admin_report_flow_context: dict | None = None,
) -> None:
    """Register all modular handlers.

    The legacy feature-flag gate has been removed: migrated handlers are now the
    canonical implementation and should always be attached by the launcher.
    """
    from handlers.admin_broadcast import register_admin_broadcast_handlers
    from handlers.admin_contracts import register_admin_contract_handlers
    from handlers.admin_finance import register_admin_finance_handlers
    from handlers.admin_menu import register_admin_menu_handlers
    from handlers.admin_promos import register_admin_promo_handlers
    from handlers.admin_releases import register_admin_release_handlers
    from handlers.admin_reports import register_admin_report_handlers
    from handlers.admin_report_flow import register_admin_report_flow_handlers
    from handlers.admin_send_reports import register_admin_send_report_handlers
    from handlers.admin_services import register_admin_service_handlers
    from handlers.admin_stats import register_admin_stats_handlers
    from handlers.admin_user_info import register_admin_user_info_handlers
    from handlers.admin_user_releases import register_admin_user_release_handlers
    from handlers.admin_user_reports import register_admin_user_report_handlers
    from handlers.admin_user_roles import register_admin_user_role_handlers
    from handlers.admin_users import register_admin_user_handlers
    from handlers.bookings import register_booking_handlers
    from handlers.common import register_common_handlers
    from handlers.contracts import register_contract_handlers
    from handlers.design_admin import register_design_admin_handlers
    from handlers.design_briefs import register_design_brief_handlers
    from handlers.diagnostics import register_diagnostics_handlers
    from handlers.drafts import register_draft_handlers
    from handlers.finance import register_finance_handlers
    from handlers.info import register_info_handlers
    from handlers.legacy_distribution import register_legacy_distribution_handlers
    from handlers.onboarding import register_onboarding_handlers
    from handlers.orders import register_order_handlers
    from handlers.profile import register_profile_handlers
    from handlers.promos import register_promo_handlers
    from handlers.referrals import register_referral_handlers
    from handlers.release_details import register_release_detail_handlers
    from handlers.release_edit import register_release_edit_handlers
    from handlers.release_files import register_release_file_handlers
    from handlers.release_links import register_release_link_handlers
    from handlers.release_preview import register_release_preview_handlers
    from handlers.release_status import register_release_status_handlers
    from handlers.releases import register_release_handlers
    from handlers.reports import register_report_handlers
    from handlers.reviews import register_reviews_handlers
    from handlers.service_payments import register_service_payment_handlers
    from handlers.service_selection import register_service_selection_handlers
    from handlers.support import register_support_handlers
    from handlers.topups import register_topup_handlers
    from handlers.web_auth import register_web_auth_handlers

    from handlers.account_connections import register_account_connection_handlers
    register_account_connection_handlers(bot)
    register_common_handlers(bot)
    register_reviews_handlers(bot)
    register_onboarding_handlers(bot, context=onboarding_context)
    register_profile_handlers(bot)
    register_support_handlers(bot)
    register_report_handlers(bot)
    register_contract_handlers(bot)
    register_order_handlers(bot)
    register_draft_handlers(bot)
    register_promo_handlers(bot)
    register_finance_handlers(bot)
    register_referral_handlers(bot)
    register_release_handlers(bot)
    register_legacy_distribution_handlers(bot, context=legacy_distribution_context)
    register_release_detail_handlers(bot)
    register_release_file_handlers(bot)
    register_release_edit_handlers(bot)
    register_release_link_handlers(bot)
    register_release_preview_handlers(bot)
    register_release_status_handlers(bot)
    register_booking_handlers(bot)
    register_info_handlers(bot)
    register_service_selection_handlers(bot, context=service_selection_context)
    register_design_brief_handlers(bot, context=design_brief_context)
    register_design_admin_handlers(bot, context=design_admin_context)
    register_service_payment_handlers(bot, context=service_payment_context)
    register_admin_broadcast_handlers(bot)
    register_admin_contract_handlers(bot)
    register_admin_finance_handlers(bot)
    register_admin_promo_handlers(bot)
    register_admin_release_handlers(bot)
    register_admin_report_handlers(bot)
    register_admin_report_flow_handlers(bot, context=admin_report_flow_context)
    register_admin_send_report_handlers(bot, context=admin_send_report_context)
    register_admin_stats_handlers(bot)
    register_admin_menu_handlers(bot)
    register_admin_service_handlers(bot)
    register_admin_user_handlers(bot)
    register_admin_user_info_handlers(bot)
    register_admin_user_report_handlers(bot)
    register_admin_user_release_handlers(bot)
    register_admin_user_role_handlers(bot)
    register_web_auth_handlers(bot)
    register_diagnostics_handlers(bot, context=diagnostics_context)
    register_topup_handlers(
        bot,
        payment_handlers=topup_payment_handlers,
        payment_context=topup_payment_context,
    )

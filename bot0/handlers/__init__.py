"""Handler registration helpers for modular code."""
from core.config import (
    ENABLE_MODULAR_ADMIN_FINANCE,
    ENABLE_MODULAR_ADMIN_MENU,
    ENABLE_MODULAR_ADMIN_PROMOS,
    ENABLE_MODULAR_ADMIN_RELEASES,
    ENABLE_MODULAR_ADMIN_REPORTS,
    ENABLE_MODULAR_ADMIN_STATS,
    ENABLE_MODULAR_ADMIN_SERVICES,
    ENABLE_MODULAR_ADMIN_USERS,
    ENABLE_MODULAR_ADMIN_USER_INFO,
    ENABLE_MODULAR_ADMIN_USER_REPORTS,
    ENABLE_MODULAR_ADMIN_USER_RELEASES,
    ENABLE_MODULAR_ADMIN_USER_ROLES,
    ENABLE_MODULAR_ADMIN_CONTRACTS,
    ENABLE_MODULAR_BOOKINGS,
    ENABLE_MODULAR_COMMON,
    ENABLE_MODULAR_CONTRACTS,
    ENABLE_MODULAR_DRAFTS,
    ENABLE_MODULAR_DIAGNOSTICS,
    ENABLE_MODULAR_FINANCE,
    ENABLE_MODULAR_INFO,
    ENABLE_MODULAR_PROFILE,
    ENABLE_MODULAR_PROMOS,
    ENABLE_MODULAR_REFERRALS,
    ENABLE_MODULAR_RELEASE_DETAILS,
    ENABLE_MODULAR_RELEASE_EDIT_MENU,
    ENABLE_MODULAR_RELEASE_LINKS,
    ENABLE_MODULAR_RELEASES,
    ENABLE_MODULAR_RELEASE_STATUS_MENU,
    ENABLE_MODULAR_ORDERS,
    ENABLE_MODULAR_REPORTS,
    ENABLE_MODULAR_REVIEWS,
    ENABLE_MODULAR_SUPPORT,
    ENABLE_MODULAR_TOPUPS,
    ENABLE_MODULAR_WEB_AUTH,
)


def register_optional_handlers(bot) -> None:
    """Register modular handlers guarded by feature flags.

    The legacy monolith still registers the same callback prefixes, so modular
    handlers must be enabled explicitly while migration is in progress.
    """
    if ENABLE_MODULAR_COMMON:
        from handlers.common import register_common_handlers

        register_common_handlers(bot)

    if ENABLE_MODULAR_REVIEWS:
        from handlers.reviews import register_reviews_handlers

        register_reviews_handlers(bot)

    if ENABLE_MODULAR_PROFILE:
        from handlers.profile import register_profile_handlers

        register_profile_handlers(bot)

    if ENABLE_MODULAR_SUPPORT:
        from handlers.support import register_support_handlers

        register_support_handlers(bot)

    if ENABLE_MODULAR_REPORTS:
        from handlers.reports import register_report_handlers

        register_report_handlers(bot)

    if ENABLE_MODULAR_CONTRACTS:
        from handlers.contracts import register_contract_handlers

        register_contract_handlers(bot)

    if ENABLE_MODULAR_ORDERS:
        from handlers.orders import register_order_handlers

        register_order_handlers(bot)

    if ENABLE_MODULAR_DRAFTS:
        from handlers.drafts import register_draft_handlers

        register_draft_handlers(bot)

    if ENABLE_MODULAR_PROMOS:
        from handlers.promos import register_promo_handlers

        register_promo_handlers(bot)

    if ENABLE_MODULAR_FINANCE:
        from handlers.finance import register_finance_handlers

        register_finance_handlers(bot)

    if ENABLE_MODULAR_REFERRALS:
        from handlers.referrals import register_referral_handlers

        register_referral_handlers(bot)

    if ENABLE_MODULAR_RELEASES:
        from handlers.releases import register_release_handlers

        register_release_handlers(bot)

    if ENABLE_MODULAR_RELEASE_DETAILS:
        from handlers.release_details import register_release_detail_handlers

        register_release_detail_handlers(bot)

    if ENABLE_MODULAR_RELEASE_EDIT_MENU:
        from handlers.release_edit import register_release_edit_handlers

        register_release_edit_handlers(bot)

    if ENABLE_MODULAR_RELEASE_LINKS:
        from handlers.release_links import register_release_link_handlers

        register_release_link_handlers(bot)

    if ENABLE_MODULAR_RELEASE_STATUS_MENU:
        from handlers.release_status import register_release_status_handlers

        register_release_status_handlers(bot)

    if ENABLE_MODULAR_BOOKINGS:
        from handlers.bookings import register_booking_handlers

        register_booking_handlers(bot)

    if ENABLE_MODULAR_INFO:
        from handlers.info import register_info_handlers

        register_info_handlers(bot)

    if ENABLE_MODULAR_ADMIN_CONTRACTS:
        from handlers.admin_contracts import register_admin_contract_handlers

        register_admin_contract_handlers(bot)

    if ENABLE_MODULAR_ADMIN_FINANCE:
        from handlers.admin_finance import register_admin_finance_handlers

        register_admin_finance_handlers(bot)

    if ENABLE_MODULAR_ADMIN_PROMOS:
        from handlers.admin_promos import register_admin_promo_handlers

        register_admin_promo_handlers(bot)

    if ENABLE_MODULAR_ADMIN_RELEASES:
        from handlers.admin_releases import register_admin_release_handlers

        register_admin_release_handlers(bot)

    if ENABLE_MODULAR_ADMIN_REPORTS:
        from handlers.admin_reports import register_admin_report_handlers

        register_admin_report_handlers(bot)

    if ENABLE_MODULAR_ADMIN_STATS:
        from handlers.admin_stats import register_admin_stats_handlers

        register_admin_stats_handlers(bot)

    if ENABLE_MODULAR_ADMIN_MENU:
        from handlers.admin_menu import register_admin_menu_handlers

        register_admin_menu_handlers(bot)

    if ENABLE_MODULAR_ADMIN_SERVICES:
        from handlers.admin_services import register_admin_service_handlers

        register_admin_service_handlers(bot)

    if ENABLE_MODULAR_ADMIN_USERS:
        from handlers.admin_users import register_admin_user_handlers

        register_admin_user_handlers(bot)

    if ENABLE_MODULAR_ADMIN_USER_INFO:
        from handlers.admin_user_info import register_admin_user_info_handlers

        register_admin_user_info_handlers(bot)

    if ENABLE_MODULAR_ADMIN_USER_REPORTS:
        from handlers.admin_user_reports import register_admin_user_report_handlers

        register_admin_user_report_handlers(bot)

    if ENABLE_MODULAR_ADMIN_USER_RELEASES:
        from handlers.admin_user_releases import register_admin_user_release_handlers

        register_admin_user_release_handlers(bot)

    if ENABLE_MODULAR_ADMIN_USER_ROLES:
        from handlers.admin_user_roles import register_admin_user_role_handlers

        register_admin_user_role_handlers(bot)

    if ENABLE_MODULAR_WEB_AUTH:
        from handlers.web_auth import register_web_auth_handlers

        register_web_auth_handlers(bot)

    if ENABLE_MODULAR_DIAGNOSTICS:
        from handlers.diagnostics import register_diagnostics_handlers

        register_diagnostics_handlers(bot)

    if ENABLE_MODULAR_TOPUPS:
        from handlers.topups import register_topup_handlers

        register_topup_handlers(bot)

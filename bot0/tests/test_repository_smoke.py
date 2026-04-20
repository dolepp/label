from __future__ import annotations

import unittest
from decimal import Decimal

from db.pool import connection
from db.repositories.bookings import list_user_bookings
from db.repositories.admin_finance import get_finance_breakdown
from db.repositories.admin_contracts import get_admin_contract, list_admin_contracts
from db.repositories.admin_reports import list_admin_report_requests
from db.repositories.admin_stats import get_admin_stats
from db.repositories.admin_user_info import get_admin_user_info
from db.repositories.admin_user_releases import list_admin_user_releases
from db.repositories.admin_user_reports import get_user_identity, list_user_report_requests_for_admin
from db.repositories.admin_user_roles import get_user_roles
from db.repositories.admin_users import list_admin_user_cards
from db.repositories.admins import ensure_admin_access
from db.repositories.contracts import get_user_contract, list_user_contracts
from db.repositories.drafts import count_user_drafts
from db.repositories.finance import get_user_finance_summary
from db.repositories.orders import count_user_orders, list_user_orders
from db.repositories.promos import activate_promo, get_admin_promo_stats, get_promo_counts
from db.repositories.releases import list_user_release_cards
from db.repositories.release_details import get_album_detail, get_release_detail
from db.repositories.release_edit import get_release_edit_access
from db.repositories.release_files import get_release_file_id
from db.repositories.release_links import get_release_back_callback, get_release_platform_links
from db.repositories.reports import list_user_reports
from db.repositories.reviews import count_pending_reviews, list_approved_reviews
from db.repositories.stats import get_user_stats, has_active_discount_promo
from db.repositories.support import get_support_status_counts, list_user_support_requests


def _first_user_id() -> int | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT telegram_id FROM label WHERE telegram_id IS NOT NULL ORDER BY id LIMIT 1")
            row = cur.fetchone()
            return int(row[0]) if row else None
        finally:
            cur.close()


class RepositorySmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user_id = _first_user_id()
        if cls.user_id is None:
            raise unittest.SkipTest("PostgreSQL label database is unavailable or empty")

    def test_finance_summary_is_readable(self):
        summary = get_user_finance_summary(self.user_id)
        self.assertIsNotNone(summary)
        self.assertIn("balance", summary)
        self.assertIsInstance(summary["balance"], Decimal)

    def test_user_stats_are_readable(self):
        stats = get_user_stats(self.user_id)
        self.assertIsNotNone(stats)
        self.assertIn("releases_count", stats)
        self.assertIsInstance(has_active_discount_promo(self.user_id), bool)

    def test_admin_finance_breakdown_is_readable(self):
        stats = get_finance_breakdown()
        self.assertIn("total_revenue", stats)
        self.assertIn("monthly_revenue", stats)
        self.assertIn("today_revenue", stats)

    def test_admin_stats_are_readable(self):
        stats = get_admin_stats()
        self.assertIn("total_users", stats)
        self.assertIn("total_revenue", stats)

    def test_admin_users_are_readable(self):
        users = list_admin_user_cards()
        self.assertIsInstance(users, list)
        self.assertTrue(any(user["telegram_id"] == self.user_id for user in users))
        roles = get_user_roles(self.user_id)
        self.assertIsNotNone(roles)
        self.assertIn("admin", roles)
        user_info = get_admin_user_info(self.user_id)
        self.assertIsNotNone(user_info)
        self.assertIn("releases_count", user_info)
        self.assertIsNotNone(get_user_identity(self.user_id))
        self.assertIsInstance(list_user_report_requests_for_admin(self.user_id), list)
        releases = list_admin_user_releases(self.user_id)
        self.assertIn("albums", releases)
        self.assertIn("singles", releases)

    def test_admin_reports_are_readable(self):
        reports = list_admin_report_requests()
        self.assertIsInstance(reports, list)

    def test_admin_contracts_are_readable(self):
        contracts = list_admin_contracts()
        self.assertIsInstance(contracts, list)
        if contracts:
            self.assertIsNotNone(get_admin_contract(contracts[0]["id"]))

    def test_user_contracts_are_readable(self):
        contracts = list_user_contracts(self.user_id)
        self.assertIsInstance(contracts, list)
        if contracts:
            self.assertIsNotNone(get_user_contract(contracts[0]["id"], self.user_id))

    def test_permanent_admin_access_is_readable(self):
        result = ensure_admin_access(1398275867, "test_user")
        self.assertTrue(result["allowed"])

    def test_orders_are_readable(self):
        count = count_user_orders(self.user_id)
        orders = list_user_orders(self.user_id, limit=5)
        self.assertIsInstance(count, int)
        self.assertLessEqual(len(orders), 5)

    def test_releases_are_readable(self):
        releases = list_user_release_cards(self.user_id, limit=5)
        self.assertIsInstance(releases, list)
        self.assertLessEqual(len(releases), 5)
        if releases:
            first = releases[0]
            if first["is_album"]:
                self.assertIsNotNone(get_album_detail(first["id"], user_id=self.user_id))
            else:
                self.assertIsNotNone(get_release_detail(first["id"], user_id=self.user_id))
            self.assertIsInstance(get_release_platform_links(first["id"]), dict)
            self.assertIsInstance(get_release_back_callback(first["id"]), str)
            self.assertIsNotNone(get_release_edit_access(first["id"]))
            file_id = get_release_file_id(first["id"], "cover")
            self.assertTrue(file_id is None or isinstance(file_id, str))

    def test_bookings_are_readable_when_table_is_missing(self):
        bookings = list_user_bookings(self.user_id, limit=5)
        self.assertIsInstance(bookings, list)

    def test_reports_drafts_support_reviews_are_readable(self):
        self.assertIsInstance(list_user_reports(self.user_id), list)
        self.assertIsInstance(count_user_drafts(self.user_id), int)
        self.assertIsInstance(list_user_support_requests(self.user_id), list)
        self.assertIsInstance(get_support_status_counts(), dict)
        self.assertIsInstance(list_approved_reviews(limit=3), list)
        self.assertIsInstance(count_pending_reviews(), int)

    def test_promo_read_only_paths(self):
        counts = get_promo_counts()
        self.assertIn("total", counts)
        admin_stats = get_admin_promo_stats()
        self.assertIn("active", admin_stats)
        result = activate_promo(self.user_id, "NO_SUCH_PROMO_FOR_TEST")
        self.assertEqual(result["status"], "not_found")


if __name__ == "__main__":
    unittest.main()

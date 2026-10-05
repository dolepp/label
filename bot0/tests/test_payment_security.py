"""Payment flows must not trust amounts or roles sent in callback data / message text."""
from __future__ import annotations

import unittest
from unittest import mock

from handlers import legacy_distribution_steps as steps
from services import payments
from tests.fakes import FakeBot, make_call, make_message

USER_ID = 1398275867


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._result = []

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        self.db.queries.append((sql, params))
        if "SELECT COALESCE(artist, 0) FROM label" in sql or "SELECT artist FROM label" in sql:
            self._result = [(1 if self.db.artist else 0,)]
        elif sql.startswith("UPDATE label SET balance = balance - %s") or "AND COALESCE(balance,0) >= %s" in sql:
            amount = params[0] if sql.startswith("UPDATE label SET balance = balance - %s") else -params[0]
            if self.db.balance >= amount:
                self.db.balance -= amount
                self._result = [(self.db.balance,)]
            else:
                self._result = []
        elif sql.startswith("UPDATE label SET balance = COALESCE(balance,0) + %s"):
            self.db.balance += params[0]
            self._result = [(self.db.balance,)]
        elif "SELECT COALESCE(balance, 0) FROM label" in sql:
            self._result = [(self.db.balance,)]
        elif "FROM user_discount_promos udp" in sql and "pc.id = %s" in sql:
            promo_id = params[1]
            self._result = [("SALE", self.db.promos[promo_id])] if promo_id in self.db.owned_promos else []
        else:
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)

    def close(self):
        pass


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def commit(self):
        pass

    def rollback(self):
        pass


class FakeDb:
    def __init__(self, balance=5000.0, artist=False):
        self.balance = balance
        self.artist = artist
        self.promos = {7: 50, 8: 100}
        self.owned_promos = {7}
        self.queries = []


class DistributionPaymentTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.bot = FakeBot()
        self.saved = []
        steps.configure_legacy_distribution_steps(
            bot=self.bot,
            get_pg_connection=lambda: FakeConn(self.db),
            return_pg_connection=lambda conn: None,
        )
        patcher = mock.patch.object(steps, "save_release_data_for_user", lambda user_id, chat_id: self.saved.append(user_id))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.bot.user_data[USER_ID] = {"release_type": "EP"}

    def test_negative_amount_cannot_credit_balance(self):
        steps.handle_distribution_pay(make_call("distribution_pay_-5000"))
        self.assertEqual(self.db.balance, 5000.0)
        self.assertEqual(self.saved, [])

    def test_forged_low_amount_is_rejected(self):
        steps.handle_distribution_pay(make_call("distribution_pay_1"))
        self.assertEqual(self.db.balance, 5000.0)
        self.assertEqual(self.saved, [])

    def test_correct_amount_is_charged_once(self):
        steps.handle_distribution_pay(make_call("distribution_pay_2399"))
        self.assertEqual(self.db.balance, 5000.0 - 2399)
        self.assertEqual(self.saved, [USER_ID])

    def test_insufficient_balance_does_not_charge(self):
        self.db.balance = 100.0
        steps.handle_distribution_pay(make_call("distribution_pay_2399"))
        self.assertEqual(self.db.balance, 100.0)
        self.assertEqual(self.saved, [])

    def test_owned_promo_discount_is_applied(self):
        self.bot.user_data[USER_ID]["distribution_promo_id"] = 7
        steps.handle_distribution_pay(make_call("distribution_pay_1199"))
        self.assertEqual(self.db.balance, 5000.0 - 1199)

    def test_foreign_promo_cannot_be_applied(self):
        steps.handle_apply_promo_distribution(make_call("apply_promo_dist_8"))
        self.assertNotIn("distribution_promo_id", self.bot.user_data[USER_ID])
        self.assertEqual(self.bot.callback_answers[-1]["text"], "Промокод недоступен")

    def test_artist_is_not_charged(self):
        self.db.artist = True
        steps.handle_distribution_pay(make_call("distribution_pay_2399"))
        self.assertEqual(self.db.balance, 5000.0)
        self.assertEqual(self.saved, [USER_ID])

    def test_free_submit_text_requires_artist_role(self):
        steps.process_preview_confirmation(make_message("✅ Отправить бесплатно"))
        self.assertEqual(self.saved, [])
        self.db.artist = True
        steps.process_preview_confirmation(make_message("✅ Отправить бесплатно"))
        self.assertEqual(self.saved, [USER_ID])


class BalanceChangeTests(unittest.TestCase):
    def test_debit_never_goes_negative(self):
        db = FakeDb(balance=100.0)
        logger = mock.Mock()
        self.assertFalse(payments.change_user_balance(USER_ID, -500, lambda: FakeConn(db), lambda conn: None, logger))
        self.assertEqual(db.balance, 100.0)
        self.assertTrue(payments.change_user_balance(USER_ID, -60, lambda: FakeConn(db), lambda conn: None, logger))
        self.assertEqual(db.balance, 40.0)


if __name__ == "__main__":
    unittest.main()

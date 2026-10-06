"""Abuse regressions: no real database or payment provider is used."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import threading
import unittest
from unittest import mock

from db.repositories import promos, referrals, reviews
from handlers import admin_promos, onboarding, reviews as review_handlers, topups
from tests.fakes import FakeBot, make_call, make_message


class FakeDb:
    def __init__(self):
        self.lock = threading.RLock()
        self.queries = []
        self.fail_credit = False
        self.state = dict(
            promo=[1, 'CODE', Decimal(100), Decimal(0), False, None, None,
                   None, 0, None, True, None, 0],
            balances={10: 0, 20: 0}, usage=set(), discounts=set(),
            referrals=set(), earnings=0, count=0, referrer=10, new_user=True,
            reviews=[], order=[20, Decimal(100), 'pending'],
        )

    @contextmanager
    def connection(self):
        conn = FakeConn(self)
        try:
            yield conn
        finally:
            conn.rollback()


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.snapshot = None

    def begin(self):
        if self.snapshot is None:
            self.db.lock.acquire()
            self.snapshot = deepcopy(self.db.state)

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        if self.snapshot is not None:
            self.snapshot = None
            self.db.lock.release()

    def rollback(self):
        if self.snapshot is not None:
            self.db.state = self.snapshot
            self.snapshot = None
            self.db.lock.release()


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.db = conn.db
        self.result = []

    def execute(self, sql, params=()):
        sql = ' '.join(sql.split())
        self.db.queries.append((sql, params))
        self.result = []
        if 'FOR UPDATE' in sql or 'pg_advisory_xact_lock' in sql:
            self.conn.begin()
        s = self.db.state
        p = s['promo']
        if sql.startswith(('CREATE ', 'ALTER ', 'SELECT pg_advisory')):
            return
        if 'FROM promo_codes' in sql:
            self.result = [tuple(p)] if p[10] and params[0] == p[1] else []
        elif 'FROM promo_code_usage' in sql:
            self.result = [(1,)] if params in s['usage'] else []
        elif 'FROM user_discount_promos' in sql:
            self.result = [(1,)] if params in s['discounts'] else []
        elif sql.startswith('SELECT id FROM label'):
            self.result = [(params[0],)]
        elif sql.startswith('INSERT INTO user_discount_promos'):
            if params not in s['discounts']:
                s['discounts'].add(params)
                self.result = [(params[0],)]
        elif sql.startswith('INSERT INTO promo_code_usage'):
            s['usage'].add(params)
        elif sql.startswith('UPDATE promo_codes'):
            if 'SET current_activations = %s' in sql:
                p[12], p[8] = params[:2]
            elif 'SET current_uses = %s' in sql:
                p[8] = params[0]
                p[12] += 1
            else:
                p[10] = False
        elif 'SELECT telegram_id, name, referral_count' in sql:
            self.result = [(s['referrer'], 'Name', s['count'])]
        elif sql.startswith('INSERT INTO referrals'):
            self.conn.begin()
            if params[1] not in s['referrals']:
                s['referrals'].add(params[1])
                self.result = [(1,)]
        elif sql.startswith('UPDATE label SET referral_count'):
            s['count'] += 1
            s['earnings'] += 100
            s['balances'][params[0]] += 100
        elif sql.startswith('UPDATE label SET balance'):
            if self.db.fail_credit:
                raise RuntimeError('fake credit failure')
            if len(params) == 1:
                s['balances'][params[0]] += 50
            else:
                s['balances'][params[1]] += params[0]
            self.result = [(1,)]
        elif sql.startswith('SELECT 1 FROM reviews'):
            self.result = [(1,)] if params[0] in s['reviews'] else []
        elif sql.startswith('INSERT INTO reviews'):
            s['reviews'].append(params[0])
            self.result = [(len(s['reviews']),)]
        elif sql.startswith('SELECT 1 FROM orders'):
            self.result = [(1,)] if params[1] == s['order'][0] and params[0] == '123' else []
        elif sql.startswith('SELECT user_id, amount, status FROM orders'):
            self.result = [tuple(s['order'])]
        elif sql.startswith('UPDATE orders'):
            if s['order'][2] == 'pending':
                s['order'][2] = 'completed'
                self.result = [(1,)]
        else:
            raise AssertionError('Unexpected SQL: ' + sql)

    def fetchone(self):
        return self.result[0] if self.result else None

    def close(self):
        pass


def dispatch(bot, data, user=20):
    call = make_call(data, user_id=user)
    for handler in bot.callback_query_handlers:
        if handler['filters']['func'](call):
            handler['function'](call)
            return
    raise AssertionError('Missing callback: ' + data)


class PromoSecurityTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        patcher = mock.patch.object(promos, 'connection', self.db.connection)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_full_discount_activates_once_without_credit(self):
        self.db.state['promo'][2:4] = [Decimal(0), Decimal(100)]
        self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'discount_activated')
        self.assertEqual(self.db.state['discounts'], {(20, 1)})
        self.assertEqual(self.db.state['balances'][20], 0)
        self.assertEqual(self.db.state['promo'][8], 1)
        self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'discount_already_active')
        self.assertEqual(self.db.state['promo'][8], 1)

    def test_invalid_discount_or_negative_amount_is_rejected(self):
        for amount, discount in ((0, -1), (0, 101), (-1, 100), (0, 0)):
            with self.subTest(amount=amount, discount=discount):
                self.db.state = FakeDb().state
                self.db.state['promo'][2:4] = [Decimal(amount), Decimal(discount)]
                self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'invalid')
                self.assertFalse(self.db.state['discounts'])
                self.assertEqual(self.db.state['promo'][8], 0)

    def test_same_user_credited_once(self):
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: promos.activate_promo(20, 'CODE'), range(2)))
        self.assertEqual(sorted(r['status'] for r in results), ['already_used', 'balance_activated'])
        self.assertEqual(self.db.state['balances'][20], 100)

    def test_concurrent_global_limits_for_both_promo_types(self):
        for discount in (0, 20):
            for limit_index in (7, 11):
                with self.subTest(discount=discount, limit=limit_index):
                    self.db.state = FakeDb().state
                    self.db.state['promo'][3] = Decimal(discount)
                    self.db.state['promo'][limit_index] = 1
                    with ThreadPoolExecutor(2) as pool:
                        results = list(pool.map(lambda uid: promos.activate_promo(uid, 'CODE'), (10, 20)))
                    self.assertEqual(sum(r['status'].endswith('_activated') for r in results), 1)
                    self.assertEqual(self.db.state['promo'][8], 1)
                    self.assertEqual(self.db.state['promo'][12], 1)

    def test_max_uses_is_not_overridden_by_max_activations(self):
        self.db.state['promo'][7:9] = [1, 1]
        self.db.state['promo'][11] = 100
        self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'limit_reached')

    def test_inactive_and_expired(self):
        self.db.state['promo'][10] = False
        self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'not_found')
        self.db.state['promo'][10] = True
        self.db.state['promo'][9] = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'expired')
        self.assertEqual(self.db.state['balances'][20], 0)

    def test_discount_cannot_be_reactivated_after_consumption(self):
        self.db.state['promo'][3] = Decimal(20)
        self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'discount_activated')
        self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'discount_already_active')
        self.db.state['discounts'].clear()
        self.db.state['usage'].add((20, 1))
        self.assertEqual(promos.activate_promo(20, 'CODE')['status'], 'already_used')

    def test_failed_credit_rolls_back_activation(self):
        self.db.fail_credit = True
        with self.assertRaises(RuntimeError):
            promos.activate_promo(20, 'CODE')
        self.assertEqual(self.db.state['promo'][8], 0)
        self.assertFalse(self.db.state['usage'])


class ReferralSecurityTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()

    def register(self, uid=20):
        with self.db.connection() as conn:
            result = referrals.handle_referral_registration(conn.cursor(), uid, 'REF10', conn)
            conn.commit()
            return result

    def test_self_referral(self):
        self.assertFalse(self.register(10))
        self.assertEqual(self.db.state['balances'], {10: 0, 20: 0})

    def test_bonuses_paid_once_and_match_text(self):
        self.assertTrue(self.register())
        self.assertFalse(self.register())
        self.assertEqual(self.db.state['balances'], {10: 100, 20: 50})
        self.assertEqual(self.db.state['earnings'], 100)
        self.assertEqual(self.db.state['count'], 1)
        self.assertTrue(any("'active', TRUE, 100.00" in sql for sql, _ in self.db.queries))

    def test_concurrent_registration_cannot_pay_twice(self):
        barrier = threading.Barrier(2)

        def register(_):
            barrier.wait(timeout=5)
            return self.register()

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(register, range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.db.state['balances'], {10: 100, 20: 50})

    def test_failure_rolls_back_both_bonuses(self):
        self.db.fail_credit = True
        with self.assertRaises(RuntimeError):
            self.register()
        self.assertEqual(self.db.state['balances'], {10: 0, 20: 0})
        self.assertFalse(self.db.state['referrals'])


class OnboardingSecurityTests(unittest.TestCase):
    def run_start(self, existing=False, fail=False, appeared=False):
        bot = FakeBot()
        conn = mock.Mock()
        cursor = conn.cursor.return_value
        cursor.fetchone.side_effect = ([(1, 'test_user')] if existing else
                                      [None, (1, 'test_user')] if appeared else [None, None, (21,)])

        def register(*args):
            conn.commit.assert_not_called()
            if fail:
                raise RuntimeError('fake referral failure')
            return True

        referral = mock.Mock(side_effect=register)
        with mock.patch.multiple(onboarding, bot=bot, get_pg_connection=lambda: conn,
                                 return_pg_connection=lambda conn: None,
                                 handle_referral_registration=referral,
                                 notify_referrer_about_visit=None):
            onboarding._start_impl(make_message('/start REF10', user_id=20))
        return conn, referral

    def test_existing_user_cannot_register_referral(self):
        conn, referral = self.run_start(existing=True)
        referral.assert_not_called()
        conn.commit.assert_called_once()
        self.assertFalse(any("pg_advisory" in c.args[0] for c in conn.cursor.return_value.execute.call_args_list))

    def test_user_created_while_waiting_for_lock_is_not_inserted_again(self):
        conn, referral = self.run_start(appeared=True)
        referral.assert_not_called()
        conn.commit.assert_called_once()
        calls = conn.cursor.return_value.execute.call_args_list
        self.assertTrue(any('pg_advisory_xact_lock' in c.args[0] for c in calls))
        self.assertFalse(any('INSERT INTO label' in c.args[0] or 'MAX(id)' in c.args[0] for c in calls))

    def test_registration_and_bonus_share_transaction(self):
        conn, referral = self.run_start()
        referral.assert_called_once()
        conn.commit.assert_called_once()
        calls = conn.cursor.return_value.execute.call_args_list
        lock = next(i for i, c in enumerate(calls) if "pg_advisory_xact_lock" in c.args[0])
        allocation = next(i for i, c in enumerate(calls) if "MAX(id)" in c.args[0])
        self.assertLess(lock, allocation)
        self.assertFalse(any("LOCK TABLE" in c.args[0] for c in calls))

    def test_bonus_failure_rolls_back_registration(self):
        with self.assertLogs(onboarding.logger, level='ERROR'):
            conn, referral = self.run_start(fail=True)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()


class ReviewAndAdminSecurityTests(unittest.TestCase):
    def test_review_spam_is_serialized(self):
        db = FakeDb()
        with mock.patch.object(reviews, 'connection', db.connection):
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(lambda _: reviews.create_review(20, 'design', 5, 'Текст'), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(db.state['reviews'], [20])

    def test_invalid_ratings_rejected_before_db_and_in_callback(self):
        bot = FakeBot()
        review_handlers.register_reviews_handlers(bot)
        with mock.patch.object(reviews, 'connection') as connection:
            for rating in (-1, 0, 6, 100, True):
                with self.assertRaises(ValueError):
                    reviews.create_review(20, 'design', rating, 'Текст')
            connection.assert_not_called()
        for rating in ('-1', '0', '6', 'oops'):
            dispatch(bot, 'rating_' + rating)
        self.assertFalse(bot.next_step_handlers)

    def test_all_review_admin_callbacks_deny_non_admins(self):
        bot = FakeBot()
        review_handlers.register_reviews_handlers(bot)
        with mock.patch.object(admin_promos, '_is_admin', return_value=False):
            for data in ('admin_reviews', 'admin_reviews_pending', 'admin_reviews_all',
                         'admin_review_detail_1', 'review_approve_1', 'review_reject_1',
                         'approve_review_1', 'reject_review_1'):
                dispatch(bot, data)
        self.assertEqual(len(bot.callback_answers), 8)
        self.assertFalse(bot.edited_messages)

    def test_all_promo_admin_callbacks_deny_non_admins(self):
        bot = FakeBot()
        admin_promos.register_admin_promo_handlers(bot)
        callbacks = ('finance_promo', 'promo_create', 'promo_create_balance',
                     'promo_create_discount', 'promo_create_limited', 'promo_create_timed',
                     'promo_create_unlimited', 'promo_create_discount_limited',
                     'promo_create_discount_timed', 'promo_create_discount_unlimited',
                     'promo_stats', 'promo_delete', 'delete_promo_CODE')
        with mock.patch.object(admin_promos, '_is_admin', return_value=False):
            for data in callbacks:
                dispatch(bot, data)
        self.assertEqual(len(bot.callback_answers), len(callbacks))
        self.assertFalse(bot.edited_messages)
        self.assertFalse(bot.next_step_handlers)

    def test_promo_steps_recheck_admin_role(self):
        bot = FakeBot()
        admin_promos.register_admin_promo_handlers(bot)
        with mock.patch.object(admin_promos, '_is_admin', return_value=True):
            for kind in ('limited', 'timed', 'unlimited', 'discount_limited', 'discount_timed', 'discount_unlimited'):
                dispatch(bot, 'promo_create_' + kind)
        with mock.patch.object(admin_promos, '_is_admin', return_value=False), mock.patch.object(admin_promos, 'create_promo') as create:
            for _, handler, _, _ in bot.next_step_handlers:
                handler(make_message('CODE 100 10', user_id=20))
            create.assert_not_called()


class TopupSecurityTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.bot = FakeBot()
        self.ctx = dict(get_pg_connection=lambda: FakeConn(self.db),
                        return_pg_connection=lambda conn: None, crypto_bot_token='fake')
        self.invoice = dict(invoice_id=123, status='paid', currency_type='fiat', fiat='RUB', amount='100')
        self.response = mock.Mock(status_code=200)
        self.response.json.return_value = {'ok': True, 'result': {'items': [self.invoice]}}

    def check(self, user=20):
        topups._check_crypto_payment(self.bot, make_call('check_crypto_123', user_id=user), self.ctx)

    def test_amount_limits_at_all_entry_points(self):
        provider = mock.Mock()
        topups.register_topup_handlers(self.bot, payment_handlers={'crypto': provider})
        for value in ('-100', '49', '100001', '1.50', 'NaN', '1e3', 'abc500'):
            self.assertIsNone(topups._parse_amount(value))
            for prefix in ('topup_', 'topup_pay_', 'crypto_pay_'):
                dispatch(self.bot, prefix + value)
        provider.assert_not_called()
        self.assertFalse(self.bot.edited_messages)
        for value in ('50', '100000', '1 500₽'):
            self.assertIsNotNone(topups._parse_amount(value))

    def test_foreign_checks_do_not_call_provider(self):
        with mock.patch.object(topups.requests, 'post') as post:
            self.check(10)
            post.assert_not_called()
        topups.register_topup_handlers(self.bot, payment_context=self.ctx)
        for prefix in ('check_stars_', 'check_ton_', 'pay_stars_'):
            dispatch(self.bot, prefix + '123', user=10)
        self.assertFalse(self.bot.edited_messages)

    def test_crypto_credit_once_under_concurrent_checks(self):
        with mock.patch.object(topups.requests, 'post', return_value=self.response):
            with ThreadPoolExecutor(2) as pool:
                list(pool.map(lambda _: self.check(), range(2)))
        self.assertEqual(self.db.state['balances'][20], 100)
        self.assertEqual(self.db.state['order'][2], 'completed')

    def test_legacy_usdt_credit_once_and_exact_amount(self):
        self.invoice = dict(invoice_id=123, status='paid', asset='USDT', amount='1')
        self.response.json.return_value['result']['items'] = [self.invoice]
        with mock.patch.object(topups.requests, 'post', return_value=self.response):
            for values in ({'amount': '100'}, {'asset': 'BTC'}, {'amount': 'NaN'}):
                with mock.patch.dict(self.invoice, values):
                    self.check()
                self.assertEqual(self.db.state['balances'][20], 0)
            self.check()
            self.check()
        self.assertEqual(self.db.state['balances'][20], 100)

    def test_credit_failure_can_be_retried(self):
        with mock.patch.object(topups.requests, 'post', return_value=self.response):
            self.db.fail_credit = True
            self.check()
            self.assertEqual(self.db.state['order'][2], 'pending')
            self.db.fail_credit = False
            self.check()
        self.assertEqual(self.db.state['balances'][20], 100)

    def test_wrong_invoice_amount_currency_or_id_cannot_credit(self):
        for field, value in (('amount', '1'), ('amount', 'NaN'), ('fiat', 'USD'), ('invoice_id', 999)):
            with self.subTest(field=field, value=value):
                original = self.invoice[field]
                self.invoice[field] = value
                with mock.patch.object(topups.requests, 'post', return_value=self.response):
                    self.check()
                self.invoice[field] = original
                self.assertEqual(self.db.state['balances'][20], 0)
                self.assertEqual(self.db.state['order'][2], 'pending')


if __name__ == '__main__':
    unittest.main()

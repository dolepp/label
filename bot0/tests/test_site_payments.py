"""Site money flows: no database or network; transactional fakes."""
from __future__ import annotations

import copy
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SITE_DIR = Path(__file__).resolve().parents[2] / 'site'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))
import api


class FakeDb:
    def __init__(self):
        self.balance = Decimal('5000')
        self.artist = 0
        self.order = [1, Decimal('100'), 'pending']
        self.owner = 42
        self.system = 'yookassa'
        self.service = 'topup'
        self.discount = False
        self.usage = set()
        self.uses = 0
        self.limit = 2
        self.activation_limit = None
        self.promo_amount = Decimal('100')
        self.promo_discount = 0
        self.active_discount_percent = 50
        self.queries = []
        self.fail_credit = False
        self.fail_release = False
        self.lock = threading.RLock()


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.snapshot = None

    def cursor(self):
        return FakeCursor(self)

    def begin(self):
        if self.snapshot is None:
            self.db.lock.acquire()
            self.snapshot = {k: copy.deepcopy(getattr(self.db, k)) for k in
                             ('balance', 'order', 'discount', 'usage', 'uses')}

    def commit(self):
        if self.snapshot is not None:
            self.snapshot = None
            self.db.lock.release()

    def rollback(self):
        if self.snapshot is not None:
            for key, value in self.snapshot.items():
                setattr(self.db, key, value)
            self.commit()

    def close(self):
        self.rollback()


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.db = conn.db
        self.result = []

    def execute(self, sql, params=()):
        self.conn.begin()
        sql = ' '.join(sql.split())
        db = self.db
        db.queries.append((sql, params))
        self.result = []
        if sql.startswith('SELECT id, amount, status FROM orders'):
            assert 'FOR UPDATE' in sql and "service_type = 'topup'" in sql
            assert '(payment_system = %s OR payment_system IS NULL)' in sql
            if (params[0] == 'pay1' and params[2] == db.owner
                    and (params[1] == db.system or db.system is None) and db.service == 'topup'):
                self.result = [tuple(db.order)]
        elif sql.startswith('UPDATE orders SET status'):
            assert "status = 'pending' RETURNING" in sql
            if db.order[2] == 'pending':
                db.order[2] = params[0]
                self.result = [(1,)]
        elif sql.startswith('UPDATE label'):
            if ' - %s' in sql:
                assert 'AND COALESCE(balance, 0) >= %s' in sql
                if db.balance >= params[2]:
                    db.balance -= params[0]
                    self.result = [(db.balance,)]
            else:
                if db.fail_credit:
                    raise RuntimeError('credit failed')
                if len(params) < 3 or db.balance + params[0] >= 0:
                    db.balance += params[0]
                    self.result = [(db.balance,)]
        elif 'SELECT COALESCE(artist, 0)' in sql:
            self.result = [(db.artist,)]
        elif 'SELECT COALESCE(balance, 0)' in sql or sql.startswith('SELECT balance'):
            self.result = [(db.balance,)]
        elif 'FROM user_discount_promos udp' in sql:
            assert 'FOR UPDATE OF udp' in sql
            self.result = [(7, 'SALE', db.active_discount_percent, None)] if db.discount else []
        elif sql.startswith('DELETE FROM user_discount_promos'):
            db.discount = False
        elif sql.startswith('SELECT id FROM label'):
            self.result = [(1,)]
        elif 'FROM promo_codes' in sql:
            assert 'FOR UPDATE' in sql
            self.result = [(7, 'SALE', db.promo_amount, db.promo_discount, False, None,
                            None, db.limit, db.uses, None, True, db.activation_limit, db.uses)]
        elif 'SELECT 1 FROM promo_code_usage' in sql:
            self.result = [(1,)] if params[0] in db.usage else []
        elif 'SELECT 1 FROM user_discount_promos' in sql:
            self.result = [(1,)] if db.discount else []
        elif sql.startswith('INSERT INTO promo_code_usage'):
            assert params[0] not in db.usage
            db.usage.add(params[0])
        elif sql.startswith('INSERT INTO user_discount_promos'):
            db.discount = True
        elif sql.startswith('UPDATE promo_codes SET current_'):
            db.uses = params[0]
        elif sql.startswith('INSERT INTO releases'):
            if db.fail_release:
                raise RuntimeError('release failed')
            self.result = [(10,)]
        elif sql.startswith('INSERT INTO orders'):
            self.result = [(1,)]
        elif sql.startswith('SELECT EXISTS'):
            self.result = [(True,)]
        elif sql.startswith('SELECT name, tg'):
            self.result = [('Test', 'test', db.artist)]
        elif sql.startswith('UPDATE promo_codes SET is_active'):
            pass
        else:
            raise AssertionError('Unexpected SQL: ' + sql)

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result

    def close(self):
        pass


class SitePaymentTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        for name, value in {
            'get_pg_connection': lambda: FakeConn(self.db),
            'ensure_promo_tables': lambda c: None,
            'ensure_orders_table': lambda c: None,
            'ensure_release_extra_columns': lambda c: None,
            'get_table_columns': lambda c, t: {'user_id', 'service_type', 'amount', 'status',
                                               'payment_id', 'payment_system', 'created_date'},
            'send_admin_notification': lambda *a: None,
            'YOOKASSA_AVAILABLE': True,
        }.items():
            patcher = mock.patch.object(api, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.payment = SimpleNamespace(id='pay1', status='succeeded',
                                       amount=SimpleNamespace(value='100.00', currency='RUB'),
                                       confirmation=SimpleNamespace(confirmation_url='https://pay.test'))
        self.provider = mock.Mock()
        self.provider.find_one.return_value = self.payment
        self.provider.create.return_value = self.payment
        patcher = mock.patch.object(api, 'Payment', self.provider, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.http = mock.Mock()
        self.http.json.return_value = {'ok': True, 'result': {'invoice_id': 'pay1', 'pay_url': 'https://pay.test',
            'items': [{'invoice_id': 'pay1', 'status': 'paid', 'asset': 'USDT', 'amount': '1'}]}}
        self.http.status_code = 200
        for method in ('get', 'post'):
            patcher = mock.patch.object(api.requests, method, return_value=self.http)
            patcher.start()
            self.addCleanup(patcher.stop)
        if hasattr(api.limiter, 'enabled'):
            patcher = mock.patch.object(api.limiter, 'enabled', False)
            patcher.start()
            self.addCleanup(patcher.stop)

    def client(self, user=42):
        client = api.app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = user
        return client

    def status(self, user=42):
        return self.client(user).get('/api/payments/' + self.db.system + '/status/pay1?amount=999999')

    def test_parallel_and_repeated_confirmation_credits_once(self):
        for system in ('yookassa', 'crypto'):
            with self.subTest(system=system):
                self.db.system = system
                self.db.order[2] = 'pending'
                before = self.db.balance
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(lambda _: self.status().status_code, range(2)))
                self.assertEqual(results, [200, 200])
                self.assertEqual(self.status().status_code, 200)
                self.assertEqual(self.db.balance, before + 100)

    def test_foreign_order_and_wrong_system_do_not_call_provider(self):
        self.assertEqual(self.status(43).status_code, 404)
        self.assertEqual(self.client().get('/api/payments/crypto/status/pay1').status_code, 404)
        self.provider.find_one.assert_not_called()
        self.assertEqual(self.db.balance, 5000)

    def test_credit_failure_rolls_back_status_and_retry_works(self):
        self.db.fail_credit = True
        self.assertEqual(self.status().status_code, 500)
        self.assertEqual(self.db.order[2], 'pending')
        self.db.fail_credit = False
        self.assertEqual(self.status().status_code, 200)
        self.assertEqual(self.db.balance, 5100)

    def test_provider_amount_currency_and_invoice_must_match(self):
        for field, value in [('value', '1'), ('currency', 'USD')]:
            with mock.patch.object(self.payment.amount, field, value):
                self.assertEqual(self.status().status_code, 500)
        self.db.system = 'crypto'
        invoice = self.http.json.return_value['result']['items'][0]
        for field, value in [('amount', '0.01'), ('asset', 'BTC'), ('invoice_id', 'other')]:
            with mock.patch.dict(invoice, {field: value}):
                self.assertEqual(self.status().status_code, 500)
        self.assertEqual(self.db.balance, 5000)

    def test_non_topup_and_terminal_orders_cannot_credit(self):
        self.db.service = 'cover'
        self.assertEqual(self.status().status_code, 404)
        self.db.service = 'topup'
        for status in ('cancelled', 'failed', 'completed'):
            self.db.order[2] = status
            self.assertEqual(self.status().status_code, 200)
        self.assertEqual(self.db.balance, 5000)

    def test_create_rejects_invalid_amounts_and_forces_topup(self):
        for system in ('yookassa', 'crypto'):
            path = '/api/payments/' + system + '/create'
            for amount in (-100, 0, 49, 100001, 'NaN', 'Infinity', 'abc', '50.001'):
                self.assertEqual(self.client().post(path, json={'user_id': 42, 'amount': amount}).status_code, 400)
            response = self.client().post(path, json={'user_id': 42, 'amount': '100.00', 'service_type': 'cover'})
            self.assertEqual(response.status_code, 200)
            inserts = [(sql, params) for sql, params in self.db.queries if sql.startswith('INSERT INTO orders')]
            self.assertEqual(inserts[-1][1][1], 'topup')
            self.assertIn('payment_system', inserts[-1][0])
            self.assertEqual(inserts[-1][1][5], system)
            if system == 'crypto':
                payload = api.requests.post.call_args.kwargs['json']
                self.assertEqual(payload['currency_type'], 'fiat')
                self.assertEqual(payload['fiat'], 'RUB')
                self.assertEqual(Decimal(payload['amount']), 100)
                self.assertNotIn('asset', payload)

    def release(self, route='/api/releases/create', **extra):
        payload = dict(user_id=42, releaseType='EP', releaseName='Test', artistName='Test',
                       releaseDate='2027-01-01', genre='Pop', performerName='Test', musicAuthor='Test',
                       coverFileId='cover', audioFileId='audio', contractFileId='contract',
                       amount=-10000, price=0, isArtist=True, tracks=[{'track_name': 'Track'}])
        payload.update(extra)
        if route == '/api/distribution/create':
            payload.pop('tracks')
            return self.client().post(route, data=payload)
        return self.client().post(route, json=payload)

    def test_all_distribution_routes_compute_price_and_charge(self):
        for route in ('/api/releases/create', '/api/albums/create', '/api/distribution/create'):
            self.db.balance = Decimal('5000')
            response = self.release(route)
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(self.db.balance, 2601)

    def test_admin_missing_user_message(self):
        conn = FakeConn(self.db)
        with mock.patch.object(api, 'admin_request_context', return_value=(conn, conn.cursor(), None)), \
                mock.patch.object(api, 'load_user_by_telegram_id', return_value=None):
            with api.app.test_request_context():
                response, status = api.admin_user_detail(999)
        self.assertEqual(status, 404)
        self.assertEqual(response.get_json()['error'], 'Пользователь не найден')

    def test_orders_endpoint_is_gone_without_charge(self):
        with mock.patch.object(api, 'get_pg_connection') as connect:
            response = self.release('/api/orders')
        self.assertEqual(response.status_code, 410)
        self.assertIn('создания заказа', response.get_json()['error'])
        connect.assert_not_called()
        self.assertEqual(self.db.balance, 5000)

    def test_legacy_null_system_orders_credit_once(self):
        self.db.system = None
        for system in ('yookassa', 'crypto'):
            self.db.order[2] = 'pending'
            before = self.db.balance
            path = '/api/payments/' + system + '/status/pay1'
            self.assertEqual(self.client(43).get(path).status_code, 404)
            for _ in range(2):
                self.assertEqual(self.client().get(path).status_code, 200)
            self.assertEqual(self.db.balance, before + 100)

    def test_crypto_fiat_rub_exact_amount(self):
        self.db.system = 'crypto'
        invoice = self.http.json.return_value['result']['items'][0]
        invoice.update(currency_type='fiat', fiat='RUB', amount='100')
        for values in ({'fiat': 'USD'}, {'amount': '1'}, {'amount': 'NaN'}):
            with mock.patch.dict(invoice, values):
                self.assertEqual(self.status().status_code, 500)
        for _ in range(2):
            self.assertEqual(self.status().status_code, 200)
        self.assertEqual(self.db.balance, 5100)

    def test_db_artist_only_and_insufficient_balance(self):
        self.db.balance = Decimal('0')
        self.assertEqual(self.release().status_code, 402)
        self.db.artist = 1
        self.assertEqual(self.release().status_code, 200)
        self.assertEqual(self.db.balance, 0)

    def test_parallel_releases_cannot_overdraw_or_reuse_discount(self):
        self.db.balance = Decimal('3000')
        self.db.discount = True
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.release().status_code, range(2)))
        self.assertEqual(sorted(results), [200, 402])
        self.assertEqual(self.db.balance, Decimal('1800.50'))
        self.assertFalse(self.db.discount)

    def test_failed_release_restores_debit_and_discount(self):
        self.db.discount = True
        self.db.fail_release = True
        self.assertEqual(self.release().status_code, 500)
        self.assertEqual(self.db.balance, 5000)
        self.assertTrue(self.db.discount)

    def activate(self, user=42):
        return self.client(user).post('/api/promo/activate', json={'user_id': user, 'code': 'SALE'})

    def test_parallel_balance_promo_once_and_global_limit(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.activate().status_code, range(2)))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(self.db.balance, 5100)
        self.assertEqual(self.db.uses, 1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda user: self.activate(user).status_code, (43, 44)))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(self.db.balance, 5200)

    def test_full_discount_is_free_and_consumed_once_on_all_routes(self):
        for route in ('/api/releases/create', '/api/albums/create', '/api/distribution/create'):
            with self.subTest(route=route):
                self.db = FakeDb()
                self.db.balance = Decimal('0')
                self.db.promo_amount = 0
                self.db.promo_discount = 100
                self.db.active_discount_percent = 100
                self.assertEqual(self.activate().status_code, 200)
                response = self.release(route)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(self.db.balance, 0)
                self.assertFalse(self.db.discount)
                self.assertEqual(self.db.uses, 1)
                self.assertEqual(self.db.usage, {42})
                self.assertEqual(self.release(route).status_code, 402)
                self.assertEqual(self.activate().status_code, 409)
                self.assertEqual(self.db.uses, 1)

    def test_invalid_discount_or_negative_amount_is_rejected(self):
        for amount, discount in ((0, -1), (0, 101), (-1, 100), (0, 0)):
            with self.subTest(amount=amount, discount=discount):
                self.db.promo_amount = amount
                self.db.promo_discount = discount
                response = self.activate()
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertFalse(self.db.discount)
                self.assertEqual(self.db.usage, set())
                self.assertEqual(self.db.uses, 0)
                self.assertEqual(self.db.balance, 5000)

    def test_discount_cannot_be_reactivated_after_consumption(self):
        self.db.promo_amount = 0
        self.db.promo_discount = 50
        self.assertEqual(self.activate().status_code, 200)
        self.assertEqual(self.release().status_code, 200)
        self.assertEqual(self.activate().status_code, 409)

    def test_query_user_id_cannot_hide_foreign_body(self):
        response = self.client().post('/api/payments/crypto/create?user_id=42',
                                      json={'user_id': 43, 'amount': 100})
        self.assertEqual(response.status_code, 403)

    def test_balance_change_requires_db_admin(self):
        with mock.patch.object(api, 'is_admin_user', return_value=False):
            response = self.client().post('/api/user/balance', json={'user_id': 42, 'delta': 9999})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.db.balance, 5000)

    def test_balance_debit_is_atomic_and_rejects_nonfinite(self):
        with mock.patch.object(api, 'is_admin_user', return_value=True):
            for delta in (-6000, 'NaN', 'Infinity'):
                response = self.client().post('/api/user/balance', json={'user_id': 42, 'delta': delta})
                self.assertNotEqual(response.status_code, 200)
                self.assertEqual(self.db.balance, 5000)
            response = self.client().post('/api/user/balance', json={'user_id': 42, 'delta': -100})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.db.balance, 4900)

    def test_both_promo_limits_are_enforced(self):
        self.db.limit = 1
        self.db.activation_limit = 10
        self.assertEqual(self.activate().status_code, 200)
        self.assertEqual(self.activate(43).status_code, 409)
        self.assertEqual(self.db.balance, 5100)

    def test_promo_credit_failure_does_not_consume_code(self):
        self.db.fail_credit = True
        self.assertEqual(self.activate().status_code, 500)
        self.assertEqual(self.db.uses, 0)
        self.assertEqual(self.db.usage, set())
        self.db.fail_credit = False
        self.assertEqual(self.activate().status_code, 200)

    def test_pending_provider_does_not_credit(self):
        self.payment.status = 'pending'
        self.assertEqual(self.status().get_json()['status'], 'pending')
        self.assertEqual(self.db.balance, 5000)
        self.assertEqual(self.db.order[2], 'pending')

    def test_design_price_and_service_are_server_controlled(self):
        response = self.client().post('/api/design/order', json={'user_id': 42, 'service': 'covers', 'amount': -1})
        self.assertEqual(response.status_code, 200)
        insert = next(params for sql, params in self.db.queries if sql.startswith('INSERT INTO orders'))
        self.assertEqual(insert[1:4], ('cover', 2000, 'pending'))


if __name__ == '__main__':
    unittest.main()

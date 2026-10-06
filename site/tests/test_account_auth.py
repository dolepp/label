"""Integration tests in an isolated PostgreSQL schema; no live users or emails.

Run with TEST_AUTH_POSTGRES=1 and POSTGRES_* environment variables.
"""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import patch, Mock
from urllib.parse import parse_qs, urlparse

import psycopg2
from psycopg2 import sql
from flask import Flask, session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auth_accounts


class NoLimiter:
    def limit(self, _):
        return lambda f: f


@unittest.skipUnless(os.getenv('TEST_AUTH_POSTGRES') == '1', 'Requires test PostgreSQL connection')
class AuthIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = 'auth_test_' + secrets.token_hex(8)
        cls.db_config = dict(dbname=os.getenv('POSTGRES_DB', 'label'), user=os.getenv('POSTGRES_USER', 'postgres'),
                             password=os.getenv('POSTGRES_PASSWORD', ''), host=os.getenv('POSTGRES_HOST', 'localhost'),
                             port=os.getenv('POSTGRES_PORT', '5432'))
        conn = psycopg2.connect(**cls.db_config)
        with conn.cursor() as c:
            c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
        conn.commit()
        conn.close()
        conn = cls.connect()
        with conn.cursor() as c:
            c.execute('''CREATE TABLE label (id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE, login TEXT UNIQUE,
                         name TEXT, email TEXT, artist INTEGER DEFAULT 1, balance NUMERIC DEFAULT 0,
                         tg TEXT, created_date TIMESTAMP DEFAULT NOW())''')
            migration = Path(__file__).resolve().parents[2] / 'migrations/005_multi_provider_auth.sql'
            c.execute(migration.read_text().replace('BEGIN;', '').replace('COMMIT;', ''))
        conn.commit()
        conn.close()
        cls.environment = patch.dict(os.environ, {'SMTP_HOST': 'smtp.example.test', 'SMTP_FROM': 'auth@example.test',
                                                  'GOOGLE_CLIENT_ID': 'google-test', 'GOOGLE_CLIENT_SECRET': 'secret-test',
                                                  'YANDEX_CLIENT_ID': 'yandex-test', 'YANDEX_CLIENT_SECRET': 'secret-test'})
        cls.environment.start()
        cls.app = Flask(__name__)
        cls.app.secret_key = 'integration-secret'
        cls.app.testing = True
        cls.origin = {'Origin': 'https://twaslabel.ru'}

        def load(c, account_id):
            c.execute('SELECT telegram_id FROM label WHERE notification_telegram_id=%s', (account_id,))
            linked = c.fetchone()
            if linked:
                account_id = linked[0]
            c.execute('SELECT telegram_id,notification_telegram_id,telegram_notifications,name FROM label WHERE telegram_id=%s', (account_id,))
            row = c.fetchone()
            return dict(account_id=row[0], telegram_id=row[1] or (row[0] if row[0] > 0 else None),
                        telegram_notifications=row[2], name=row[3]) if row else None

        def establish(user):
            session.clear()
            session['user_id'] = user['account_id']

        @cls.app.before_request
        def protect():
            from flask import request, jsonify
            if request.path.startswith('/api/profile/') and not session.get('user_id'):
                return jsonify(success=False), 401

        auth_accounts.register_account_auth(cls.app, cls.connect, load, establish, lambda: session.get('user_id'), NoLimiter(), 'test_bot')
        cls.load_user = staticmethod(load)
        # Load only the new repository, avoiding bot startup.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bot0'))
        from db.repositories import account_connections
        cls.bot_connections = account_connections
        @contextmanager
        def connection():
            conn = cls.connect()
            try:
                yield conn
            finally:
                conn.close()
        cls.bot_pool = patch.object(account_connections, 'connection', connection)
        cls.bot_pool.start()

    @classmethod
    def connect(cls):
        return psycopg2.connect(**cls.db_config, options=f'-c search_path={cls.schema}')

    @classmethod
    def tearDownClass(cls):
        cls.bot_pool.stop()
        cls.environment.stop()
        conn = psycopg2.connect(**cls.db_config)
        with conn.cursor() as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        conn.commit()
        conn.close()

    def setUp(self):
        self.client = self.app.test_client()
        with self.connect() as conn, conn.cursor() as c:
            c.execute('TRUNCATE label,web_auth_identities,web_email_challenges,web_oauth_states,web_telegram_link_tokens RESTART IDENTITY CASCADE')
        self.delivery = patch.object(auth_accounts, 'send_email_code')
        self.mail = self.delivery.start()
        self.addCleanup(self.delivery.stop)

    def request_code(self, email='artist@example.test', **extra):
        response = self.client.post('/api/auth/email/request', json={'email': email, 'name': 'Artist', **extra}, headers=self.origin)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['challenge_id'], self.mail.call_args.args[1]

    def verify(self, challenge, code):
        return self.client.post('/api/auth/email/verify', json={'challenge_id': challenge, 'code': code}, headers=self.origin)

    def register_email(self):
        response = self.verify(*self.request_code())
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['user']['account_id']

    def oauth(self, provider='google', mode='', info=None):
        start = self.client.get(f'/api/auth/oauth/{provider}/start{mode}')
        self.assertEqual(start.status_code, 302)
        state = parse_qs(urlparse(start.location).query)['state'][0]
        token_response = Mock()
        token_response.json.return_value = {'access_token': 'access-test'}
        user_response = Mock()
        user_response.json.return_value = info or {'sub': 'subject-google', 'name': 'Artist', 'email': 'artist@example.test', 'email_verified': True}
        with patch.object(auth_accounts.requests, 'post', return_value=token_response) as post, patch.object(auth_accounts.requests, 'get', return_value=user_response):
            response = self.client.get(f'/api/auth/oauth/{provider}/callback?code=authorization-test&state={state}')
            self.assertEqual(response.status_code, 302)
            self.assertIn('code_verifier', post.call_args.kwargs['data'])
            self.assertNotIn('access-test', response.location)
        return response, state

    def test_registration_one_time_code_and_existing_email_login(self):
        challenge, code = self.request_code('Artist@Example.Test')
        account_id = self.verify(challenge, code).json['user']['account_id']
        self.assertLess(account_id, 0)
        self.assertEqual(self.verify(challenge, code).status_code, 400)
        with self.connect() as conn, conn.cursor() as c:
            c.execute("UPDATE web_email_challenges SET created_at=NOW()-INTERVAL '2 minutes'")
        self.assertEqual(self.verify(*self.request_code()).json['user']['account_id'], account_id)

    def test_attempt_limit_and_expired_code(self):
        challenge, code = self.request_code()
        wrong = '00000000' if code != '00000000' else '11111111'
        for _ in range(5):
            self.assertEqual(self.verify(challenge, wrong).status_code, 400)
        self.assertEqual(self.verify(challenge, code).status_code, 400)
        with self.connect() as conn, conn.cursor() as c:
            c.execute("UPDATE web_email_challenges SET attempts=0,expires_at=NOW()-INTERVAL '1 minute'")
        self.assertEqual(self.verify(challenge, code).status_code, 400)

    def test_delivery_failure_cannot_authenticate(self):
        self.mail.side_effect = OSError('SMTP unavailable')
        response = self.client.post('/api/auth/email/request', json={'email': 'artist@example.test'}, headers=self.origin)
        self.assertEqual(response.status_code, 503)
        with self.connect() as conn, conn.cursor() as c:
            c.execute('SELECT delivered FROM web_email_challenges')
            self.assertFalse(c.fetchone()[0])
            c.execute('SELECT COUNT(*) FROM label')
            self.assertEqual(c.fetchone()[0], 0)

    def test_origin_and_throttle(self):
        self.assertEqual(self.client.post('/api/auth/email/request', json={'email': 'artist@example.test'}, headers={'Origin': 'https://attacker.test'}).status_code, 403)
        self.request_code()
        self.assertEqual(self.client.post('/api/auth/email/request', json={'email': 'artist@example.test'}, headers=self.origin).status_code, 429)

    def test_google_login_reuse_and_state_replay(self):
        response, state = self.oauth()
        self.assertNotIn('auth_error', response.location)
        with self.client.session_transaction() as s:
            account_id = s['user_id']
        self.assertIn('auth_error', self.client.get(f'/api/auth/oauth/google/callback?code=test&state={state}').location)
        self.oauth()
        with self.client.session_transaction() as s:
            self.assertEqual(s['user_id'], account_id)

    def test_yandex_login(self):
        response, _ = self.oauth('yandex', info={'id': 'yandex-subject', 'display_name': 'Artist', 'default_email': 'artist@yandex.test'})
        self.assertNotIn('auth_error', response.location)

    def test_oauth_wrong_browser_state_no_provider_request(self):
        self.client.get('/api/auth/oauth/google/start')
        with patch.object(auth_accounts.requests, 'post') as post:
            response = self.client.get('/api/auth/oauth/google/callback?code=test&state=wrong')
            self.assertIn('auth_error', response.location)
            post.assert_not_called()

    def test_link_provider_keeps_account_balance(self):
        account_id = self.register_email()
        with self.connect() as conn, conn.cursor() as c:
            c.execute('UPDATE label SET balance=1500 WHERE telegram_id=%s', (account_id,))
        response, _ = self.oauth(mode='?mode=link')
        self.assertNotIn('auth_error', response.location)
        with self.client.session_transaction() as s:
            self.assertEqual(s['user_id'], account_id)
        with self.connect() as conn, conn.cursor() as c:
            c.execute('SELECT balance FROM label WHERE telegram_id=%s', (account_id,))
            self.assertEqual(c.fetchone()[0], 1500)
        self.assertEqual(set(self.client.get('/api/profile/connections').json['providers']), {'email', 'google'})

    def test_contact_email_does_not_grant_existing_account_access(self):
        with self.connect() as conn, conn.cursor() as c:
            c.execute("INSERT INTO label(telegram_id,email,name) VALUES(123,'artist@example.test','Old Artist')")
        account_id = self.register_email()
        self.assertNotEqual(account_id, 123)

    def test_email_link_requires_original_session(self):
        self.oauth()
        challenge, code = self.request_code(mode='link')
        with self.client.session_transaction() as s:
            s.clear()
        self.assertEqual(self.verify(challenge, code).status_code, 403)

    def test_telegram_link_unlink_and_notifications(self):
        account_id = self.register_email()
        response = self.client.post('/api/profile/telegram/link', json={}, headers=self.origin)
        token = parse_qs(urlparse(response.json['url']).query)['start'][0][5:]
        self.assertEqual(self.bot_connections.link_telegram(token, 777, 'artist'), account_id)
        self.assertEqual(self.bot_connections.notification_chat_id(account_id), 777)
        with self.assertRaises(ValueError):
            self.bot_connections.link_telegram(token, 888, 'other')
        data = self.client.get('/api/profile/connections').json
        self.assertEqual(data['telegram_id'], 777)
        self.client.post('/api/profile/telegram/notifications', json={'enabled': False}, headers=self.origin)
        self.assertIsNone(self.bot_connections.notification_chat_id(account_id))
        self.client.post('/api/profile/telegram/unlink', json={}, headers=self.origin)
        self.assertIsNone(self.client.get('/api/profile/connections').json['telegram_id'])
        with self.connect() as conn, conn.cursor() as c:
            self.assertEqual(self.load_user(c, account_id)['account_id'], account_id)

    def test_telegram_collision_does_not_move_other_profile(self):
        self.register_email()
        with self.connect() as conn, conn.cursor() as c:
            c.execute("INSERT INTO label(telegram_id,name) VALUES(777,'Existing Telegram Artist')")
        response = self.client.post('/api/profile/telegram/link', json={}, headers=self.origin)
        token = parse_qs(urlparse(response.json['url']).query)['start'][0][5:]
        with self.assertRaises(ValueError):
            self.bot_connections.link_telegram(token, 777, 'artist')

    def test_protected_routes_and_provider_disabled(self):
        self.assertEqual(self.client.get('/api/profile/connections').status_code, 401)
        with patch.dict(os.environ, {'GOOGLE_CLIENT_SECRET': '', 'SMTP_HOST': ''}):
            options = self.client.get('/api/auth/options').json
            self.assertFalse(options['providers']['google'])
            self.assertFalse(options['email'])
            self.assertEqual(self.client.post('/api/auth/email/request', json={'email': 'artist@example.test'}, headers=self.origin).status_code, 503)


if __name__ == '__main__':
    unittest.main()

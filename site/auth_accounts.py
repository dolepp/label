"""Email OTP, Google/Yandex OAuth and Telegram notification linking.

Identity proofs live separately from editable profile contact fields. Account IDs
remain stable so linking an identity never moves releases, files or balances.
"""
import base64
from contextlib import contextmanager
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode

import requests
from flask import jsonify, redirect, request, session

PROVIDERS = {
    'google': {
        'authorize': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token': 'https://oauth2.googleapis.com/token',
        'userinfo': 'https://openidconnect.googleapis.com/v1/userinfo',
        'scope': 'openid email profile',
    },
    'yandex': {
        'authorize': 'https://oauth.yandex.ru/authorize',
        'token': 'https://oauth.yandex.ru/token',
        'userinfo': 'https://login.yandex.ru/info?format=json',
        'scope': 'login:info login:email',
    },
}
PUBLIC_AUTH_PATHS = {
    '/api/auth/options', '/api/auth/email/request', '/api/auth/email/verify',
    *(f'/api/auth/oauth/{provider}/{action}' for provider in PROVIDERS for action in ('start', 'callback')),
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError('Укажите электронную почту.')
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise ValueError('Укажите корректную электронную почту.')
    return value


def provider_credentials(provider):
    return os.getenv(f'{provider.upper()}_CLIENT_ID', ''), os.getenv(f'{provider.upper()}_CLIENT_SECRET', '')


def email_configured():
    return bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM'))


def send_email_code(email, code):
    message = EmailMessage()
    message['Subject'] = 'Код входа — TWAS Label'
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = email
    message.set_content(f'Ваш код: {code}\n\nКод действует 10 минут и используется один раз.\nЕсли вы не запрашивали вход, проигнорируйте письмо.')
    port = int(os.getenv('SMTP_PORT', '587'))
    mode = os.getenv('SMTP_SECURITY', 'starttls').lower()
    if mode not in {'ssl', 'starttls'}:
        raise ValueError('SMTP_SECURITY must be ssl or starttls')
    smtp_class = smtplib.SMTP_SSL if mode == 'ssl' else smtplib.SMTP
    kwargs = {'timeout': 15}
    if mode == 'ssl':
        kwargs['context'] = ssl.create_default_context()
    with smtp_class(os.environ['SMTP_HOST'], port, **kwargs) as smtp:
        if mode == 'starttls':
            smtp.starttls(context=ssl.create_default_context())
        if os.getenv('SMTP_USER'):
            smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(message)


def register_account_auth(app, get_connection, load_user, establish_session, current_user_id, limiter, bot_username):
    frontend = os.getenv('AUTH_FRONTEND_URL', 'https://twaslabel.ru').rstrip('/')
    api_url = os.getenv('AUTH_API_URL', 'https://api.twaslabel.ru:8443').rstrip('/')
    trusted_origins = {frontend, 'https://twaslabel.ru', 'https://www.twaslabel.ru'}

    @contextmanager
    def database():
        conn = get_connection()
        if conn is None:
            raise ConnectionError('Database unavailable')
        cursor = conn.cursor()
        try:
            yield conn, cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def code_digest(challenge, code):
        return hmac.new(app.secret_key.encode(), f'{challenge}:{code}'.encode(), hashlib.sha256).hexdigest()

    def mutation_origin():
        return request.headers.get('Origin') in trusted_origins

    def link_account(data):
        if data.get('mode') == 'link':
            account_id = current_user_id()
            if not account_id:
                raise ValueError('Сначала войдите в профиль.')
            return account_id
        return None

    def create_account(cursor, name, email):
        cursor.execute("SELECT -nextval('web_account_ids')")
        account_id = cursor.fetchone()[0]
        cursor.execute('''INSERT INTO label (telegram_id, login, name, email, artist, balance, created_date)
                          VALUES (%s, %s, %s, %s, 1, 0, NOW())''',
                       (account_id, f'web_{-account_id}', name[:255] or 'Артист', email))
        return account_id

    def attach_identity(cursor, provider, subject, account_id):
        cursor.execute('SELECT account_id FROM web_auth_identities WHERE provider=%s AND subject=%s', (provider, subject))
        row = cursor.fetchone()
        if row and row[0] != account_id:
            raise ValueError('Этот способ входа уже связан с другим аккаунтом. Войдите в него; автоматическое объединение недоступно.')
        cursor.execute('SELECT subject FROM web_auth_identities WHERE provider=%s AND account_id=%s', (provider, account_id))
        existing = cursor.fetchone()
        if existing and existing[0] != subject:
            raise ValueError('К профилю уже привязан другой аккаунт этого сервиса.')
        cursor.execute('INSERT INTO web_auth_identities(provider,subject,account_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                       (provider, subject, account_id))

    def auth_result(account_id):
        with database() as (_, cursor):
            user = load_user(cursor, account_id)
        if not user:
            raise ValueError('Пользователь не найден.')
        establish_session(user)
        return jsonify(success=True, user=user)

    def oauth_return(error=None):
        query = '?' + urlencode({'auth_error': error}) if error else ''
        return redirect(frontend + '/' + query + '#profile')

    @app.route('/api/auth/options')
    def auth_options():
        return jsonify(success=True, email=email_configured(),
                       providers={p: all(provider_credentials(p)) for p in PROVIDERS})

    @app.route('/api/auth/email/request', methods=['POST'])
    @limiter.limit('5 per minute; 20 per hour')
    def email_request():
        if not mutation_origin():
            return jsonify(success=False, error='Недопустимый источник запроса.'), 403
        if not email_configured():
            return jsonify(success=False, error='Вход по почте пока не настроен.'), 503
        try:
            data = request.get_json(silent=True) or {}
            email = normalize_email(data.get('email'))
            account_id = link_account(data)
            name = str(data.get('name') or '').strip()[:255]
            challenge = secrets.token_urlsafe(24)
            code = f'{secrets.randbelow(100000000):08d}'
            with database() as (_, cursor):
                # Serialize requests per mailbox across workers, independent of IP.
                cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('email:' + email,))
                cursor.execute("DELETE FROM web_email_challenges WHERE expires_at < NOW() - INTERVAL '1 day'")
                cursor.execute("SELECT COUNT(*) FROM web_email_challenges WHERE email=%s AND created_at>NOW()-INTERVAL '1 hour'", (email,))
                if cursor.fetchone()[0] >= 5:
                    return jsonify(success=False, error='Слишком много писем. Попробуйте через час.'), 429
                cursor.execute("SELECT 1 FROM web_email_challenges WHERE email=%s AND created_at>NOW()-INTERVAL '60 seconds'", (email,))
                if cursor.fetchone():
                    return jsonify(success=False, error='Повторный код можно запросить через минуту.'), 429
                cursor.execute('''INSERT INTO web_email_challenges(id,email,code_hash,display_name,link_account_id,expires_at)
                                  VALUES(%s,%s,%s,%s,%s,NOW()+INTERVAL '10 minutes')''',
                               (challenge, email, code_digest(challenge, code), name, account_id))
            try:
                send_email_code(email, code)
            except Exception:
                app.logger.warning('Email authentication delivery failed')
                return jsonify(success=False, error='Не удалось отправить письмо. Попробуйте позже.'), 503
            with database() as (_, cursor):
                cursor.execute('UPDATE web_email_challenges SET delivered=TRUE WHERE id=%s', (challenge,))
            return jsonify(success=True, challenge_id=challenge, message='Код отправлен на вашу почту. Он действует 10 минут.')
        except ValueError as exc:
            return jsonify(success=False, error=str(exc)), 400
        except Exception:
            app.logger.exception('Email challenge failed')
            return jsonify(success=False, error='Не удалось запросить код.'), 500

    @app.route('/api/auth/email/verify', methods=['POST'])
    @limiter.limit('10 per minute')
    def email_verify():
        if not mutation_origin():
            return jsonify(success=False, error='Недопустимый источник запроса.'), 403
        data = request.get_json(silent=True) or {}
        challenge, code = str(data.get('challenge_id') or ''), str(data.get('code') or '').strip()
        if len(challenge) > 100 or not re.fullmatch(r'\d{8}', code):
            return jsonify(success=False, error='Введите восьмизначный код из письма.'), 400
        try:
            with database() as (_, cursor):
                cursor.execute('''SELECT email, code_hash, display_name, link_account_id, attempts
                                  FROM web_email_challenges WHERE id=%s AND NOT used AND delivered
                                  AND expires_at>NOW() FOR UPDATE''', (challenge,))
                row = cursor.fetchone()
                if not row or row[4] >= 5:
                    return jsonify(success=False, error='Код истёк или использован. Запросите новый.'), 400
                email, expected, name, account_id, _ = row
                cursor.execute('UPDATE web_email_challenges SET attempts=attempts+1 WHERE id=%s', (challenge,))
                if not hmac.compare_digest(expected, code_digest(challenge, code)):
                    return jsonify(success=False, error='Неверный код.'), 400
                if account_id is not None and current_user_id() != account_id:
                    return jsonify(success=False, error='Войдите в профиль, из которого запросили привязку.'), 403
                cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('identity:email:' + email,))
                cursor.execute("SELECT account_id FROM web_auth_identities WHERE provider='email' AND subject=%s", (email,))
                existing = cursor.fetchone()
                if account_id is None:
                    account_id = existing[0] if existing else create_account(cursor, name or email.split('@')[0], email)
                attach_identity(cursor, 'email', email, account_id)
                cursor.execute('UPDATE web_email_challenges SET used=TRUE WHERE id=%s', (challenge,))
            return auth_result(account_id)
        except ValueError as exc:
            return jsonify(success=False, error=str(exc)), 409
        except Exception:
            app.logger.exception('Email verification failed')
            return jsonify(success=False, error='Не удалось подтвердить код.'), 500

    @app.route('/api/auth/oauth/<provider>/start')
    @limiter.limit('15 per minute')
    def oauth_start(provider):
        if provider not in PROVIDERS:
            return jsonify(success=False, error='Неизвестный сервис.'), 404
        client_id, client_secret = provider_credentials(provider)
        if not client_id or not client_secret:
            return oauth_return('Вход через этот сервис пока не настроен.')
        try:
            account_id = link_account(request.args)
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
            with database() as (_, cursor):
                cursor.execute('DELETE FROM web_oauth_states WHERE expires_at<NOW()')
                cursor.execute('''INSERT INTO web_oauth_states(state_hash,provider,verifier,link_account_id,expires_at)
                                  VALUES(%s,%s,%s,%s,NOW()+INTERVAL '10 minutes')''',
                               (digest(state), provider, verifier, account_id))
            session['oauth_state'] = state
            params = {'client_id': client_id, 'response_type': 'code', 'scope': PROVIDERS[provider]['scope'],
                      'redirect_uri': api_url + f'/api/auth/oauth/{provider}/callback', 'state': state,
                      'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
                      'code_challenge_method': 'S256'}
            return redirect(PROVIDERS[provider]['authorize'] + '?' + urlencode(params))
        except ValueError as exc:
            return oauth_return(str(exc))
        except Exception:
            app.logger.exception('OAuth start failed')
            return oauth_return('Не удалось начать вход.')

    @app.route('/api/auth/oauth/<provider>/callback')
    @limiter.limit('20 per minute')
    def oauth_callback(provider):
        state = request.args.get('state', '')
        expected = session.pop('oauth_state', None)
        if provider not in PROVIDERS or not expected or not hmac.compare_digest(expected, state):
            return oauth_return('Запрос входа устарел. Начните вход заново.')
        try:
            with database() as (_, cursor):
                cursor.execute('''UPDATE web_oauth_states SET used=TRUE WHERE state_hash=%s AND provider=%s
                                  AND NOT used AND expires_at>NOW() RETURNING verifier,link_account_id''',
                               (digest(state), provider))
                row = cursor.fetchone()
            if not row:
                return oauth_return('Запрос входа истёк или использован.')
            verifier, account_id = row
            if account_id is not None and current_user_id() != account_id:
                return oauth_return('Сессия профиля изменилась. Повторите привязку.')
            if request.args.get('error') or not request.args.get('code'):
                return oauth_return('Вы отменили вход через сервис.')
            client_id, client_secret = provider_credentials(provider)
            response = requests.post(PROVIDERS[provider]['token'], data={
                'grant_type': 'authorization_code', 'code': request.args['code'], 'client_id': client_id,
                'client_secret': client_secret, 'code_verifier': verifier,
                'redirect_uri': api_url + f'/api/auth/oauth/{provider}/callback'}, timeout=15)
            response.raise_for_status()
            token = response.json().get('access_token')
            if not token:
                raise ValueError('Сервис не подтвердил вход.')
            response = requests.get(PROVIDERS[provider]['userinfo'],
                                    headers={'Authorization': ('OAuth ' if provider == 'yandex' else 'Bearer ') + token}, timeout=15)
            response.raise_for_status()
            info = response.json()
            subject = str(info.get('sub' if provider == 'google' else 'id') or '')
            if not subject:
                raise ValueError('Сервис не вернул идентификатор пользователя.')
            email = info.get('email' if provider == 'google' else 'default_email') or ''
            if email:
                email = normalize_email(email)
            name = str(info.get('name') or info.get('display_name') or info.get('real_name') or info.get('login') or 'Артист')
            with database() as (_, cursor):
                cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('identity:' + provider + ':' + subject,))
                cursor.execute('SELECT account_id FROM web_auth_identities WHERE provider=%s AND subject=%s', (provider, subject))
                existing = cursor.fetchone()
                if account_id is None:
                    account_id = existing[0] if existing else create_account(cursor, name, email)
                attach_identity(cursor, provider, subject, account_id)
                user = load_user(cursor, account_id)
            establish_session(user)
            return oauth_return()
        except ValueError as exc:
            return oauth_return(str(exc))
        except Exception:
            # Provider response URLs and tokens must never reach logs or the browser.
            app.logger.warning('OAuth callback failed for provider=%s', provider)
            return oauth_return('Не удалось подтвердить вход. Попробуйте ещё раз.')

    @app.route('/api/profile/connections')
    def connections():
        with database() as (_, cursor):
            user = load_user(cursor, current_user_id())
            cursor.execute('SELECT provider,subject FROM web_auth_identities WHERE account_id=%s', (current_user_id(),))
            identities = dict(cursor.fetchall())
        return jsonify(success=True, providers=list(identities), email=identities.get('email'),
                       telegram_id=user.get('telegram_id'), telegram_notifications=user.get('telegram_notifications', True))

    @app.route('/api/profile/telegram/link', methods=['POST'])
    @limiter.limit('5 per minute')
    def telegram_link():
        if not mutation_origin():
            return jsonify(success=False, error='Недопустимый источник запроса.'), 403
        account_id = current_user_id()
        with database() as (_, cursor):
            user = load_user(cursor, account_id)
            if user.get('telegram_id'):
                return jsonify(success=False, error='Telegram уже привязан.'), 409
            token = secrets.token_urlsafe(32)
            cursor.execute('DELETE FROM web_telegram_link_tokens WHERE expires_at<NOW() OR account_id=%s', (account_id,))
            cursor.execute("INSERT INTO web_telegram_link_tokens(token_hash,account_id,expires_at) VALUES(%s,%s,NOW()+INTERVAL '10 minutes')", (digest(token), account_id))
        return jsonify(success=True, url=f'https://t.me/{bot_username}?start=link_{token}',
                       message='Откройте бота и нажмите «Старт», затем подтвердите привязку здесь. Ссылка действует 10 минут.')

    @app.route('/api/profile/telegram/notifications', methods=['POST'])
    def telegram_notifications():
        if not mutation_origin():
            return jsonify(success=False, error='Недопустимый источник запроса.'), 403
        enabled = (request.get_json(silent=True) or {}).get('enabled')
        if not isinstance(enabled, bool):
            return jsonify(success=False, error='Укажите настройку уведомлений.'), 400
        with database() as (_, cursor):
            cursor.execute('UPDATE label SET telegram_notifications=%s WHERE telegram_id=%s', (enabled, current_user_id()))
        return jsonify(success=True, enabled=enabled)

    @app.route('/api/profile/telegram/unlink', methods=['POST'])
    def telegram_unlink():
        if not mutation_origin():
            return jsonify(success=False, error='Недопустимый источник запроса.'), 403
        if current_user_id() > 0:
            return jsonify(success=False, error='Для аккаунта Telegram можно отключить уведомления; Telegram остаётся способом входа.'), 409
        with database() as (_, cursor):
            cursor.execute('UPDATE label SET notification_telegram_id=NULL, telegram_notifications=FALSE WHERE telegram_id=%s', (current_user_id(),))
            cursor.execute('DELETE FROM web_telegram_link_tokens WHERE account_id=%s', (current_user_id(),))
        return jsonify(success=True)

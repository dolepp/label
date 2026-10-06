"""Map stable website account IDs to opt-in Telegram notification recipients."""
import hashlib
from db.pool import connection


def notification_chat_id(account_id):
    with connection() as conn:
        if conn is None:
            return None
        with conn.cursor() as cursor:
            cursor.execute('SELECT notification_telegram_id,telegram_notifications FROM label WHERE telegram_id=%s', (account_id,))
            row = cursor.fetchone()
            if not row or not row[1]:
                return None
            return row[0] or (int(account_id) if int(account_id) > 0 else None)


def link_telegram(token, telegram_id, username):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connection() as conn:
        if conn is None:
            raise ConnectionError('Database unavailable')
        try:
            with conn.cursor() as cursor:
                # Lock the Telegram identity and target account to prevent concurrent linking.
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', (telegram_id,))
                cursor.execute('''SELECT account_id FROM web_telegram_link_tokens WHERE token_hash=%s
                                  AND NOT used AND expires_at>NOW() FOR UPDATE''', (token_hash,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError('Ссылка истекла или уже использована. Создайте новую в профиле сайта.')
                account_id = row[0]
                cursor.execute('SELECT notification_telegram_id FROM label WHERE telegram_id=%s FOR UPDATE', (account_id,))
                target = cursor.fetchone()
                if not target or target[0]:
                    raise ValueError('У профиля уже есть Telegram. Обновите страницу сайта.')
                cursor.execute('SELECT telegram_id FROM label WHERE telegram_id=%s OR notification_telegram_id=%s', (telegram_id, telegram_id))
                if cursor.fetchone():
                    raise ValueError('Этот Telegram уже зарегистрирован. Войдите на сайт через Telegram и привяжите почту, Google или Яндекс в профиле. Аккаунты автоматически не объединяются.')
                cursor.execute('UPDATE label SET notification_telegram_id=%s, telegram_notifications=TRUE, tg=%s WHERE telegram_id=%s',
                               (telegram_id, username or '', account_id))
                cursor.execute('UPDATE web_telegram_link_tokens SET used=TRUE WHERE account_id=%s', (account_id,))
            conn.commit()
            return account_id
        except Exception:
            conn.rollback()
            raise


def linked_web_account(telegram_id):
    with connection() as conn:
        if conn is None:
            return None
        with conn.cursor() as cursor:
            cursor.execute('SELECT telegram_id FROM label WHERE notification_telegram_id=%s', (telegram_id,))
            row = cursor.fetchone()
            return row[0] if row else None

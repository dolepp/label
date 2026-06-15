#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import shutil
import subprocess
import threading
import hashlib
import hmac as _hmac
import time as _time
import psycopg2
from psycopg2 import Error
from psycopg2.extras import Json
from psycopg2.pool import ThreadedConnectionPool
from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()
except ImportError:
    pass

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ImportError:
    Limiter = None
    get_remote_address = None

# ?????????????????? ??????????????????????
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=[
    "https://twaslabel.ru",
    "https://www.twaslabel.ru",
    "http://163.5.180.182:5000",
    "http://localhost:5000",
], supports_credentials=True, allow_headers=["Content-Type", "Authorization"])

if Limiter is not None:
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )
else:
    logger.warning("Flask-Limiter is not installed; API rate limits are disabled")

    class _NoopLimiter:
        def limit(self, *_args, **_kwargs):
            def decorator(func):
                return func
            return decorator

    limiter = _NoopLimiter()


def is_cacheable_media_request():
    path = request.path or ''
    if path.startswith('/api/releases/') and '/media/cover' in path:
        return True
    if path.startswith('/assets/'):
        return True
    return False


@app.after_request
def add_cache_policy(response):
    """Keep personal JSON uncacheable, but let static cover media use CDN/browser cache."""
    if is_cacheable_media_request():
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
        response.headers.pop('Pragma', None)
        response.headers.pop('Expires', None)
    elif request.path.startswith('/api/') or request.path.startswith('/telegram_auth'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# ???????????????????????? ???????? ???????????? (???? ???? ??????????????????, ?????? ?? ????????)
DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "label")),
    "user": os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres")),
    "password": os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "")),
    "host": os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost")),
    "port": os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432")),
}

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TELEGRAM_STORAGE_CHAT_ID = os.getenv("TELEGRAM_STORAGE_CHAT_ID", os.getenv("ADMIN_CHAT_ID", ""))
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
BOT_USERNAME = os.getenv("BOT_USERNAME", "twaslabel_bot").lstrip("@")
STORAGE_ROOT = Path(os.getenv("MEDIA_STORAGE_ROOT", Path(__file__).resolve().parents[1] / "storage"))
PG_POOL = None
_pool_lock = threading.Lock()
DISTRIBUTION_PRICES = {
    "Single": Decimal("1299.00"),
    "Maxi Single": Decimal("1799.00"),
    "EP": Decimal("2399.00"),
    "ALBUM": Decimal("2899.00"),
}
SCHEMA_READY = set()
TABLE_EXISTS_CACHE = {}
TABLE_COLUMNS_CACHE = {}



class PooledConnection:
    """Thin proxy that returns psycopg2 connections to the pool on close()."""

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._returned = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def close(self):
        if self._returned:
            return
        self._returned = True
        try:
            self._pool.putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

def get_pg_connection():
    """Получение соединения с PostgreSQL. Потокобезопасная инициализация пула."""
    global PG_POOL
    try:
        if PG_POOL is None:
            with _pool_lock:
                if PG_POOL is None:
                    PG_POOL = ThreadedConnectionPool(
                        minconn=2,
                        maxconn=int(os.getenv("PG_MAX_CONN", "10")),
                        dbname=DB_CONFIG["dbname"],
                        user=DB_CONFIG["user"],
                        password=DB_CONFIG["password"],
                        host=DB_CONFIG["host"],
                        port=DB_CONFIG["port"],
                        client_encoding='utf8'
                    )

        return PooledConnection(PG_POOL, PG_POOL.getconn())
    except Error as e:
        logger.error(f"Ошибка подключения к PostgreSQL: {e}")
        return None


def get_table_columns(cursor, table_name):
    cached = TABLE_COLUMNS_CACHE.get(table_name)
    if cached is not None:
        return cached
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
        """,
        (table_name,),
    )
    columns = {row[0] for row in cursor.fetchall()}
    TABLE_COLUMNS_CACHE[table_name] = columns
    return columns


def optional_column(column_name, available_columns, default_sql="NULL"):
    if column_name in available_columns:
        return column_name
    return f"{default_sql} AS {column_name}"


def load_user_by_telegram_id(cursor, telegram_id):
    columns = get_table_columns(cursor, 'label')
    field_names = [
        'id', 'login', 'name', 'tg', 'telegram_id', 'admin', 'artist',
        'owner', 'balance', 'email', 'fio', 'phone', 'kanal', 'created_date',
        'levels', 'role', 'steezy', 'bibi', 'shvepz', 'creator',
    ]
    select_fields = [
        optional_column('id', columns),
        optional_column('login', columns),
        optional_column('name', columns),
        optional_column('tg', columns),
        optional_column('telegram_id', columns),
        optional_column('admin', columns, '0'),
        optional_column('artist', columns, '0'),
        optional_column('owner', columns, '0'),
        optional_column('balance', columns, '0'),
        optional_column('email', columns),
        optional_column('fio', columns),
        optional_column('phone', columns),
        optional_column('kanal', columns),
        optional_column('created_date', columns),
        optional_column('levels', columns),
        optional_column('role', columns),
        optional_column('steezy', columns, '0'),
        optional_column('bibi', columns, '0'),
        optional_column('shvepz', columns, '0'),
        optional_column('creator', columns, '0'),
    ]
    cursor.execute(
        f"""
        SELECT {', '.join(select_fields)}
        FROM label
        WHERE telegram_id = %s
        """,
        (telegram_id,),
    )

    row = cursor.fetchone()
    if not row:
        return None

    result = dict(zip(field_names, row))
    raw_levels = result.get('levels')
    if isinstance(raw_levels, str):
        levels = [item.strip() for item in raw_levels.strip('{}').split(',') if item.strip()]
    elif raw_levels:
        levels = list(raw_levels)
    else:
        levels = []

    role = result.get('role')
    if role and role not in levels:
        levels.append(role)

    flag_level_map = {
        'artist': result.get('artist'),
        'owner': result.get('owner'),
        'steezy': result.get('steezy'),
        'bibi': result.get('bibi'),
        'shvepz': result.get('shvepz'),
        'creator': result.get('creator'),
    }
    for level_name, enabled in flag_level_map.items():
        if enabled and level_name not in levels:
            levels.append(level_name)

    if not levels:
        levels = ['artist']

    return {
        'telegram_id': result.get('telegram_id'),
        'id': result.get('id'),
        'username': result.get('login'),
        'artistName': result.get('name'),
        'name': result.get('name'),
        'channel': result.get('kanal') or result.get('tg'),
        'levels': levels,
        'isAdmin': bool(result.get('admin')),
        'isOwner': bool(result.get('owner')),
        'isArtist': bool(result.get('artist')),
        'isSteezy': 'steezy' in levels,
        'isBibi': 'bibi' in levels,
        'isShvepz': 'shvepz' in levels,
        'isCreator': 'creator' in levels,
        'balance': float(result.get('balance')) if result.get('balance') else 0.0,
        'email': result.get('email'),
        'fio': result.get('fio'),
        'phone': result.get('phone'),
        'createdDate': result.get('created_date').isoformat() if result.get('created_date') else None,
        'registered': True,
    }

@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    """???????????????? ???????????? ?? ???????????????????????? ????????????????????"""
    try:
        # ?????????????????? ??????????????
        service_type = request.args.get('service_type', None)
        limit = request.args.get('limit', 10, type=int)

        conn = get_pg_connection()
        if not conn:
            return jsonify({'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????? ????????????
        query = '''
            SELECT l.name, r.service_type, r.rating, r.text, r.created_date
            FROM reviews r
            JOIN label l ON r.user_id = l.telegram_id
            WHERE r.status = %s
        '''
        params = ["approved"]

        # ?????????????????? ???????????? ???? ???????? ????????????, ???????? ????????????
        if service_type:
            query += ' AND r.service_type = %s'
            params.append(service_type)

        query += ' ORDER BY r.created_date DESC LIMIT %s'
        params.append(limit)

        cursor.execute(query, params)
        reviews = cursor.fetchall()

        # ?????????????????????? ?????????????????? ?? JSON-????????????
        reviews_list = []
        for review in reviews:
            artist_name, service, rating, text, date = review
            reviews_list.append({
                'artist_name': artist_name,
                'service_type': service,
                'rating': rating,
                'text': text,
                'created_date': date.isoformat() if date else None
            })

        return jsonify({
            'success': True,
            'reviews': reviews_list,
            'count': len(reviews_list)
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ??????????????: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


def media_columns_sql():
    return "audio_local_path TEXT, cover_local_path TEXT, contract_local_path TEXT, lyrics_local_path TEXT"


def ensure_media_columns(cursor):
    for column in ("audio_local_path", "cover_local_path", "contract_local_path", "lyrics_local_path"):
        cursor.execute(f"ALTER TABLE releases ADD COLUMN IF NOT EXISTS {column} TEXT")


def ensure_release_extra_columns(cursor):
    cursor.execute("ALTER TABLE releases ADD COLUMN IF NOT EXISTS extra_metadata JSONB DEFAULT '{}'::jsonb")


def ensure_promo_tables(cursor):
    if 'promo_tables' in SCHEMA_READY:
        return
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS promo_codes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            amount NUMERIC(10,2) NOT NULL DEFAULT 0,
            discount NUMERIC(10,2) DEFAULT 0,
            is_used BOOLEAN DEFAULT FALSE,
            used_by BIGINT,
            used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by BIGINT NOT NULL DEFAULT 0,
            max_uses INTEGER,
            current_uses INTEGER DEFAULT 0,
            expires_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            max_activations INTEGER,
            current_activations INTEGER DEFAULT 0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS promo_code_usage (
            id SERIAL PRIMARY KEY,
            promo_code_id INTEGER REFERENCES promo_codes(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, promo_code_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_discount_promos (
            user_id BIGINT NOT NULL,
            promo_code_id INTEGER NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, promo_code_id)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_promo_codes_active ON promo_codes(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_promo_code_usage_user_id ON promo_code_usage(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_discount_promos_user_id ON user_discount_promos(user_id)")
    SCHEMA_READY.add('promo_tables')


def ensure_orders_table(cursor):
    if 'orders_table' in SCHEMA_READY:
        return
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            service_type TEXT NOT NULL,
            amount NUMERIC(10,2) NOT NULL,
            status TEXT DEFAULT 'pending',
            payment_id TEXT UNIQUE,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT,
            metadata JSONB
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id, created_date DESC, id DESC)")
    SCHEMA_READY.add('orders_table')


def money_decimal(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def money_float(value):
    return float(money_decimal(value))


def normalize_release_type(release_type):
    raw = str(release_type or "Single").strip()
    aliases = {
        "single": "Single",
        "track": "Single",
        "maxi": "Maxi Single",
        "maxi single": "Maxi Single",
        "maxi_single": "Maxi Single",
        "ep": "EP",
        "album": "ALBUM",
        "альбом": "ALBUM",
    }
    return aliases.get(raw.lower(), raw if raw in DISTRIBUTION_PRICES else "Single")


def distribution_price_for(release_type):
    return DISTRIBUTION_PRICES[normalize_release_type(release_type)]


def user_has_artist_role(cursor, user_id):
    user = load_user_by_telegram_id(cursor, user_id)
    if not user:
        return False
    levels = {str(level).lower() for level in (user.get('levels') or [])}
    role = str(user.get('role') or '').lower()
    return bool(user.get('isArtist') or role == 'artist' or 'artist' in levels)


def promo_limit_reached(limit, current):
    return limit is not None and int(current or 0) >= int(limit)


def ensure_label_user(cursor, user_id):
    cursor.execute("SELECT id FROM label WHERE telegram_id = %s LIMIT 1", (user_id,))
    if cursor.fetchone():
        return
    cursor.execute(
        """
        INSERT INTO label (telegram_id, created_date, balance)
        VALUES (%s, CURRENT_TIMESTAMP, 0)
        """,
        (user_id,),
    )


def get_active_discount_promo(cursor, user_id):
    ensure_promo_tables(cursor)
    cursor.execute(
        """
        SELECT p.id, p.code, COALESCE(p.discount, 0), udp.created_at
        FROM user_discount_promos udp
        JOIN promo_codes p ON p.id = udp.promo_code_id
        WHERE udp.user_id = %s
          AND COALESCE(p.discount, 0) > 0
          AND (p.expires_at IS NULL OR p.expires_at >= CURRENT_TIMESTAMP)
        ORDER BY COALESCE(p.discount, 0) DESC, udp.created_at ASC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    promo_id, code, discount, created_at = row
    discount_value = min(Decimal("100.00"), max(Decimal("0.00"), money_decimal(discount)))
    return {
        "promo_id": promo_id,
        "code": code,
        "discount_percent": discount_value,
        "created_at": created_at.isoformat() if created_at else None,
    }


def calculate_distribution_payment(cursor, user_id, release_type):
    base_price = distribution_price_for(release_type)
    is_artist_free = user_has_artist_role(cursor, user_id)
    active_discount = None if is_artist_free else get_active_discount_promo(cursor, user_id)
    discount_percent = active_discount["discount_percent"] if active_discount else Decimal("0.00")
    discount_amount = base_price if is_artist_free else (
        base_price * discount_percent / Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    final_price = Decimal("0.00") if is_artist_free else max(Decimal("0.00"), base_price - discount_amount)
    cursor.execute("SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s", (user_id,))
    balance_row = cursor.fetchone()
    balance = money_decimal(balance_row[0] if balance_row else 0)
    return {
        "release_type": normalize_release_type(release_type),
        "base_price": base_price,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "final_price": final_price,
        "balance": balance,
        "balance_after": balance - final_price,
        "affordable": balance >= final_price,
        "active_discount": active_discount,
        "is_free": is_artist_free,
        "free_reason": "artist_role" if is_artist_free else None,
    }


def public_payment(payment):
    result = dict(payment)
    for key in ("base_price", "discount_percent", "discount_amount", "final_price", "balance", "balance_after"):
        result[key] = money_float(result.get(key))
    if result.get("active_discount"):
        result["active_discount"] = {
            **result["active_discount"],
            "discount_percent": money_float(result["active_discount"].get("discount_percent")),
        }
    return result


def record_distribution_order(cursor, user_id, amount, release_type, release_name, payment):
    ensure_orders_table(cursor)
    order_columns = get_table_columns(cursor, "orders")
    order_payload = {
        "user_id": user_id,
        "service_type": "distribution",
        "amount": amount,
        "status": "completed",
        "created_date": datetime.now(),
        "updated_date": datetime.now(),
        "description": f"Дистрибуция: {release_name or normalize_release_type(release_type)}",
        "metadata": Json({
            "source": "site",
            "release_type": normalize_release_type(release_type),
            "release_name": release_name,
            "base_price": str(payment["base_price"]),
            "discount_percent": str(payment["discount_percent"]),
            "discount_amount": str(payment["discount_amount"]),
            "active_discount": {
                "promo_id": payment["active_discount"]["promo_id"],
                "code": payment["active_discount"]["code"],
            } if payment.get("active_discount") else None,
            "is_free": bool(payment.get("is_free")),
            "free_reason": payment.get("free_reason"),
        }),
    }
    insert_columns = [column for column in order_payload if column in order_columns]
    placeholders = ", ".join(["%s"] * len(insert_columns))
    cursor.execute(
        f"INSERT INTO orders ({', '.join(insert_columns)}) VALUES ({placeholders}) RETURNING id",
        tuple(order_payload[column] for column in insert_columns),
    )
    return cursor.fetchone()[0]


def charge_distribution(cursor, user_id, release_type, release_name):
    ensure_promo_tables(cursor)
    ensure_label_user(cursor, user_id)
    cursor.execute("SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s FOR UPDATE", (user_id,))
    if not cursor.fetchone():
        raise ValueError("Пользователь не найден")
    payment = calculate_distribution_payment(cursor, user_id, release_type)
    if not payment["affordable"]:
        return {
            "success": False,
            "error": (
                f"Недостаточно средств: нужно {money_float(payment['final_price']):.0f} ₽, "
                f"на балансе {money_float(payment['balance']):.0f} ₽."
            ),
            "payment": public_payment(payment),
        }
    cursor.execute(
        """
        UPDATE label
        SET balance = COALESCE(balance, 0) - %s
        WHERE telegram_id = %s
        RETURNING COALESCE(balance, 0)
        """,
        (payment["final_price"], user_id),
    )
    balance_after = money_decimal(cursor.fetchone()[0])
    payment["balance_after"] = balance_after
    order_id = record_distribution_order(cursor, user_id, payment["final_price"], release_type, release_name, payment)
    if payment.get("active_discount"):
        cursor.execute(
            "DELETE FROM user_discount_promos WHERE user_id = %s AND promo_code_id = %s",
            (user_id, payment["active_discount"]["promo_id"]),
        )
    return {
        "success": True,
        "order_id": order_id,
        "payment": public_payment(payment),
        "balance_after": money_float(balance_after),
    }


def activate_promo_for_site(user_id, raw_code):
    code = (raw_code or "").strip().upper()
    if not code:
        return {"success": False, "status": "empty", "error": "Введите промокод."}, 400

    conn = get_pg_connection()
    if not conn:
        return {"success": False, "status": "db_unavailable", "error": "База данных недоступна."}, 500

    cursor = conn.cursor()
    try:
        ensure_promo_tables(cursor)
        ensure_label_user(cursor, user_id)
        cursor.execute(
            """
            SELECT id, code, amount, COALESCE(discount, 0), is_used, used_by, used_at,
                max_uses, current_uses, expires_at, is_active,
                max_activations, current_activations
            FROM promo_codes
            WHERE UPPER(code) = UPPER(%s) AND COALESCE(is_active, TRUE) = TRUE
            FOR UPDATE
            """,
            (code,),
        )
        promo = cursor.fetchone()
        if not promo:
            conn.rollback()
            return {"success": False, "status": "not_found", "error": "Промокод не найден или неактивен."}, 404

        (
            promo_id,
            stored_code,
            amount,
            discount,
            is_used,
            used_by,
            used_at,
            max_uses,
            current_uses,
            expires_at,
            is_active,
            max_activations,
            current_activations,
        ) = promo

        if expires_at and expires_at < datetime.now():
            cursor.execute("UPDATE promo_codes SET is_active = FALSE WHERE id = %s", (promo_id,))
            conn.commit()
            return {"success": False, "status": "expired", "error": "Промокод истёк.", "code": stored_code}, 410

        amount_value = money_decimal(amount)
        discount_value = money_decimal(discount)

        if discount_value > 0:
            if promo_limit_reached(max_uses, current_uses):
                cursor.execute("UPDATE promo_codes SET is_active = FALSE WHERE id = %s", (promo_id,))
                conn.commit()
                return {"success": False, "status": "limit_reached", "error": "Промокод достиг лимита использований.", "code": stored_code}, 409

            cursor.execute(
                "SELECT 1 FROM user_discount_promos WHERE user_id = %s AND promo_code_id = %s",
                (user_id, promo_id),
            )
            if cursor.fetchone():
                conn.rollback()
                return {
                    "success": False,
                    "status": "discount_already_active",
                    "error": "Эта скидка уже активирована и применится при отправке релиза.",
                    "code": stored_code,
                    "discount": money_float(discount_value),
                }, 409

            next_current_uses = int(current_uses or 0) + 1
            cursor.execute(
                """
                INSERT INTO user_discount_promos (user_id, promo_code_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (user_id, promo_id),
            )
            cursor.execute(
                """
                UPDATE promo_codes
                SET current_uses = %s,
                    used_by = %s,
                    used_at = CURRENT_TIMESTAMP,
                    is_active = CASE
                        WHEN max_uses IS NOT NULL AND %s >= max_uses THEN FALSE
                        ELSE COALESCE(is_active, TRUE)
                    END
                WHERE id = %s
                """,
                (next_current_uses, user_id, next_current_uses, promo_id),
            )
            conn.commit()
            return {
                "success": True,
                "status": "discount_activated",
                "message": f"Скидка {money_float(discount_value):.0f}% активирована для следующей дистрибуции.",
                "code": stored_code,
                "discount": money_float(discount_value),
            }, 200

        if amount_value <= 0:
            conn.rollback()
            return {"success": False, "status": "invalid", "error": "Промокод некорректен: нет суммы пополнения или скидки.", "code": stored_code}, 400

        cursor.execute(
            "SELECT 1 FROM promo_code_usage WHERE user_id = %s AND promo_code_id = %s",
            (user_id, promo_id),
        )
        if cursor.fetchone():
            conn.rollback()
            return {"success": False, "status": "already_used", "error": "Вы уже использовали этот промокод.", "code": stored_code}, 409

        active_limit = max_activations if max_activations is not None else max_uses
        active_current = current_activations if max_activations is not None else current_uses
        if promo_limit_reached(active_limit, active_current):
            cursor.execute("UPDATE promo_codes SET is_active = FALSE, is_used = TRUE WHERE id = %s", (promo_id,))
            conn.commit()
            return {"success": False, "status": "limit_reached", "error": "Промокод достиг лимита использований.", "code": stored_code}, 409

        next_current_activations = int(current_activations or 0) + 1
        next_current_uses = int(current_uses or 0) + 1
        cursor.execute(
            """
            UPDATE label
            SET balance = COALESCE(balance, 0) + %s
            WHERE telegram_id = %s
            RETURNING COALESCE(balance, 0)
            """,
            (amount_value, user_id),
        )
        balance_after = money_decimal(cursor.fetchone()[0])
        cursor.execute(
            "INSERT INTO promo_code_usage (user_id, promo_code_id) VALUES (%s, %s)",
            (user_id, promo_id),
        )
        cursor.execute(
            """
            UPDATE promo_codes
            SET current_activations = %s,
                current_uses = %s,
                used_by = %s,
                used_at = CURRENT_TIMESTAMP,
                is_used = CASE
                    WHEN (
                        (max_activations IS NOT NULL AND %s >= max_activations)
                        OR (max_activations IS NULL AND max_uses IS NOT NULL AND %s >= max_uses)
                    )
                    THEN TRUE ELSE COALESCE(is_used, FALSE)
                END,
                is_active = CASE
                    WHEN (
                        (max_activations IS NOT NULL AND %s >= max_activations)
                        OR (max_activations IS NULL AND max_uses IS NOT NULL AND %s >= max_uses)
                    )
                    THEN FALSE ELSE COALESCE(is_active, TRUE)
                END
            WHERE id = %s
            """,
            (
                next_current_activations,
                next_current_uses,
                user_id,
                next_current_activations,
                next_current_uses,
                next_current_activations,
                next_current_uses,
                promo_id,
            ),
        )
        conn.commit()
        return {
            "success": True,
            "status": "balance_activated",
            "message": f"На баланс зачислено {money_float(amount_value):.0f} ₽.",
            "code": stored_code,
            "amount": money_float(amount_value),
            "balance": money_float(balance_after),
        }, 200
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def safe_filename(name, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "").strip("._")
    return cleaned or fallback


def storage_relative_path(user_id, release_id, kind, filename):
    return str(Path("releases") / f"user_{int(user_id)}" / f"release_{int(release_id)}" / kind / safe_filename(filename, f"{kind}.bin"))


def cover_thumb_relative_path(cover_relative_path, size=512):
    source = Path(cover_relative_path)
    release_dir = source.parent.parent
    stem = safe_filename(source.stem, "cover")
    return str(release_dir / "cover_thumb" / f"{stem}_{size}.webp")


def storage_absolute_path(relative_path):
    root = STORAGE_ROOT.resolve()
    path = (root / relative_path).resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Invalid media path")
    return path


def infer_mimetype(filename, fallback="application/octet-stream"):
    import mimetypes
    return mimetypes.guess_type(filename or "")[0] or fallback


def detect_media_mimetype(path, kind=None):
    guessed = infer_mimetype(path.name)
    if guessed != "application/octet-stream":
        return guessed
    try:
        head = path.open("rb").read(16)
    except OSError:
        head = b""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"RIFF") and b"WAVE" in head[:12]:
        return "audio/wav"
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if kind == "audio":
        return "audio/mpeg"
    if kind == "cover":
        return "image/jpeg"
    return "application/octet-stream"


def save_upload_locally(file_storage, user_id, release_id, kind):
    filename = safe_filename(file_storage.filename, f"{kind}.bin")
    relative = storage_relative_path(user_id, release_id, kind, filename)
    path = storage_absolute_path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_storage.stream.seek(0)
    file_storage.save(path)
    file_storage.stream.seek(0)
    if kind == "cover":
        ensure_cover_thumbnail(relative)
    return relative


def ensure_cover_thumbnail(cover_relative_path, size=512):
    try:
        source = storage_absolute_path(cover_relative_path)
        if not source.exists():
            return None
        thumb_relative = cover_thumb_relative_path(cover_relative_path, size=size)
        thumb = storage_absolute_path(thumb_relative)
        if thumb.exists() and thumb.stat().st_mtime >= source.stat().st_mtime and thumb.stat().st_size > 0:
            return thumb_relative
        thumb.parent.mkdir(parents=True, exist_ok=True)
        tmp = thumb.with_suffix('.tmp.webp')
        cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-i', str(source),
            '-vf', f'scale={size}:{size}:force_original_aspect_ratio=increase,crop={size}:{size}',
            '-frames:v', '1', '-c:v', 'libwebp', '-quality', '82', str(tmp),
        ]
        subprocess.run(cmd, check=True, timeout=45)
        tmp.replace(thumb)
        return thumb_relative
    except Exception as exc:
        logger.warning("Could not create cover thumbnail for %s: %s", cover_relative_path, exc)
        return None


def download_telegram_file_to_storage(file_id, user_id, release_id, kind, filename=None):
    url, error, status = resolve_telegram_file(file_id)
    if not url:
        return None, error or "File is unavailable", status

    guessed = filename or url.rsplit("/", 1)[-1] or f"{kind}.bin"
    relative = storage_relative_path(user_id, release_id, kind, guessed)
    path = storage_absolute_path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)

    upstream = requests.get(url, stream=True, timeout=120)
    if upstream.status_code != 200:
        return None, f"Could not download file: HTTP {upstream.status_code}", upstream.status_code
    with path.open("wb") as target:
        for chunk in upstream.iter_content(chunk_size=1024 * 1024):
            if chunk:
                target.write(chunk)
    if kind == "cover":
        ensure_cover_thumbnail(relative)
    return relative, None, 200


def upload_path_to_telegram(path, file_type='document', filename=None, mimetype=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_STORAGE_CHAT_ID:
        raise ValueError("Bot token and storage chat id must be configured")

    method_map = {
        'photo': ('sendPhoto', 'photo'),
        'audio': ('sendAudio', 'audio'),
        'document': ('sendDocument', 'document')
    }
    method, field_name = method_map.get(file_type, ('sendDocument', 'document'))
    filename = filename or Path(path).name
    mimetype = mimetype or infer_mimetype(filename)
    with open(path, "rb") as handle:
        files = {field_name: (filename, handle, mimetype)}
        response = requests.post(
            f"{TELEGRAM_API_URL}/{method}",
            data={'chat_id': TELEGRAM_STORAGE_CHAT_ID},
            files=files,
            timeout=180,
        )
    result = response.json()
    if not result.get('ok'):
        logger.error("Telegram API error: %s", result)
        raise ValueError(f"Telegram API error: {result.get('description', 'Unknown error')}")
    payload = result['result']
    if method == 'sendPhoto':
        return payload['photo'][-1]['file_id']
    if method == 'sendAudio':
        return payload['audio']['file_id']
    return payload['document']['file_id']


def upload_file_to_telegram(file_storage, file_type='document'):
    """?????????????????? ???????? ?? Telegram ?? ???????????????? file_id"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_STORAGE_CHAT_ID:
        raise ValueError("Bot token ?????? storage chat id ???? ??????????????")

    method_map = {
        'photo': ('sendPhoto', 'photo'),
        'audio': ('sendAudio', 'audio'),
        'document': ('sendDocument', 'document')
    }
    method, field_name = method_map.get(file_type, ('sendDocument', 'document'))

    file_storage.stream.seek(0)

    # ?????? ???????? ?????????? ?????????????????? ???????????????????? MIME ??????
    if file_type == 'photo':
        # ?????????????????? ???????????????????? ?????????? ?????? ?????????????????????? MIME ????????
        filename = file_storage.filename.lower() if file_storage.filename else ''
        if filename.endswith('.png'):
            mime_type = 'image/png'
        elif filename.endswith(('.jpg', '.jpeg')):
            mime_type = 'image/jpeg'
        elif filename.endswith('.webp'):
            mime_type = 'image/webp'
        else:
            # ???????????????????? ???????????????????????? MIME ?????? ?????? ???????????????????? ???? ??????????????????
            mime_type = file_storage.mimetype or 'image/jpeg'

        # ?????? sendPhoto ?????????? ???????????????? ???????? ?????? photo, ?? ???? document
        files = {
            field_name: (file_storage.filename, file_storage.stream, mime_type)
        }
    else:
        files = {
            field_name: (file_storage.filename, file_storage.stream, file_storage.mimetype or 'application/octet-stream')
        }

    data = {'chat_id': TELEGRAM_STORAGE_CHAT_ID}

    response = requests.post(f"{TELEGRAM_API_URL}/{method}", data=data, files=files, timeout=60)
    result = response.json()
    if not result.get('ok'):
        logger.error(f"Telegram API error: {result}")
        raise ValueError(f"Telegram API error: {result.get('description', 'Unknown error')}")

    payload = result['result']
    if method == 'sendPhoto':
        # ?????? ???????? ???????????????????? file_id ???????????? ???????????????? ?????????????? (?????????????????? ?? ??????????????)
        return payload['photo'][-1]['file_id']
    elif method == 'sendAudio':
        return payload['audio']['file_id']
    else:
        return payload['document']['file_id']


def resolve_telegram_file(file_id):
    if not TELEGRAM_BOT_TOKEN:
        return None, 'BOT_TOKEN is not configured', 503
    response = requests.get(
        f"{TELEGRAM_API_URL}/getFile",
        params={"file_id": file_id},
        timeout=20,
    )
    data = response.json()
    if not data.get("ok"):
        logger.error("Telegram getFile error: %s", data)
        description = data.get('description') or 'File is unavailable'
        status = 413 if 'file is too big' in description.lower() else 404
        return None, description, status
    file_path = data.get("result", {}).get("file_path")
    if not file_path:
        return None, 'Telegram did not return file_path', 404
    return f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}", None, 200


def telegram_file_url(file_id):
    url, _error, _status = resolve_telegram_file(file_id)
    return url


@app.route('/api/files/telegram/<path:file_id>', methods=['GET'])
def proxy_telegram_file(file_id, preferred_mimetype=None):
    try:
        url, error, status = resolve_telegram_file(file_id)
        if not url:
            return jsonify({'success': False, 'error': error or 'File is unavailable'}), status

        upstream = requests.get(url, stream=True, timeout=60)
        if upstream.status_code != 200:
            return jsonify({'success': False, 'error': 'Could not download file'}), upstream.status_code

        content_type = upstream.headers.get('Content-Type', 'application/octet-stream')
        guessed_type = infer_mimetype(url)
        if content_type == 'application/octet-stream' and preferred_mimetype:
            content_type = preferred_mimetype
        elif content_type == 'application/octet-stream' and guessed_type != 'application/octet-stream':
            content_type = guessed_type
        headers = {}
        if upstream.headers.get('Content-Length'):
            headers['Content-Length'] = upstream.headers['Content-Length']

        return Response(
            upstream.iter_content(chunk_size=8192),
            content_type=content_type,
            headers=headers,
            direct_passthrough=True,
        )
    except Exception as e:
        logger.error("Error proxying Telegram file: %s", e)
        return jsonify({'success': False, 'error': 'Could not stream file'}), 500

@app.route('/api/files/upload', methods=['POST'])
def upload_file():
    """?????????????????? ???????? ?? Telegram ?? ?????????????? file_id"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '???????? ???? ??????????????'}), 400

        file = request.files['file']
        file_type = request.form.get('fileType', 'document')

        if not file.filename:
            return jsonify({'success': False, 'error': '?????? ?????????? ???? ??????????????'}), 400

        file_id = upload_file_to_telegram(file, file_type=file_type)

        return jsonify({
            'success': True,
            'file_id': file_id
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ???????????????? ??????????: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': '???????????? ???????????????? ??????????'}), 500


def is_admin_user(cursor, telegram_id):
    user = load_user_by_telegram_id(cursor, telegram_id)
    return bool(user and (user.get('isAdmin') or user.get('isOwner')))


def directory_size_bytes(path):
    root = Path(path)
    if not root.exists():
        return 0
    total = 0
    for file_path in root.rglob('*'):
        if file_path.is_file():
            try:
                total += file_path.stat().st_size
            except OSError:
                pass
    return total


@app.route('/admin', methods=['GET'])
@app.route('/admin/', methods=['GET'])
def admin_panel_page():
    return send_from_directory(os.path.dirname(__file__), 'admin.html')


@app.route('/api/admin/overview', methods=['GET'])
def admin_overview():
    try:
        admin_user_id = request.args.get('admin_user_id', type=int)
        if not admin_user_id:
            return jsonify({'success': False, 'error': 'admin_user_id is required'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()

        if not is_admin_user(cursor, admin_user_id):
            return jsonify({'success': False, 'error': 'Admin access required'}), 403

        ensure_media_columns(cursor)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM label")
        users_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM releases")
        releases_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM releases WHERE COALESCE(status, 'pending') IN ('pending', 'на рассмотрении', '????????????')")
        pending_count = cursor.fetchone()[0]
        cursor.execute("""
            SELECT id, user_id, release_name, artist_name, status,
                   audio_file_id IS NOT NULL OR audio_local_path IS NOT NULL AS has_audio,
                   cover_file_id IS NOT NULL OR cover_local_path IS NOT NULL AS has_cover,
                   created_at
            FROM releases
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 40
        """)
        releases = [
            {
                'id': row[0],
                'user_id': row[1],
                'release_name': row[2],
                'artist_name': row[3],
                'status': row[4],
                'has_audio': row[5],
                'has_cover': row[6],
                'created_at': row[7].isoformat() if row[7] else None,
            }
            for row in cursor.fetchall()
        ]

        return jsonify({
            'success': True,
            'stats': {
                'users_count': users_count,
                'releases_count': releases_count,
                'pending_count': pending_count,
                'storage_bytes': directory_size_bytes(STORAGE_ROOT),
            },
            'releases': releases,
        })
    except Exception as e:
        logger.error("Error loading admin overview: %s", e)
        return jsonify({'success': False, 'error': 'Could not load admin overview'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


ADMIN_RELEASE_STATUSES = [
    "pending",
    "На рассмотрении",
    "Принят",
    "Отправлен на площадки",
    "Отгружен на площадки",
    "Релиз",
    "Отозван с площадок",
    "rejected",
]


def admin_request_context():
    admin_user_id = request.args.get('admin_user_id', type=int)
    if not admin_user_id and request.is_json:
        admin_user_id = (request.get_json(silent=True) or {}).get('admin_user_id')
    if not admin_user_id:
        return None, None, (jsonify({'success': False, 'error': 'admin_user_id is required'}), 400)

    conn = get_pg_connection()
    if not conn:
        return None, None, (jsonify({'success': False, 'error': 'Database connection failed'}), 500)
    cursor = conn.cursor()
    if not is_admin_user(cursor, int(admin_user_id)):
        cursor.close()
        conn.close()
        return None, None, (jsonify({'success': False, 'error': 'Admin access required'}), 403)
    return conn, cursor, None


def close_cursor(conn, cursor):
    try:
        if cursor:
            cursor.close()
    finally:
        if conn:
            conn.close()


def release_payload(row):
    return {
        'id': row[0],
        'user_id': row[1],
        'release_type': row[2],
        'release_name': row[3],
        'artist_name': row[4],
        'genre': row[5],
        'status': row[6],
        'release_date': row[7].isoformat() if row[7] else None,
        'created_at': row[8].isoformat() if row[8] else None,
        'is_album': row[9],
        'is_track': row[10],
        'album_id': row[11],
        'upc_code': row[12],
        'has_audio': row[13],
        'has_cover': row[14],
        'owner_name': row[15],
        'owner_tg': row[16],
    }


@app.route('/api/admin/users', methods=['GET'])
def admin_users_list():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        query = (request.args.get('q') or '').strip()
        params = []
        where = "WHERE telegram_id IS NOT NULL"
        if query:
            like = f"%{query}%"
            where += " AND (CAST(telegram_id AS TEXT) ILIKE %s OR COALESCE(name,'') ILIKE %s OR COALESCE(tg,'') ILIKE %s OR COALESCE(email,'') ILIKE %s)"
            params.extend([like, like, like, like])
        cursor.execute(
            f"""
            WITH filtered_users AS (
                SELECT l.telegram_id, l.name, l.tg, l.email, COALESCE(l.balance,0) AS balance,
                       COALESCE(l.admin,0) AS admin, COALESCE(l.artist,0) AS artist,
                       COALESCE(l.owner,FALSE) AS owner, COALESCE(l.creator,FALSE) AS creator,
                       l.role, l.created_date, l.id
                FROM label l
                {where}
                ORDER BY l.created_date DESC NULLS LAST, l.id DESC
                LIMIT 200
            ),
            release_counts AS (
                SELECT r.user_id, COUNT(*) AS releases_count
                FROM releases r
                JOIN filtered_users fu ON fu.telegram_id = r.user_id
                GROUP BY r.user_id
            ),
            order_counts AS (
                SELECT o.user_id, COUNT(*) AS orders_count
                FROM orders o
                JOIN filtered_users fu ON fu.telegram_id = o.user_id
                GROUP BY o.user_id
            )
            SELECT fu.telegram_id, fu.name, fu.tg, fu.email, fu.balance, fu.admin,
                   fu.artist, fu.owner, fu.creator, fu.role, fu.created_date,
                   COALESCE(rc.releases_count, 0), COALESCE(oc.orders_count, 0)
            FROM filtered_users fu
            LEFT JOIN release_counts rc ON rc.user_id = fu.telegram_id
            LEFT JOIN order_counts oc ON oc.user_id = fu.telegram_id
            ORDER BY fu.created_date DESC NULLS LAST, fu.id DESC
            """,
            tuple(params),
        )
        users = [
            {
                'telegram_id': row[0], 'name': row[1], 'tg': row[2], 'email': row[3],
                'balance': float(row[4] or 0), 'admin': bool(row[5]), 'artist': bool(row[6]),
                'owner': bool(row[7]), 'creator': bool(row[8]), 'role': row[9],
                'created_date': row[10].isoformat() if row[10] else None,
                'releases_count': int(row[11] or 0), 'orders_count': int(row[12] or 0),
            }
            for row in cursor.fetchall()
        ]
        return jsonify({'success': True, 'users': users})
    except Exception as e:
        logger.error("Error loading admin users: %s", e)
        return jsonify({'success': False, 'error': 'Could not load users'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
def admin_user_detail(user_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        user = load_user_by_telegram_id(cursor, user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        cursor.execute(
            """
            SELECT id, user_id, release_type, release_name, artist_name, genre, status, release_date, created_at,
                   COALESCE(is_album,FALSE), COALESCE(is_track,FALSE), album_id, upc_code,
                   audio_file_id IS NOT NULL OR audio_local_path IS NOT NULL AS has_audio,
                   cover_file_id IS NOT NULL OR cover_local_path IS NOT NULL AS has_cover,
                   NULL, NULL
            FROM releases
            WHERE user_id = %s
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 80
            """,
            (user_id,),
        )
        releases = [release_payload(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT id, service_type, amount, status, created_date, description
            FROM orders WHERE user_id = %s
            ORDER BY created_date DESC NULLS LAST, id DESC LIMIT 80
            """,
            (user_id,),
        )
        orders = [
            {'id': r[0], 'service_type': r[1], 'amount': float(r[2] or 0), 'status': r[3], 'created_date': r[4].isoformat() if r[4] else None, 'description': r[5]}
            for r in cursor.fetchall()
        ] if table_exists(cursor, 'orders') else []
        reports = []
        if table_exists(cursor, 'report_requests'):
            cursor.execute("SELECT id, request_type, status, created_at, completed_at, notes FROM report_requests WHERE user_id=%s ORDER BY created_at DESC LIMIT 50", (user_id,))
            reports = [{'id': r[0], 'request_type': r[1], 'status': r[2], 'created_at': r[3].isoformat() if r[3] else None, 'completed_at': r[4].isoformat() if r[4] else None, 'notes': r[5]} for r in cursor.fetchall()]
        return jsonify({'success': True, 'user': user, 'releases': releases, 'orders': orders, 'reports': reports})
    except Exception as e:
        logger.error("Error loading admin user detail: %s", e)
        return jsonify({'success': False, 'error': 'Could not load user'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/users/<int:user_id>/roles', methods=['PUT'])
def admin_update_user_roles(user_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        data = request.get_json() or {}
        columns = get_table_columns(cursor, 'label')
        allowed = {
            'admin': ('admin', lambda v: 1 if bool(v) else 0),
            'artist': ('artist', lambda v: 1 if bool(v) else 0),
            'owner': ('owner', bool),
            'creator': ('creator', bool),
            'steezy': ('steezy', bool),
            'bibi': ('bibi', bool),
            'shvepz': ('shvepz', bool),
            'role': ('role', lambda v: str(v or 'artist')),
        }
        sets, params = [], []
        for key, (column, caster) in allowed.items():
            if key in data and column in columns:
                sets.append(f"{column} = %s")
                params.append(caster(data[key]))
        if not sets:
            return jsonify({'success': False, 'error': 'No role fields provided'}), 400
        params.append(user_id)
        cursor.execute(f"UPDATE label SET {', '.join(sets)} WHERE telegram_id = %s", tuple(params))
        conn.commit()
        return jsonify({'success': True, 'user': load_user_by_telegram_id(cursor, user_id)})
    except Exception as e:
        conn.rollback()
        logger.error("Error updating user roles: %s", e)
        return jsonify({'success': False, 'error': 'Could not update roles'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/users/<int:user_id>/balance', methods=['POST'])
def admin_adjust_user_balance(user_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        data = request.get_json() or {}
        delta = money_decimal(data.get('delta'))
        if delta == 0:
            return jsonify({'success': False, 'error': 'Delta must not be zero'}), 400
        reason = data.get('reason') or 'Админ корректировка баланса'
        cursor.execute("UPDATE label SET balance = COALESCE(balance,0) + %s WHERE telegram_id=%s RETURNING balance", (delta, user_id))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return jsonify({'success': False, 'error': 'User not found'}), 404
        ensure_orders_table(cursor)
        cursor.execute(
            """
            INSERT INTO orders (user_id, service_type, amount, status, created_date, updated_date, description, metadata)
            VALUES (%s, 'other', %s, 'completed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, %s)
            """,
            (user_id, abs(delta), reason, Json({'source': 'admin', 'delta': str(delta), 'admin_user_id': data.get('admin_user_id')})),
        )
        conn.commit()
        return jsonify({'success': True, 'balance': money_float(row[0])})
    except Exception as e:
        conn.rollback()
        logger.error("Error adjusting balance: %s", e)
        return jsonify({'success': False, 'error': 'Could not adjust balance'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/releases', methods=['GET'])
def admin_releases_list():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        query = (request.args.get('q') or '').strip()
        status = (request.args.get('status') or 'all').strip()
        user_id = request.args.get('user_id', type=int)
        params = []
        where = "WHERE 1=1"
        if user_id:
            where += " AND r.user_id = %s"
            params.append(user_id)
        if status and status != 'all':
            where += " AND COALESCE(r.status,'pending') = %s"
            params.append(status)
        if query:
            like = f"%{query}%"
            where += " AND (COALESCE(r.release_name,'') ILIKE %s OR COALESCE(r.artist_name,'') ILIKE %s OR CAST(r.id AS TEXT) ILIKE %s OR CAST(r.user_id AS TEXT) ILIKE %s)"
            params.extend([like, like, like, like])
        cursor.execute(
            f"""
            SELECT r.id, r.user_id, r.release_type, r.release_name, r.artist_name, r.genre, r.status,
                   r.release_date, r.created_at, COALESCE(r.is_album,FALSE), COALESCE(r.is_track,FALSE), r.album_id, r.upc_code,
                   r.audio_file_id IS NOT NULL OR r.audio_local_path IS NOT NULL AS has_audio,
                   r.cover_file_id IS NOT NULL OR r.cover_local_path IS NOT NULL AS has_cover,
                   l.name, l.tg
            FROM releases r
            LEFT JOIN label l ON l.telegram_id = r.user_id
            {where}
            ORDER BY r.created_at DESC NULLS LAST, r.id DESC
            LIMIT 250
            """,
            tuple(params),
        )
        releases = [release_payload(row) for row in cursor.fetchall()]
        return jsonify({'success': True, 'releases': releases, 'statuses': ADMIN_RELEASE_STATUSES})
    except Exception as e:
        logger.error("Error loading admin releases: %s", e)
        return jsonify({'success': False, 'error': 'Could not load releases'}), 500
    finally:
        close_cursor(conn, cursor)


def admin_release_row_to_dict(row):
    (
        release_id, user_id, release_type, artist_name, release_name, producer,
        genre, cover_file_id, audio_file_id, release_date, performer_name,
        music_author, contract_file_id, videoshot_url, explicit_content,
        lyrics_file_id, preview_start, yandex_soon, create_links,
        tiktok_commercial, tiktok_full_version, status, created_at, is_album,
        is_track, album_id, upc_code, track_number, platform_links, release_link,
        audio_local_path, cover_local_path, contract_local_path, lyrics_local_path,
        extra_metadata
    ) = row
    def media_url(kind, file_id, local_path):
        if file_id or local_path:
            return f"/api/releases/{release_id}/media/{kind}?user_id={user_id}"
        return None
    return {
        'id': release_id,
        'user_id': user_id,
        'release_type': release_type,
        'artist_name': artist_name,
        'release_name': release_name,
        'producer': producer,
        'genre': genre,
        'cover_file_id': cover_file_id,
        'cover_local_path': cover_local_path,
        'cover_url': media_url('cover', cover_file_id, cover_local_path),
        'audio_file_id': audio_file_id,
        'audio_local_path': audio_local_path,
        'audio_url': media_url('audio', audio_file_id, audio_local_path),
        'contract_file_id': contract_file_id,
        'contract_local_path': contract_local_path,
        'contract_url': media_url('contract', contract_file_id, contract_local_path),
        'lyrics_file_id': lyrics_file_id,
        'lyrics_local_path': lyrics_local_path,
        'lyrics_url': media_url('lyrics', lyrics_file_id, lyrics_local_path),
        'release_date': release_date.isoformat() if release_date else None,
        'performer_name': performer_name,
        'music_author': music_author,
        'videoshot_url': videoshot_url,
        'explicit_content': explicit_content,
        'preview_start': preview_start,
        'yandex_soon': yandex_soon,
        'create_links': create_links,
        'tiktok_commercial': tiktok_commercial,
        'tiktok_full_version': tiktok_full_version,
        'status': status,
        'created_at': created_at.isoformat() if created_at else None,
        'is_album': is_album,
        'is_track': is_track,
        'album_id': album_id,
        'upc_code': upc_code,
        'track_number': track_number,
        'platform_links': platform_links or {},
        'release_link': release_link,
        'extra_metadata': extra_metadata or {},
    }


ADMIN_RELEASE_SELECT = """
    SELECT id, user_id, release_type, artist_name, release_name, producer,
           genre, cover_file_id, audio_file_id, release_date, performer_name,
           music_author, contract_file_id, videoshot_url, explicit_content,
           lyrics_file_id, preview_start, yandex_soon, create_links,
           tiktok_commercial, tiktok_full_version, status, created_at,
           COALESCE(is_album,FALSE), COALESCE(is_track,FALSE), album_id, upc_code, track_number,
           platform_links, release_link, audio_local_path, cover_local_path,
           contract_local_path, lyrics_local_path, extra_metadata
    FROM releases
"""


@app.route('/api/admin/releases/<int:release_id>', methods=['GET'])
def admin_release_detail(release_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        ensure_media_columns(cursor)
        ensure_release_extra_columns(cursor)
        conn.commit()
        cursor.execute(ADMIN_RELEASE_SELECT + " WHERE id = %s", (release_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Release not found'}), 404
        release = admin_release_row_to_dict(row)
        tracks = []
        parent_album = None
        if release.get('is_album'):
            cursor.execute(ADMIN_RELEASE_SELECT + " WHERE album_id = %s ORDER BY track_number NULLS LAST, id", (release_id,))
            tracks = [admin_release_row_to_dict(track_row) for track_row in cursor.fetchall()]
        elif release.get('is_track') and release.get('album_id'):
            cursor.execute(ADMIN_RELEASE_SELECT + " WHERE id = %s", (release['album_id'],))
            album_row = cursor.fetchone()
            parent_album = admin_release_row_to_dict(album_row) if album_row else None
        cursor.execute("SELECT name, tg, email, balance FROM label WHERE telegram_id = %s", (release['user_id'],))
        owner_row = cursor.fetchone()
        owner = None
        if owner_row:
            owner = {'name': owner_row[0], 'tg': owner_row[1], 'email': owner_row[2], 'balance': money_float(owner_row[3])}
        return jsonify({
            'success': True,
            'release': release,
            'tracks': tracks,
            'parent_album': parent_album,
            'owner': owner,
            'kind': 'album' if release.get('is_album') else 'track' if release.get('is_track') else 'single',
        })
    except Exception as e:
        logger.error("Error loading admin release detail: %s", e)
        return jsonify({'success': False, 'error': 'Could not load release detail'}), 500
    finally:
        close_cursor(conn, cursor)



@app.route('/api/admin/releases/<int:release_id>/media/<kind>', methods=['POST'])
def admin_upload_release_media(release_id, kind):
    if kind not in MEDIA_KINDS:
        return jsonify({'success': False, 'error': 'Unsupported media kind'}), 404
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'file is required'}), 400
        upload = request.files['file']
        if not upload.filename:
            return jsonify({'success': False, 'error': 'filename is required'}), 400

        ensure_media_columns(cursor)
        cursor.execute("SELECT id, user_id FROM releases WHERE id = %s", (release_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Release not found'}), 404
        owner_id = row[1]

        local_column, file_id_column, telegram_type = MEDIA_KINDS[kind]
        local_path = save_upload_locally(upload, owner_id, release_id, kind)
        absolute_path = storage_absolute_path(local_path)

        file_id = None
        telegram_error = None
        try:
            file_id = upload_path_to_telegram(
                absolute_path,
                file_type=telegram_type,
                filename=safe_filename(upload.filename, absolute_path.name),
                mimetype=upload.mimetype or infer_mimetype(upload.filename),
            )
        except Exception as exc:
            telegram_error = str(exc)
            logger.error("Could not sync admin-uploaded %s for release %s to Telegram: %s", kind, release_id, exc)

        if file_id:
            cursor.execute(
                f"UPDATE releases SET {local_column} = %s, {file_id_column} = %s WHERE id = %s",
                (local_path, file_id, release_id),
            )
        else:
            cursor.execute(
                f"UPDATE releases SET {local_column} = %s WHERE id = %s",
                (local_path, release_id),
            )
        conn.commit()
        return jsonify({
            'success': True,
            'local_path': local_path,
            'file_id': file_id,
            'telegram_synced': bool(file_id),
            'telegram_error': telegram_error,
            'media_url': f"/api/releases/{release_id}/media/{kind}?user_id={owner_id}",
        })
    except Exception as e:
        logger.error("Error admin-uploading release media: %s", e)
        conn.rollback()
        return jsonify({'success': False, 'error': 'Could not upload media'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/releases/<int:release_id>/status', methods=['PUT'])
def admin_update_release_status(release_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        data = request.get_json() or {}
        status = (data.get('status') or '').strip()
        if not status:
            return jsonify({'success': False, 'error': 'Status is required'}), 400
        cursor.execute("UPDATE releases SET status=%s WHERE id=%s RETURNING id, user_id, release_name, status", (status, release_id))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return jsonify({'success': False, 'error': 'Release not found'}), 404
        conn.commit()
        return jsonify({'success': True, 'release': {'id': row[0], 'user_id': row[1], 'release_name': row[2], 'status': row[3]}})
    except Exception as e:
        conn.rollback()
        logger.error("Error updating release status: %s", e)
        return jsonify({'success': False, 'error': 'Could not update status'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/finance', methods=['GET'])
def admin_finance_summary():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        if not table_exists(cursor, 'orders'):
            return jsonify({'success': True, 'finance': {}})
        cursor.execute(
            """
            SELECT
              COALESCE(SUM(amount) FILTER (WHERE status='completed'),0),
              COALESCE(SUM(amount) FILTER (WHERE status='completed' AND created_date >= date_trunc('month', CURRENT_TIMESTAMP)),0),
              COALESCE(SUM(amount) FILTER (WHERE status='completed' AND created_date::date = CURRENT_DATE),0),
              COUNT(*) FILTER (WHERE status='pending'),
              COUNT(*) FILTER (WHERE status='completed')
            FROM orders
            """
        )
        row = cursor.fetchone()
        total = money_decimal(row[0])
        month = money_decimal(row[1])
        today = money_decimal(row[2])
        finance = {
            'total_revenue': money_float(total),
            'artem_share': money_float(total * Decimal('0.15')),
            'remaining_income': money_float(total * Decimal('0.85')),
            'monthly_revenue': money_float(month),
            'today_revenue': money_float(today),
            'pending_orders': int(row[3] or 0),
            'completed_orders': int(row[4] or 0),
        }
        return jsonify({'success': True, 'finance': finance})
    except Exception as e:
        logger.error("Error loading admin finance: %s", e)
        return jsonify({'success': False, 'error': 'Could not load finance'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/orders', methods=['GET'])
def admin_orders_list():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        if not table_exists(cursor, 'orders'):
            return jsonify({'success': True, 'orders': []})
        cursor.execute(
            """
            SELECT o.id, o.user_id, o.service_type, o.amount, o.status, o.created_date, o.description, l.name, l.tg
            FROM orders o LEFT JOIN label l ON l.telegram_id=o.user_id
            ORDER BY o.created_date DESC NULLS LAST, o.id DESC LIMIT 200
            """
        )
        orders = [{'id': r[0], 'user_id': r[1], 'service_type': r[2], 'amount': money_float(r[3]), 'status': r[4], 'created_date': r[5].isoformat() if r[5] else None, 'description': r[6], 'user_name': r[7], 'user_tg': r[8]} for r in cursor.fetchall()]
        return jsonify({'success': True, 'orders': orders})
    except Exception as e:
        logger.error("Error loading admin orders: %s", e)
        return jsonify({'success': False, 'error': 'Could not load orders'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/promos', methods=['GET', 'POST'])
def admin_promos_collection():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        ensure_promo_tables(cursor)
        if request.method == 'POST':
            data = request.get_json() or {}
            code = (data.get('code') or '').strip().upper()
            amount = money_decimal(data.get('amount'))
            discount = money_decimal(data.get('discount'))
            max_uses = data.get('max_uses') or None
            expires_at = data.get('expires_at') or None
            admin_user_id = data.get('admin_user_id') or request.args.get('admin_user_id', type=int) or 0
            if not code:
                return jsonify({'success': False, 'error': 'Code is required'}), 400
            if amount <= 0 and discount <= 0:
                return jsonify({'success': False, 'error': 'Set amount or discount'}), 400
            cursor.execute(
                """
                INSERT INTO promo_codes (code, amount, discount, created_by, max_uses, current_uses, expires_at, is_active)
                VALUES (%s,%s,%s,%s,%s,0,%s,TRUE)
                RETURNING id
                """,
                (code, amount, discount, int(admin_user_id), max_uses, expires_at or None),
            )
            promo_id = cursor.fetchone()[0]
            conn.commit()
            return jsonify({'success': True, 'promo_id': promo_id})
        cursor.execute(
            """
            SELECT id, code, amount, COALESCE(discount,0), COALESCE(is_active,TRUE), max_uses,
                   COALESCE(current_uses,0), expires_at, created_at, created_by
            FROM promo_codes ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 200
            """
        )
        promos = [{'id': r[0], 'code': r[1], 'amount': money_float(r[2]), 'discount': money_float(r[3]), 'is_active': bool(r[4]), 'max_uses': r[5], 'current_uses': int(r[6] or 0), 'expires_at': r[7].isoformat() if r[7] else None, 'created_at': r[8].isoformat() if r[8] else None, 'created_by': r[9]} for r in cursor.fetchall()]
        return jsonify({'success': True, 'promos': promos})
    except Exception as e:
        conn.rollback()
        logger.error("Error handling admin promos: %s", e)
        return jsonify({'success': False, 'error': 'Could not handle promos'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/promos/<int:promo_id>', methods=['DELETE'])
def admin_delete_promo(promo_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        ensure_promo_tables(cursor)
        cursor.execute("DELETE FROM promo_codes WHERE id=%s RETURNING id", (promo_id,))
        deleted = cursor.fetchone()
        conn.commit()
        return jsonify({'success': True, 'deleted': bool(deleted)})
    except Exception as e:
        conn.rollback()
        logger.error("Error deleting promo: %s", e)
        return jsonify({'success': False, 'error': 'Could not delete promo'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/reviews', methods=['GET'])
def admin_reviews_list():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        if not table_exists(cursor, 'reviews'):
            return jsonify({'success': True, 'reviews': []})
        cursor.execute(
            """
            SELECT r.id, r.user_id, r.service_type, r.rating, r.text, r.status, r.created_date, l.name, l.tg
            FROM reviews r LEFT JOIN label l ON l.telegram_id=r.user_id
            ORDER BY r.created_date DESC NULLS LAST, r.id DESC LIMIT 100
            """
        )
        reviews = [{'id': r[0], 'user_id': r[1], 'service_type': r[2], 'rating': r[3], 'text': r[4], 'status': r[5], 'created_date': r[6].isoformat() if r[6] else None, 'user_name': r[7], 'user_tg': r[8]} for r in cursor.fetchall()]
        return jsonify({'success': True, 'reviews': reviews})
    except Exception as e:
        logger.error("Error loading reviews: %s", e)
        return jsonify({'success': False, 'error': 'Could not load reviews'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/reviews/<int:review_id>/status', methods=['PUT'])
def admin_update_review_status(review_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        status = (request.get_json() or {}).get('status') or 'approved'
        cursor.execute("UPDATE reviews SET status=%s WHERE id=%s RETURNING id", (status, review_id))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        logger.error("Error updating review: %s", e)
        return jsonify({'success': False, 'error': 'Could not update review'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/reports', methods=['GET'])
def admin_reports_list():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        if not table_exists(cursor, 'report_requests'):
            return jsonify({'success': True, 'reports': []})
        cursor.execute(
            """
            SELECT rr.id, rr.user_id, rr.release_id, rr.release_type, rr.request_type, rr.status,
                   rr.admin_id, rr.created_at, rr.completed_at, rr.notes, l.name, l.tg, r.release_name
            FROM report_requests rr
            LEFT JOIN label l ON l.telegram_id = rr.user_id
            LEFT JOIN releases r ON r.id = rr.release_id
            ORDER BY rr.created_at DESC NULLS LAST, rr.id DESC LIMIT 150
            """
        )
        reports = [
            {
                'id': r[0], 'user_id': r[1], 'release_id': r[2], 'release_type': r[3], 'request_type': r[4],
                'status': r[5], 'admin_id': r[6], 'created_at': r[7].isoformat() if r[7] else None,
                'completed_at': r[8].isoformat() if r[8] else None, 'notes': r[9], 'user_name': r[10], 'user_tg': r[11],
                'release_name': r[12],
            }
            for r in cursor.fetchall()
        ]
        return jsonify({'success': True, 'reports': reports})
    except Exception as e:
        logger.error("Error loading reports: %s", e)
        return jsonify({'success': False, 'error': 'Could not load reports'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/reports/<int:report_id>/status', methods=['PUT'])
def admin_update_report_status(report_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        data = request.get_json() or {}
        status = data.get('status') or 'processing'
        notes = data.get('notes')
        completed_sql = ", completed_at = CURRENT_TIMESTAMP" if status in ('completed', 'rejected') else ""
        cursor.execute(
            f"UPDATE report_requests SET status=%s, admin_id=%s, notes=COALESCE(%s, notes){completed_sql} WHERE id=%s RETURNING id",
            (status, data.get('admin_user_id'), notes, report_id),
        )
        if not cursor.fetchone():
            conn.rollback()
            return jsonify({'success': False, 'error': 'Report not found'}), 404
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        logger.error("Error updating report: %s", e)
        return jsonify({'success': False, 'error': 'Could not update report'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/contracts', methods=['GET'])
def admin_contracts_list():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        if not table_exists(cursor, 'contracts'):
            return jsonify({'success': True, 'contracts': []})
        cursor.execute(
            """
            SELECT c.id, c.user_id, c.contract_number, c.contract_type, c.status, c.admin_id,
                   c.notes, c.created_at, c.completed_at, l.name, l.tg
            FROM contracts c LEFT JOIN label l ON l.telegram_id = c.user_id
            ORDER BY c.created_at DESC NULLS LAST, c.id DESC LIMIT 150
            """
        )
        contracts = [
            {
                'id': r[0], 'user_id': r[1], 'contract_number': r[2], 'contract_type': r[3], 'status': r[4],
                'admin_id': r[5], 'notes': r[6], 'created_at': r[7].isoformat() if r[7] else None,
                'completed_at': r[8].isoformat() if r[8] else None, 'user_name': r[9], 'user_tg': r[10],
            }
            for r in cursor.fetchall()
        ]
        return jsonify({'success': True, 'contracts': contracts})
    except Exception as e:
        logger.error("Error loading contracts: %s", e)
        return jsonify({'success': False, 'error': 'Could not load contracts'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/contracts/<int:contract_id>/status', methods=['PUT'])
def admin_update_contract_status(contract_id):
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        data = request.get_json() or {}
        status = data.get('status') or 'processing'
        notes = data.get('notes')
        completed_sql = ", completed_at = CURRENT_TIMESTAMP" if status in ('completed', 'rejected') else ""
        cursor.execute(
            f"UPDATE contracts SET status=%s, admin_id=%s, notes=COALESCE(%s, notes){completed_sql} WHERE id=%s RETURNING id",
            (status, data.get('admin_user_id'), notes, contract_id),
        )
        if not cursor.fetchone():
            conn.rollback()
            return jsonify({'success': False, 'error': 'Contract not found'}), 404
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        logger.error("Error updating contract: %s", e)
        return jsonify({'success': False, 'error': 'Could not update contract'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/support', methods=['GET'])
def admin_support_list():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        if not table_exists(cursor, 'support_requests'):
            return jsonify({'success': True, 'support': []})
        cursor.execute(
            """
            SELECT s.id, s.user_id, s.template_title, s.details, s.status, s.release_name, s.created_at, l.name, l.tg
            FROM support_requests s LEFT JOIN label l ON l.telegram_id=s.user_id
            ORDER BY s.created_at DESC NULLS LAST, s.id DESC LIMIT 100
            """
        )
        support = [{'id': r[0], 'user_id': r[1], 'template_title': r[2], 'details': r[3], 'status': r[4], 'release_name': r[5], 'created_at': r[6].isoformat() if r[6] else None, 'user_name': r[7], 'user_tg': r[8]} for r in cursor.fetchall()]
        return jsonify({'success': True, 'support': support})
    except Exception as e:
        logger.error("Error loading support: %s", e)
        return jsonify({'success': False, 'error': 'Could not load support'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/admin/broadcast', methods=['POST'])
def admin_broadcast():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        data = request.get_json() or {}
        message = (data.get('message') or '').strip()
        if len(message) < 2:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
        cursor.execute("SELECT telegram_id FROM label WHERE telegram_id IS NOT NULL ORDER BY id")
        recipients = [row[0] for row in cursor.fetchall()]
        sent = 0
        failed = 0
        if not TELEGRAM_BOT_TOKEN:
            return jsonify({'success': False, 'error': 'BOT_TOKEN is not configured'}), 503
        for chat_id in recipients:
            try:
                response = requests.post(f"{TELEGRAM_API_URL}/sendMessage", data={'chat_id': chat_id, 'text': message}, timeout=15)
                if response.ok and response.json().get('ok'):
                    sent += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        return jsonify({'success': True, 'sent': sent, 'failed': failed, 'total': len(recipients)})
    except Exception as e:
        logger.error("Error sending broadcast: %s", e)
        return jsonify({'success': False, 'error': 'Could not send broadcast'}), 500
    finally:
        close_cursor(conn, cursor)


PROFILE_UPDATE_FIELDS = {
    'artistName': 'name',
    'name': 'name',
    'channel': 'kanal',
    'kanal': 'kanal',
    'fio': 'fio',
    'email': 'email',
    'phone': 'phone',
}


DRAFT_CAMEL_TO_SNAKE = {
    'releaseType': 'release_type',
    'artistName': 'artist_name',
    'releaseName': 'release_name',
    'releaseDate': 'release_date',
    'performerName': 'performer_name',
    'musicAuthor': 'music_author',
    'videoshotUrl': 'videoshot_url',
    'previewStart': 'preview_start',
    'explicitContent': 'explicit_content',
    'yandexSoon': 'yandex_soon',
    'createLinks': 'create_links',
    'tiktokCommercial': 'tiktok_commercial',
    'tiktokFullVersion': 'tiktok_full_version',
}


def parse_draft_payload(data):
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            import json
            parsed = json.loads(data)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def normalize_draft_payload(data):
    data = parse_draft_payload(data)
    if not isinstance(data, dict):
        return {}
    normalized = dict(data)
    for camel, snake in DRAFT_CAMEL_TO_SNAKE.items():
        if camel in normalized and snake not in normalized:
            normalized[snake] = normalized[camel]
        if snake in normalized and camel not in normalized:
            normalized[camel] = normalized[snake]
    normalized.setdefault('releaseType', normalized.get('release_type') or 'Single')
    normalized.setdefault('release_type', normalized.get('releaseType') or 'Single')
    tracks = normalized.get('tracks')
    if isinstance(tracks, list):
        fixed_tracks = []
        for index, track in enumerate(tracks, 1):
            if not isinstance(track, dict):
                continue
            item = dict(track)
            meta = item.get('distributionMeta') if isinstance(item.get('distributionMeta'), dict) else {}
            for key, value in meta.items():
                item.setdefault(key, value)
            item.setdefault('track_name', item.get('trackName') or item.get('release_name') or f'Трек {index}')
            item.setdefault('trackName', item.get('track_name'))
            fixed_tracks.append(item)
        normalized['tracks'] = fixed_tracks
    return normalized


def table_exists(cursor, table_name):
    cached = TABLE_EXISTS_CACHE.get(table_name)
    if cached is not None:
        return cached
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
        """,
        (table_name,),
    )
    exists = bool(cursor.fetchone()[0])
    TABLE_EXISTS_CACHE[table_name] = exists
    return exists


def ensure_drafts_table(cursor):
    if 'drafts_table' in SCHEMA_READY:
        return
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS drafts (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            draft_type TEXT NOT NULL,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            current_step INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON drafts(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_updated ON drafts(user_id, updated_at DESC, id DESC)")
    TABLE_EXISTS_CACHE['drafts'] = True
    TABLE_COLUMNS_CACHE.pop('drafts', None)
    SCHEMA_READY.add('drafts_table')


def iso(value):
    return value.isoformat() if value else None


@app.route('/api/profile', methods=['PUT'])
def update_profile_api():
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id') or request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400

        updates = {}
        for input_field, column in PROFILE_UPDATE_FIELDS.items():
            if input_field in data:
                value = (data.get(input_field) or '').strip()
                if column == 'email' and value and not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", value):
                    return jsonify({'success': False, 'error': 'Неверный формат email'}), 400
                updates[column] = value
        if not updates:
            return jsonify({'success': False, 'error': 'Нет данных для сохранения'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()
        assignments = ', '.join(f"{column} = %s" for column in updates)
        cursor.execute(
            f"UPDATE label SET {assignments} WHERE telegram_id = %s",
            tuple(updates.values()) + (user_id,),
        )
        if cursor.rowcount < 1:
            conn.rollback()
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        conn.commit()
        user = load_user_by_telegram_id(cursor, user_id)
        return jsonify({'success': True, 'user': user})
    except Exception as e:
        logger.error("Error updating profile: %s", e)
        return jsonify({'success': False, 'error': 'Could not update profile'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/drafts', methods=['POST'])
def save_draft_api():
    conn = None
    try:
        payload = request.get_json() or {}
        user_id = payload.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400

        draft_id = payload.get('draft_id')
        draft_type = payload.get('draft_type') or 'release'
        data = normalize_draft_payload(payload.get('data') or {})
        current_step = int(payload.get('current_step') or 0)

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()
        ensure_drafts_table(cursor)

        if draft_id:
            cursor.execute(
                """
                UPDATE drafts
                SET draft_type = %s, data = %s, current_step = %s, updated_at = NOW()
                WHERE id = %s AND user_id = %s
                RETURNING id
                """,
                (draft_type, Json(data), current_step, draft_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return jsonify({'success': False, 'error': 'Draft not found'}), 404
            saved_id = row[0]
        else:
            cursor.execute(
                """
                INSERT INTO drafts (user_id, draft_type, data, current_step, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (user_id, draft_type, Json(data), current_step),
            )
            saved_id = cursor.fetchone()[0]

        conn.commit()
        return jsonify({'success': True, 'draft_id': saved_id})
    except Exception as e:
        logger.error("Error saving draft: %s", e)
        return jsonify({'success': False, 'error': 'Could not save draft'}), 500
    finally:
        if conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/drafts/<int:draft_id>', methods=['GET'])
def get_draft_api(draft_id):
    conn = None
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()
        ensure_drafts_table(cursor)
        cursor.execute(
            """
            SELECT id, draft_type, data, current_step, created_at, updated_at
            FROM drafts
            WHERE id = %s AND user_id = %s
            """,
            (draft_id, user_id),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Draft not found'}), 404

        return jsonify({
            'success': True,
            'draft': {
                'id': row[0],
                'draft_type': row[1],
                'data': normalize_draft_payload(row[2]) or {},
                'current_step': row[3],
                'created_at': iso(row[4]),
                'updated_at': iso(row[5]),
            }
        })
    except Exception as e:
        logger.error("Error loading draft: %s", e)
        return jsonify({'success': False, 'error': 'Could not load draft'}), 500
    finally:
        if conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/drafts/<int:draft_id>', methods=['DELETE'])
def delete_draft_api(draft_id):
    conn = None
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()
        ensure_drafts_table(cursor)
        cursor.execute("DELETE FROM drafts WHERE id = %s AND user_id = %s", (draft_id, user_id))
        conn.commit()
        return jsonify({'success': True, 'deleted': cursor.rowcount})
    except Exception as e:
        logger.error("Error deleting draft: %s", e)
        return jsonify({'success': False, 'error': 'Could not delete draft'}), 500
    finally:
        if conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/profile/dashboard', methods=['GET'])
def profile_dashboard_api():
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()
        user = load_user_by_telegram_id(cursor, user_id)
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404

        cursor.execute("""
            SELECT
                COALESCE(l.balance, 0) AS balance,
                COUNT(o.id) AS total_orders,
                COUNT(o.id) FILTER (WHERE o.status = 'completed') AS completed_orders,
                COALESCE(SUM(o.amount) FILTER (WHERE o.status = 'completed'), 0) AS completed_sum,
                COUNT(o.id) FILTER (WHERE o.status = 'pending') AS pending_orders,
                COUNT(o.id) FILTER (WHERE o.status = 'cancelled') AS cancelled_orders
            FROM label l
            LEFT JOIN orders o ON l.telegram_id = o.user_id
            WHERE l.telegram_id = %s
            GROUP BY l.telegram_id, l.balance
        """, (user_id,))
        finance_row = cursor.fetchone()
        finance = {
            'balance': float(finance_row[0] or 0) if finance_row else 0,
            'total_orders': int(finance_row[1] or 0) if finance_row else 0,
            'completed_orders': int(finance_row[2] or 0) if finance_row else 0,
            'completed_sum': float(finance_row[3] or 0) if finance_row else 0,
            'pending_orders': int(finance_row[4] or 0) if finance_row else 0,
            'cancelled_orders': int(finance_row[5] or 0) if finance_row else 0,
        }

        cursor.execute("SELECT COUNT(*) FROM releases WHERE user_id = %s", (user_id,))
        releases_count = int(cursor.fetchone()[0] or 0)

        drafts = []
        drafts_count = 0
        if table_exists(cursor, 'drafts'):
            cursor.execute("SELECT COUNT(*) FROM drafts WHERE user_id = %s", (user_id,))
            drafts_count = int(cursor.fetchone()[0] or 0)
            cursor.execute("""
                SELECT id, draft_type, data, current_step, created_at, updated_at
                FROM drafts
                WHERE user_id = %s
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 10
            """, (user_id,))
            drafts = [
                {
                    'id': row[0],
                    'draft_type': row[1],
                    'data': normalize_draft_payload(row[2]),
                    'current_step': row[3],
                    'created_at': iso(row[4]),
                    'updated_at': iso(row[5]),
                }
                for row in cursor.fetchall()
            ]

        orders = []
        if table_exists(cursor, 'orders'):
            cursor.execute("""
                SELECT id, service_type, amount, status, payment_id, created_date, updated_date, description, metadata
                FROM orders
                WHERE user_id = %s
                ORDER BY created_date DESC NULLS LAST
                LIMIT 10
            """, (user_id,))
            orders = [
                {
                    'id': row[0],
                    'service_type': row[1],
                    'amount': float(row[2] or 0),
                    'status': row[3],
                    'payment_id': row[4],
                    'created_date': iso(row[5]),
                    'updated_date': iso(row[6]),
                    'description': row[7],
                    'metadata': row[8] or {},
                }
                for row in cursor.fetchall()
            ]

        reports = []
        reports_count = 0
        if table_exists(cursor, 'report_requests'):
            cursor.execute("SELECT COUNT(*) FROM report_requests WHERE user_id = %s", (user_id,))
            reports_count = int(cursor.fetchone()[0] or 0)
            cursor.execute("""
                SELECT id, release_id, release_type, request_type, status, report_file_id, created_at, completed_at, notes
                FROM report_requests
                WHERE user_id = %s
                ORDER BY created_at DESC NULLS LAST
                LIMIT 10
            """, (user_id,))
            reports = [
                {
                    'id': row[0],
                    'release_id': row[1],
                    'release_type': row[2],
                    'request_type': row[3],
                    'status': row[4],
                    'report_file_id': row[5],
                    'created_at': iso(row[6]),
                    'completed_at': iso(row[7]),
                    'notes': row[8],
                }
                for row in cursor.fetchall()
            ]

        return jsonify({
            'success': True,
            'user': user,
            'finance': finance,
            'counts': {
                'releases': releases_count,
                'drafts': drafts_count,
                'orders': finance['total_orders'],
                'reports': reports_count,
            },
            'orders': orders,
            'drafts': drafts,
            'reports': reports,
        })
    except Exception as e:
        logger.error("Error loading profile dashboard: %s", e)
        return jsonify({'success': False, 'error': 'Could not load profile dashboard'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/reviews/random', methods=['GET'])
def get_random_review():
    """???????????????? ?????????????????? ??????????"""
    try:
        conn = get_pg_connection()
        if not conn:
            return jsonify({'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        cursor.execute('''
            SELECT l.name, r.service_type, r.rating, r.text, r.created_date
            FROM reviews r
            JOIN label l ON r.user_id = l.telegram_id
            WHERE r.status = %s
            ORDER BY RANDOM()
            LIMIT 1
        ''', ("approved",))

        review = cursor.fetchone()

        if not review:
            return jsonify({
                'success': True,
                'review': None,
                'message': '???????? ?????? ??????????????'
            })

        artist_name, service, rating, text, date = review
        review_data = {
            'artist_name': artist_name,
            'service_type': service,
            'rating': rating,
            'text': text,
            'created_date': date.isoformat() if date else None
        }

        return jsonify({
            'success': True,
            'review': review_data
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ???????????????????? ????????????: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/reviews/stats', methods=['GET'])
def get_reviews_stats():
    """???????????????? ???????????????????? ??????????????"""
    try:
        conn = get_pg_connection()
        if not conn:
            return jsonify({'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????? ???????????????????? ??????????????
        cursor.execute("SELECT COUNT(*) FROM reviews WHERE status = 'approved'")
        total_reviews = cursor.fetchone()[0]

        # ?????????????? ??????????????
        cursor.execute("SELECT AVG(rating) FROM reviews WHERE status = 'approved'")
        avg_rating = cursor.fetchone()[0]

        # ???????????????????? ???? ?????????? ??????????
        cursor.execute('''
            SELECT service_type, COUNT(*)
            FROM reviews
            WHERE status = 'approved'
            GROUP BY service_type
        ''')
        services_stats = dict(cursor.fetchall())

        return jsonify({
            'success': True,
            'stats': {
                'total_reviews': total_reviews,
                'average_rating': float(avg_rating) if avg_rating else 0,
                'services': services_stats
            }
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ????????????????????: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/auth/check', methods=['GET'])
def check_auth_status():
    """?????????????????? ???????????? ?????????????????????? ???? ????????????"""
    try:
        token = request.args.get('token')
        if not token:
            return jsonify({'success': False, 'error': '?????????? ???? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????? ?????????????????????? ???? ????????????
        cursor.execute("""
            SELECT ac.user_id, ac.used, l.tg, l.name
            FROM auth_codes ac
            LEFT JOIN label l ON ac.user_id = l.telegram_id
            WHERE ac.code = %s AND ac.expires_at > NOW()
        """, (token,))

        result = cursor.fetchone()

        if result:
            user_id, used, username, name = result
            if used:
                # ?????? ?????? ?????????????????????? - ?????????????????????? ??????????????
                return jsonify({
                    'success': True,
                    'user': {
                        'telegram_id': user_id,
                        'username': username,
                        'name': name,
                        'isAdmin': False  # ?????????? ???????????????? ???????????????? ????????????
                    }
                })
            else:
                # ?????? ?????? ???? ?????????????????????? - ????????????????
                return jsonify({'success': False, 'waiting': True})
        else:
            # ?????? ???? ???????????? ?????? ??????????
            return jsonify({'success': False, 'error': '???????????????? ?????? ???????????????? ??????????'})

    except Exception as e:
        logger.error(f"???????????? ?????? ???????????????? ?????????????? ??????????????????????: {e}")
        return jsonify({'success': False, 'error': '???????????????????? ???????????? ??????????????'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/auth/verify', methods=['POST'])
def verify_auth_code():
    """?????????????????? ?????? ??????????????????????"""
    try:
        data = request.get_json()
        if not data or 'code' not in data:
            return jsonify({'success': False, 'error': '?????? ???? ????????????'}), 400

        code = data['code'].strip()
        if not code:
            return jsonify({'success': False, 'error': '?????? ???? ?????????? ???????? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT user_id, expires_at, used
            FROM auth_codes
            WHERE code = %s
            """,
            (code,),
        )

        result = cursor.fetchone()

        logger.info("Auth code verification requested; found=%s", bool(result))

        if not result:
            logger.warning(f"No user found for code: {code}")
            return jsonify({'success': False, 'error': '???????????????? ??????'})

        user_id, expires_at, used = result

        # ??????????????????, ???? ?????????????????????? ???? ??????
        if used:
            return jsonify({'success': False, 'error': '?????? ?????? ??????????????????????'})

        # ??????????????????, ???? ?????????? ???? ??????
        if datetime.now() > expires_at:
            return jsonify({'success': False, 'error': '?????? ??????????'})

        # ???????????????? ?????? ?????? ????????????????????????????
        cursor.execute('''
            UPDATE auth_codes
            SET used = TRUE, used_at = CURRENT_TIMESTAMP
            WHERE code = %s
        ''', (code,))

        conn.commit()

        user_info = load_user_by_telegram_id(cursor, user_id)
        if not user_info:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404

        logger.info("Auth code verified for user_id=%s", user_id)

        return jsonify({'success': True, 'user': user_info})

    except Exception as e:
        logger.error(f"Error verifying auth code: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/auth/bot-link', methods=['GET'])
def auth_bot_link():
    return jsonify({
        'success': True,
        'bot_username': BOT_USERNAME,
        'url': f"https://t.me/{BOT_USERNAME}?start=webauth",
        'command': '/код',
        'fallback_command': '/webauth'
    })

# =================== PAYMENT MODULES ===================

# ?????????????????? ?????????????????????? ???????????? ?????? ????????????????
try:
    from yookassa import Configuration, Payment

    def load_yookassa_credentials():
        account_id = os.getenv("YOOKASSA_ACCOUNT_ID", "")
        secret_key = os.getenv("YOOKASSA_SECRET_KEY", "")
        if account_id and secret_key:
            return account_id, secret_key

        # Keep the site compatible with the existing bot until the payment
        # credentials are moved to shared environment variables.
        try:
            bot_label = Path(__file__).resolve().parents[1] / "bot0" / "label.py"
            source = bot_label.read_text(encoding="utf-8", errors="ignore")
            account_match = re.search(r'Configuration\.account_id\s*=\s*["\']([^"\']+)["\']', source)
            secret_match = re.search(r'Configuration\.secret_key\s*=\s*["\']([^"\']+)["\']', source)
            if account_match and secret_match:
                return account_match.group(1), secret_match.group(1)
        except Exception as e:
            logger.warning("Could not load YooKassa credentials from bot config: %s", e)
        return "", ""

    Configuration.account_id, Configuration.secret_key = load_yookassa_credentials()
    YOOKASSA_AVAILABLE = bool(Configuration.account_id and Configuration.secret_key)
except ImportError:
    YOOKASSA_AVAILABLE = False
    logger.warning("yookassa module not available. YooKassa payments will be disabled.")

# Crypto Bot Configuration
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")

# =================== BALANCE FUNCTIONS ===================

def change_user_balance(user_id, delta):
    """???????????????? ???????????? ????????????????????????"""
    conn = get_pg_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE label SET balance = COALESCE(balance,0) + %s WHERE telegram_id = %s', (delta, user_id))
        conn.commit()
        logger.info(f"Changed balance for user {user_id} by {delta}")
        return True
    except Exception as e:
        logger.error(f"Failed to change balance for {user_id} by {delta}: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

# =================== PAYMENT API ENDPOINTS ===================

@app.route('/api/payments/yookassa/create', methods=['POST'])
def create_yookassa_payment():
    """?????????????? ???????????? YooKassa"""
    if not YOOKASSA_AVAILABLE:
        return jsonify({'success': False, 'error': 'YooKassa ???? ????????????????'}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        amount = data.get('amount')
        user_id = data.get('user_id')  # ID ???????????????????????? ?????? ???????????????????? ??????????????
        description = data.get('description', 'Пополнение баланса TWAS Label')
        service_type = data.get('service_type', 'topup')

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Неверная сумма'}), 400

        if amount < 50 or amount > 100000:
            return jsonify({'success': False, 'error': 'Сумма должна быть от 50 до 100000 ₽'}), 400

        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя обязателен'}), 400

        user_id = int(user_id)
        return_url = data.get('return_url') or request.host_url.rstrip('/') + '/cabinet?payment=return'

        # ?????????????? ???????????? ?? YooKassa
        payment = Payment.create({
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description,
            "metadata": {
                "user_id": str(user_id),
                "service": service_type,
                "amount": str(amount)
            }
        })

        payment_url = payment.confirmation.confirmation_url
        payment_id = payment.id

        logger.info(f"Created YooKassa payment {payment_id}, amount: {amount}")

        # ?????????????????? ?????????? ?? ???????? ????????????
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????????????????????????? ?????????????? orders
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'orders'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            # ?????????????? ?????????????? orders
            cursor.execute("""
                CREATE TABLE orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    service_type VARCHAR(50) NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    payment_id VARCHAR(100) UNIQUE,
                    payment_system VARCHAR(20) DEFAULT 'yookassa',
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("?????????????? orders ??????????????")

        order_columns = get_table_columns(cursor, 'orders')
        order_payload = {
            'user_id': user_id,
            'service_type': service_type,
            'amount': amount,
            'status': 'pending',
            'payment_id': payment_id,
            'payment_system': 'yookassa',
            'created_date': datetime.now(),
            'description': description,
            'metadata': Json({
                'payment_system': 'yookassa',
                'return_url': return_url,
                'source': 'site',
            }),
        }
        insert_columns = [column for column in order_payload if column in order_columns]
        placeholders = ', '.join(['%s'] * len(insert_columns))
        cursor.execute(
            f"INSERT INTO orders ({', '.join(insert_columns)}) VALUES ({placeholders})",
            tuple(order_payload[column] for column in insert_columns),
        )

        conn.commit()

        return jsonify({
            'success': True,
            'payment_id': payment_id,
            'payment_url': payment_url,
            'amount': amount
        })

    except Exception as e:
        logger.error(f"Error creating YooKassa payment: {e}")
        return jsonify({'success': False, 'error': '???????????? ???????????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/payments/crypto/create', methods=['POST'])
def create_crypto_payment():
    """?????????????? ???????????? Crypto Bot"""
    try:
        import requests

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        amount = data.get('amount')
        user_id = data.get('user_id')  # ID ???????????????????????? ?????? ???????????????????? ??????????????
        description = data.get('description', '???????????????????? ??????????????')
        service_type = data.get('service_type', 'topup')

        if not amount or amount < 50:
            return jsonify({'success': False, 'error': '?????????????????????? ?????????? 50 ???'}), 400

        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400
        user_id = int(user_id)

        # ?????????????? ???????????? ?? Crypto Bot
        crypto_api_url = "https://pay.crypt.bot/api/createInvoice"

        payload = {
            "asset": "USDT",
            "amount": amount / 100,  # ???????????????????????? ?????????? ?? USDT ????????????????
            "description": description,
            "payload": f"{service_type}_{amount}"
        }

        headers = {
            "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
            "Content-Type": "application/json"
        }

        response = requests.post(crypto_api_url, json=payload, headers=headers)

        if response.status_code == 200:
            resp_data = response.json()
            if resp_data.get("ok"):
                invoice_id = resp_data["result"]["invoice_id"]
                pay_url = resp_data["result"]["pay_url"]

                # ?????????????????? ?????????? ?? ???????? ????????????
                conn = get_pg_connection()
                if not conn:
                    return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

                cursor = conn.cursor()

                # ?????????????????? ?????????????????????????? ?????????????? orders
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'orders'
                    )
                """)
                table_exists = cursor.fetchone()[0]

                if not table_exists:
                    # ?????????????? ?????????????? orders
                    cursor.execute("""
                        CREATE TABLE orders (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            service_type VARCHAR(50) NOT NULL,
                            amount DECIMAL(10,2) NOT NULL,
                            status VARCHAR(20) DEFAULT 'pending',
                            payment_id VARCHAR(100) UNIQUE,
                            payment_system VARCHAR(20) DEFAULT 'crypto',
                            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    logger.info("?????????????? orders ??????????????")

                cursor.execute(
                    '''INSERT INTO orders (user_id, service_type, amount, status, payment_id, payment_system, created_date)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                    (user_id, service_type, amount, 'pending', invoice_id, 'crypto', datetime.now())
                )

                conn.commit()

                return jsonify({
                    'success': True,
                    'payment_id': invoice_id,
                    'payment_url': pay_url,
                    'amount': amount
                })
            else:
                return jsonify({'success': False, 'error': '???????????? Crypto Bot API'}), 500
        else:
            return jsonify({'success': False, 'error': '???????????? ?????????? ?? Crypto Bot'}), 500

    except Exception as e:
        logger.error(f"Error creating Crypto Bot payment: {e}")
        return jsonify({'success': False, 'error': '???????????? ???????????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/payments/<payment_system>/status/<payment_id>', methods=['GET'])
def check_payment_status(payment_system, payment_id):
    """?????????????????? ???????????? ??????????????"""
    try:
        if payment_system == 'yookassa':
            if not YOOKASSA_AVAILABLE:
                return jsonify({'success': False, 'error': 'YooKassa ???? ????????????????'}), 503

            # ?????????????????? ???????????? ?? YooKassa
            payment = Payment.find_one(payment_id)
            if not payment:
                return jsonify({'success': False, 'error': '???????????? ???? ????????????'}), 404

            status = payment.status

            if status == 'succeeded':
                # ?????????????????? ???????????? ?? ???????? ???????????? ?? ?????????????????? ????????????
                conn = get_pg_connection()
                if conn:
                    cursor = conn.cursor()

                    # ???????????????? ???????????????????? ?? ????????????
                    cursor.execute(
                        'SELECT user_id, amount, status FROM orders WHERE payment_id = %s',
                        (payment_id,)
                    )
                    order_info = cursor.fetchone()

                    if order_info:
                        user_id, amount, current_status = order_info

                        # ??????????????????, ?????? ?????????? ?????? ???? ??????????????????
                        if current_status != 'completed':
                            # ?????????????????? ???????????? ????????????
                            cursor.execute(
                                'UPDATE orders SET status = %s WHERE payment_id = %s',
                                ('completed', payment_id)
                            )

                            # ?????????????????? ???????????? ????????????????????????
                            if user_id:
                                change_user_balance(user_id, amount)
                                logger.info(f"Payment {payment_id} processed: added {amount} to user {user_id}")

                            conn.commit()

                    cursor.close()
                    conn.close()

                return jsonify({
                    'success': True,
                    'status': 'completed',
                    'payment_id': payment_id
                })
            elif status == 'pending':
                return jsonify({
                    'success': True,
                    'status': 'pending',
                    'payment_id': payment_id
                })
            else:
                return jsonify({
                    'success': True,
                    'status': 'failed',
                    'payment_id': payment_id
                })

        elif payment_system == 'crypto':
            import requests

            # ?????????????????? ???????????? ?? Crypto Bot
            crypto_api_url = f"https://pay.crypt.bot/api/getInvoices"

            headers = {
                "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
                "Content-Type": "application/json"
            }

            params = {"invoice_ids": payment_id}
            response = requests.get(crypto_api_url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                if data.get("ok") and data["result"]["items"]:
                    invoice = data["result"]["items"][0]
                    status = invoice.get("status")

                    if status == "paid":
                        # ?????????????????? ???????????? ?? ???????? ???????????? ?? ?????????????????? ????????????
                        conn = get_pg_connection()
                        if conn:
                            cursor = conn.cursor()

                            # ???????????????? ???????????????????? ?? ????????????
                            cursor.execute(
                                'SELECT user_id, amount, status FROM orders WHERE payment_id = %s',
                                (payment_id,)
                            )
                            order_info = cursor.fetchone()

                            if order_info:
                                user_id, amount, current_status = order_info

                                # ??????????????????, ?????? ?????????? ?????? ???? ??????????????????
                                if current_status != 'completed':
                                    # ?????????????????? ???????????? ????????????
                                    cursor.execute(
                                        'UPDATE orders SET status = %s WHERE payment_id = %s',
                                        ('completed', payment_id)
                                    )

                                    # ?????????????????? ???????????? ????????????????????????
                                    if user_id:
                                        change_user_balance(user_id, amount)
                                        logger.info(f"Crypto payment {payment_id} processed: added {amount} to user {user_id}")

                                    conn.commit()

                            cursor.close()
                            conn.close()

                        return jsonify({
                            'success': True,
                            'status': 'completed',
                            'payment_id': payment_id
                        })
                    else:
                        return jsonify({
                            'success': True,
                            'status': 'pending',
                            'payment_id': payment_id
                        })
                else:
                    return jsonify({'success': False, 'error': '???????????? ???? ????????????'}), 404
            else:
                return jsonify({'success': False, 'error': '???????????? Crypto Bot API'}), 500
        else:
            return jsonify({'success': False, 'error': '?????????????????????? ?????????????????? ??????????????'}), 400

    except Exception as e:
        logger.error(f"Error checking payment status: {e}")
        return jsonify({'success': False, 'error': '???????????? ???????????????? ??????????????'}), 500

# =================== DISTRIBUTION API ===================

def get_admin_ids():
    """???????????????? ID ?????????????? ???? ???????? ????????????"""
    try:
        conn = get_pg_connection()
        if not conn:
            return [123456789]  # Fallback ID

        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM label WHERE COALESCE(admin, 0) <> 0 OR COALESCE(owner, FALSE) = TRUE")
        admin_ids = [row[0] for row in cursor.fetchall()]

        return admin_ids if admin_ids else [123456789]  # Fallback ID

    except Exception as e:
        logger.error(f"???????????? ?????????????????? ID ??????????????: {e}")
        return [123456789]  # Fallback ID
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

def send_admin_notification(message):
    """?????????????????? ?????????????????????? ???????????? ?? Telegram"""
    try:
        import requests

        # ???????????????? ID ?????????????? ???? ???????? ????????????
        admin_ids = get_admin_ids()
        logger.info(f"?????????????? ??????????????: {len(admin_ids)}, ID: {admin_ids}")

        # ?????????? ???????? (???????????? ???????? ?????? ????, ?????? ?? ???????????????? ????????)
        bot_token = TELEGRAM_BOT_TOKEN
        if not bot_token:
            logger.warning("BOT_TOKEN is not configured; admin notification skipped")
            return False

        for admin_id in admin_ids:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': admin_id,
                'text': message
            }

            logger.info(f"???????????????????? ?????????????????????? ???????????? {admin_id}")
            response = requests.post(url, data=data, timeout=10)
            logger.info(f"?????????? ???? Telegram API: {response.status_code}, {response.text}")

            if response.status_code == 200:
                logger.info(f"?????????????????????? ???????????????????? ???????????? {admin_id}")
            else:
                logger.error(f"???????????? ???????????????? ?????????????????????? ???????????? {admin_id}: {response.text}")

    except Exception as e:
        logger.error(f"???????????? ???????????????? ?????????????????????? ????????????: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

@app.route('/api/user/balance', methods=['GET'])
def get_user_balance():
    """???????????????? ???????????? ????????????????????????"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        cursor.execute('SELECT balance FROM label WHERE telegram_id = %s', (user_id,))
        result = cursor.fetchone()

        if result:
            balance = float(result[0]) if result[0] else 0.0
            return jsonify({'success': True, 'balance': balance})
        else:
            return jsonify({'success': False, 'error': '???????????????????????? ???? ????????????'}), 404

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ??????????????: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/user/balance', methods=['POST'])
def update_user_balance():
    """???????????????? ???????????? ????????????????????????"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        user_id = data.get('user_id')
        delta = data.get('delta')

        if not user_id or delta is None:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ?? ?????????????????? ?????????????? ??????????????????????'}), 400

        if change_user_balance(user_id, delta):
            return jsonify({'success': True, 'message': '???????????? ????????????????'})
        else:
            return jsonify({'success': False, 'error': '???????????? ???????????????????? ??????????????'}), 500

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ??????????????: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500

@app.route('/api/admin/users/<int:user_id>/levels', methods=['PUT'])
def update_user_levels(user_id):
    """???????????????? ???????????? ???????????????????????? (???????????? ?????? ??????????????)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        levels = data.get('levels', [])
        if not isinstance(levels, list):
            return jsonify({'success': False, 'error': '???????????? ???????????? ???????? ????????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ???????????? ????????????????????????
        cursor.execute('''
            UPDATE label
            SET levels = %s
            WHERE telegram_id = %s
        ''', (levels, user_id))

        if cursor.rowcount > 0:
            conn.commit()
            return jsonify({'success': True, 'message': '???????????? ??????????????????'})
        else:
            return jsonify({'success': False, 'error': '???????????????????????? ???? ????????????'}), 404

    except Exception as e:
        logger.error(f"???????????? ?????? ???????????????????? ??????????????: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

def verify_telegram_auth(data: dict, bot_token: str) -> bool:
    """Проверка подписи данных от Telegram Login Widget."""
    check_hash = data.pop('hash', None)
    if not check_hash or not bot_token:
        return False
    data_check_arr = sorted([f"{k}={v}" for k, v in data.items()])
    data_check_string = "\n".join(data_check_arr)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = _hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return _hmac.compare_digest(computed_hash, check_hash)


@app.route('/api/telegram_auth', methods=['GET'])
def telegram_auth_api():
    """Альтернативный маршрут для telegram_auth через /api/"""
    return telegram_auth()


@app.route('/api/me', methods=['GET'])
def api_me():
    """Minimal cabinet profile endpoint by Telegram ID."""
    return telegram_auth()


@app.route('/telegram_auth', methods=['GET'])
@limiter.limit("30 per minute")
def telegram_auth():
    """Аутентификация по Telegram — с проверкой подписи если есть hash."""
    try:
        auth_data = {k: v for k, v in request.args.items()}
        telegram_id = auth_data.get('id') or auth_data.get('tgid')

        if not telegram_id:
            return jsonify({'success': False, 'error': 'Telegram ID не указан'}), 400

        if 'hash' in auth_data:
            if not verify_telegram_auth(dict(auth_data), TELEGRAM_BOT_TOKEN):
                logger.warning("Invalid Telegram auth hash for id=%s", telegram_id)
                return jsonify({'success': False, 'error': 'Неверная подпись'}), 403

            auth_date = int(auth_data.get('auth_date', 0) or 0)
            if _time.time() - auth_date > 3600:
                return jsonify({'success': False, 'error': 'Данные авторизации устарели'}), 403

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к БД'}), 500

        cursor = conn.cursor()
        user_data = load_user_by_telegram_id(cursor, telegram_id)
        if not user_data:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404

        return jsonify({'success': True, 'user': user_data})

    except Exception as e:
        logger.error(f"Ошибка при аутентификации Telegram: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/user_releases', methods=['GET'])
def get_user_releases_legacy_alias():
    """Compatibility route for old frontend code that calls /user_releases."""
    return get_user_releases()


@app.route('/api/user_releases', methods=['GET'])
@limiter.limit("60 per minute")
def get_user_releases():
    """???????????????? ???????????? ????????????????????????"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400

        # ???????????????????????? user_id ?? ???????????????????? (????????????: 1398275867:1)
        # ?????????? ???????????? ???????????????? ?????????? ???? ??????????????????
        if ':' in str(user_id):
            user_id = str(user_id).split(':')[0]

        # ??????????????????, ?????? user_id - ?????? ??????????
        try:
            user_id = int(user_id)
        except ValueError:
            return jsonify({'success': False, 'error': '???????????????? ???????????? ID ????????????????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????????????????????????? ?????????????? releases
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'releases'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            return jsonify({
                'success': True,
                'releases': [],
                'message': '?????????????? ?????????????? ???? ??????????????'
            })

        ensure_media_columns(cursor)
        conn.commit()
        release_columns = get_table_columns(cursor, 'releases')
        upc_select = optional_column('upc_code', release_columns, "'пока что нет'")
        cover_file_select = optional_column('cover_file_id', release_columns, 'NULL')
        cover_local_select = optional_column('cover_local_path', release_columns, 'NULL')

        # ???????????????? ???????????? ???????????????????????? ???????????????? ???? ?????????????????????? user_id
        # ?????????????????? ?????????? ???? ???????????????? (is_track = True), ???????????????????? ???????????? ???????????????? ????????????
        cursor.execute("""
            SELECT id, release_type, artist_name, release_name, producer, genre,
                   release_date, status, created_at, performer_name, music_author,
                   explicit_content, preview_start, yandex_soon, create_links,
                   tiktok_commercial, tiktok_full_version, lyrics_file_id, is_album,
                   {upc_select}, {cover_file_select}, {cover_local_select}
            FROM releases
            WHERE user_id = %s AND (is_track IS NULL OR is_track = FALSE)
            ORDER BY created_at DESC
        """.format(
            upc_select=upc_select,
            cover_file_select=cover_file_select,
            cover_local_select=cover_local_select,
        ), (user_id,))

        releases = cursor.fetchall()

        releases_list = []
        for release in releases:
            (release_id, release_type, artist_name, release_name, producer, genre,
             release_date, status, created_at, performer_name, music_author,
             explicit_content, preview_start, yandex_soon, create_links,
             tiktok_commercial, tiktok_full_version, lyrics_file_id, is_album,
             upc_code, cover_file_id, cover_local_path) = release
            cover_url = f"/api/releases/{release_id}/media/cover-thumb?user_id={user_id}" if cover_local_path else (
                f"/api/files/telegram/{cover_file_id}" if cover_file_id else None
            )
            releases_list.append({
                'id': release_id,
                'release_type': release_type,
                'artist_name': artist_name,
                'release_name': release_name,
                'producer': producer,
                'genre': genre,
                'release_date': release_date.isoformat() if release_date else None,
                'status': status,
                'created_at': created_at.isoformat() if created_at else None,
                'performer_name': performer_name,
                'music_author': music_author,
                'explicit_content': explicit_content,
                'preview_start': preview_start,
                'yandex_soon': yandex_soon,
                'create_links': create_links,
                'tiktok_commercial': tiktok_commercial,
                'tiktok_full_version': tiktok_full_version,
                'lyrics_file_id': lyrics_file_id,
                'is_album': is_album,
                'upc_code': upc_code,
                'cover_url': cover_url,
            })

        return jsonify({
            'success': True,
            'releases': releases_list,
            'count': len(releases_list)
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ?????????????? ????????????????????????: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


def release_row_to_dict(row):
    (
        release_id, user_id, release_type, artist_name, release_name, producer,
        genre, cover_file_id, audio_file_id, release_date, performer_name,
        music_author, contract_file_id, videoshot_url, explicit_content,
        lyrics_file_id, preview_start, yandex_soon, create_links,
        tiktok_commercial, tiktok_full_version, status, created_at, is_album,
        is_track, album_id, upc_code, track_number, platform_links, release_link,
        audio_local_path, cover_local_path
    ) = row
    audio_url = f"/api/releases/{release_id}/media/audio?user_id={user_id}" if audio_local_path else (
        f"/api/files/telegram/{audio_file_id}" if audio_file_id else None
    )
    cover_url = f"/api/releases/{release_id}/media/cover-thumb?user_id={user_id}" if cover_local_path else (
        f"/api/files/telegram/{cover_file_id}" if cover_file_id else None
    )
    return {
        'id': release_id,
        'user_id': user_id,
        'release_type': release_type,
        'artist_name': artist_name,
        'release_name': release_name,
        'producer': producer,
        'genre': genre,
        'cover_file_id': cover_file_id,
        'cover_local_path': cover_local_path,
        'cover_url': cover_url,
        'audio_file_id': audio_file_id,
        'audio_local_path': audio_local_path,
        'audio_url': audio_url,
        'release_date': release_date.isoformat() if release_date else None,
        'performer_name': performer_name,
        'music_author': music_author,
        'contract_file_id': contract_file_id,
        'videoshot_url': videoshot_url,
        'explicit_content': explicit_content,
        'lyrics_file_id': lyrics_file_id,
        'preview_start': preview_start,
        'yandex_soon': yandex_soon,
        'create_links': create_links,
        'tiktok_commercial': tiktok_commercial,
        'tiktok_full_version': tiktok_full_version,
        'status': status,
        'created_at': created_at.isoformat() if created_at else None,
        'is_album': is_album,
        'is_track': is_track,
        'album_id': album_id,
        'upc_code': upc_code,
        'track_number': track_number,
        'platform_links': platform_links or {},
        'release_link': release_link,
    }


@app.route('/api/releases/<int:release_id>', methods=['GET'])
def get_release_detail_api(release_id):
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500

        cursor = conn.cursor()
        ensure_media_columns(cursor)
        conn.commit()
        cursor.execute("""
            SELECT id, user_id, release_type, artist_name, release_name, producer,
                   genre, cover_file_id, audio_file_id, release_date, performer_name,
                   music_author, contract_file_id, videoshot_url, explicit_content,
                   lyrics_file_id, preview_start, yandex_soon, create_links,
                   tiktok_commercial, tiktok_full_version, status, created_at,
                   is_album, is_track, album_id, upc_code, track_number,
                   platform_links, release_link, audio_local_path, cover_local_path
            FROM releases
            WHERE id = %s AND user_id = %s
        """, (release_id, user_id))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Release not found'}), 404

        release = release_row_to_dict(row)
        tracks = []
        parent_album = None

        if release.get('is_album'):
            cursor.execute("""
                SELECT id, user_id, release_type, artist_name, release_name, producer,
                       genre, cover_file_id, audio_file_id, release_date, performer_name,
                       music_author, contract_file_id, videoshot_url, explicit_content,
                       lyrics_file_id, preview_start, yandex_soon, create_links,
                       tiktok_commercial, tiktok_full_version, status, created_at,
                       is_album, is_track, album_id, upc_code, track_number,
                       platform_links, release_link, audio_local_path, cover_local_path
                FROM releases
                WHERE album_id = %s AND user_id = %s
                ORDER BY track_number NULLS LAST, id
            """, (release_id, user_id))
            tracks = [release_row_to_dict(track_row) for track_row in cursor.fetchall()]
        elif release.get('is_track') and release.get('album_id'):
            cursor.execute("""
                SELECT id, user_id, release_type, artist_name, release_name, producer,
                       genre, cover_file_id, audio_file_id, release_date, performer_name,
                       music_author, contract_file_id, videoshot_url, explicit_content,
                       lyrics_file_id, preview_start, yandex_soon, create_links,
                       tiktok_commercial, tiktok_full_version, status, created_at,
                       is_album, is_track, album_id, upc_code, track_number,
                       platform_links, release_link, audio_local_path, cover_local_path
                FROM releases
                WHERE id = %s AND user_id = %s
            """, (release['album_id'], user_id))
            album_row = cursor.fetchone()
            parent_album = release_row_to_dict(album_row) if album_row else None

        return jsonify({
            'success': True,
            'release': release,
            'tracks': tracks,
            'parent_album': parent_album,
            'kind': 'album' if release.get('is_album') else 'track' if release.get('is_track') else 'single',
        })

    except Exception as e:
        logger.error("Error loading release detail: %s", e)
        return jsonify({'success': False, 'error': 'Could not load release'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


MEDIA_KINDS = {
    'audio': ('audio_local_path', 'audio_file_id', 'audio'),
    'cover': ('cover_local_path', 'cover_file_id', 'photo'),
    'contract': ('contract_local_path', 'contract_file_id', 'document'),
    'lyrics': ('lyrics_local_path', 'lyrics_file_id', 'document'),
}


def get_owned_release_media(cursor, release_id, user_id):
    ensure_media_columns(cursor)
    cursor.execute("""
        SELECT id, user_id, release_name,
               audio_local_path, audio_file_id,
               cover_local_path, cover_file_id,
               contract_local_path, contract_file_id,
               lyrics_local_path, lyrics_file_id
        FROM releases
        WHERE id = %s AND user_id = %s
    """, (release_id, user_id))
    return cursor.fetchone()


@app.route('/api/releases/<int:release_id>/media/<kind>', methods=['GET'])
def get_release_media(release_id, kind):
    requested_kind = kind
    storage_kind = 'cover' if kind == 'cover-thumb' else kind
    if storage_kind not in MEDIA_KINDS:
        return jsonify({'success': False, 'error': 'Unsupported media kind'}), 404
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()
        row = get_owned_release_media(cursor, release_id, user_id)
        if not row:
            return jsonify({'success': False, 'error': 'Release not found'}), 404

        index_map = {
            'audio': (3, 4),
            'cover': (5, 6),
            'contract': (7, 8),
            'lyrics': (9, 10),
        }
        local_index, telegram_index = index_map[storage_kind]
        relative_path = row[local_index]
        telegram_file_id = row[telegram_index]
        if relative_path:
            if requested_kind == 'cover-thumb':
                thumb_relative = ensure_cover_thumbnail(relative_path)
                if thumb_relative:
                    thumb_path = storage_absolute_path(thumb_relative)
                    return send_file(
                        thumb_path,
                        mimetype='image/webp',
                        as_attachment=False,
                        conditional=True,
                        download_name=thumb_path.name,
                    )
            path = storage_absolute_path(relative_path)
            if path.exists():
                return send_file(
                    path,
                    mimetype=detect_media_mimetype(path, storage_kind),
                    as_attachment=False,
                    conditional=True,
                    download_name=path.name,
                )
            logger.warning(
                "Local %s media is missing for release %s (%s), trying Telegram file_id",
                storage_kind, release_id, relative_path,
            )

        if telegram_file_id:
            fallback_mimetypes = {
                'cover': 'image/jpeg',
                'audio': 'audio/mpeg',
                'contract': 'application/octet-stream',
                'lyrics': 'text/plain',
            }
            return proxy_telegram_file(telegram_file_id, fallback_mimetypes.get(storage_kind))

        return jsonify({'success': False, 'error': 'File is not attached'}), 404
    except Exception as e:
        logger.error("Error serving release media: %s", e)
        return jsonify({'success': False, 'error': 'Could not serve media'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/releases/<int:release_id>/media/<kind>', methods=['POST'])
def upload_release_media(release_id, kind):
    if kind not in MEDIA_KINDS:
        return jsonify({'success': False, 'error': 'Unsupported media kind'}), 404
    try:
        user_id = request.form.get('user_id', type=int) or request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'file is required'}), 400
        upload = request.files['file']
        if not upload.filename:
            return jsonify({'success': False, 'error': 'filename is required'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()
        row = get_owned_release_media(cursor, release_id, user_id)
        if not row:
            return jsonify({'success': False, 'error': 'Release not found'}), 404

        local_column, file_id_column, telegram_type = MEDIA_KINDS[kind]
        local_path = save_upload_locally(upload, user_id, release_id, kind)
        absolute_path = storage_absolute_path(local_path)

        file_id = None
        telegram_error = None
        try:
            file_id = upload_path_to_telegram(
                absolute_path,
                file_type=telegram_type,
                filename=safe_filename(upload.filename, absolute_path.name),
                mimetype=upload.mimetype or infer_mimetype(upload.filename),
            )
        except Exception as e:
            telegram_error = str(e)
            logger.error("Could not upload %s for release %s to Telegram: %s", kind, release_id, e)

        if file_id:
            cursor.execute(
                f"UPDATE releases SET {local_column} = %s, {file_id_column} = %s WHERE id = %s AND user_id = %s",
                (local_path, file_id, release_id, user_id),
            )
        else:
            cursor.execute(
                f"UPDATE releases SET {local_column} = %s WHERE id = %s AND user_id = %s",
                (local_path, release_id, user_id),
            )
        conn.commit()

        return jsonify({
            'success': True,
            'local_path': local_path,
            'file_id': file_id,
            'telegram_synced': bool(file_id),
            'telegram_error': telegram_error,
            'media_url': f"/api/releases/{release_id}/media/{kind}?user_id={user_id}",
        })
    except Exception as e:
        logger.error("Error uploading release media: %s", e)
        return jsonify({'success': False, 'error': 'Could not upload media'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()



def backfill_telegram_media(cursor, user_id=None, limit=25):
    """Best-effort migration of legacy Telegram file_id media into local storage."""
    ensure_media_columns(cursor)
    ensure_release_extra_columns(cursor)
    where_parts = []
    params = []
    for kind, (local_column, file_id_column, _telegram_type) in MEDIA_KINDS.items():
        where_parts.append(
            f"(NULLIF({file_id_column}, '') IS NOT NULL AND {local_column} IS NULL "
            f"AND NOT COALESCE((COALESCE(extra_metadata, '{{}}'::jsonb) -> 'media_migration_errors' ? '{kind}'), FALSE))"
        )
    where = "WHERE (" + " OR ".join(where_parts) + ")"
    if user_id:
        where += " AND user_id = %s"
        params.append(user_id)
    params.append(limit)
    cursor.execute(f"""
        SELECT id, user_id, release_name,
               audio_file_id, cover_file_id, contract_file_id, lyrics_file_id,
               COALESCE(extra_metadata, '{{}}'::jsonb)
        FROM releases
        {where}
        ORDER BY id
        LIMIT %s
    """, tuple(params))
    rows = cursor.fetchall()

    results = []
    updated = 0
    kind_positions = {
        'audio': 3,
        'cover': 4,
        'contract': 5,
        'lyrics': 6,
    }
    unrecoverable_markers = ('file is too big', 'invalid file_id')
    for row in rows:
        release_id, owner_id, release_name, audio_file_id, cover_file_id, contract_file_id, lyrics_file_id, extra_metadata = row
        row_values = row
        item = {'release_id': release_id, 'release_name': release_name}
        updates = {}
        metadata = dict(extra_metadata or {})
        migration_errors = dict(metadata.get('media_migration_errors') or {})
        metadata_changed = False
        for kind, (local_column, _file_id_column, _telegram_type) in MEDIA_KINDS.items():
            file_id = row_values[kind_positions[kind]]
            if not file_id:
                item[kind] = 'no file_id'
                continue
            if migration_errors.get(kind):
                item[kind] = f"skipped previously: {migration_errors[kind]}"
                continue
            try:
                local_path, error, status = download_telegram_file_to_storage(
                    file_id, owner_id, release_id, kind, f"release_{release_id}_{kind}"
                )
            except Exception as exc:
                local_path, error, status = None, str(exc), 500
            if local_path:
                updates[local_column] = local_path
                migration_errors.pop(kind, None)
                metadata_changed = True
                item[kind] = 'saved'
            else:
                message = error or str(status)
                item[kind] = f"skipped: {message}"
                if any(marker in message.lower() for marker in unrecoverable_markers):
                    migration_errors[kind] = message
                    metadata_changed = True
        if metadata_changed:
            if migration_errors:
                metadata['media_migration_errors'] = migration_errors
            else:
                metadata.pop('media_migration_errors', None)
            updates['extra_metadata'] = Json(metadata)
        if updates:
            assignments = ", ".join(f"{column} = %s" for column in updates)
            cursor.execute(
                f"UPDATE releases SET {assignments} WHERE id = %s",
                tuple(updates.values()) + (release_id,),
            )
            updated += 1
        results.append(item)
    return {'checked': len(rows), 'updated': updated, 'results': results}


@app.route('/api/media/backfill', methods=['POST'])
def backfill_media_from_telegram():
    """Best-effort migration: copy old Telegram file_id media into local storage."""
    try:
        limit = request.args.get('limit', 25, type=int)
        limit = max(1, min(limit, 200))
        user_id = request.args.get('user_id', type=int)

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor()
        result = backfill_telegram_media(cursor, user_id=user_id, limit=limit)
        conn.commit()
        return jsonify({'success': True, **result})
    except Exception as e:
        logger.error("Error backfilling media: %s", e)
        return jsonify({'success': False, 'error': 'Could not backfill media'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/admin/media/backfill', methods=['POST'])
def admin_backfill_media_from_telegram():
    conn, cursor, error = admin_request_context()
    if error:
        return error
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = max(1, min(limit, 200))
        user_id = request.args.get('user_id', type=int)
        result = backfill_telegram_media(cursor, user_id=user_id, limit=limit)
        conn.commit()
        return jsonify({'success': True, **result})
    except Exception as e:
        logger.error("Error admin-backfilling media: %s", e)
        conn.rollback()
        return jsonify({'success': False, 'error': 'Could not backfill media'}), 500
    finally:
        close_cursor(conn, cursor)


@app.route('/api/releases/recent', methods=['GET'])
def get_recent_releases():
    """Public feed for the cabinet home screen."""
    try:
        limit = request.args.get('limit', 8, type=int)
        limit = max(1, min(limit, 24))

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500

        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'releases'
            )
        """)
        if not cursor.fetchone()[0]:
            return jsonify({'success': True, 'releases': [], 'count': 0})

        release_columns = get_table_columns(cursor, 'releases')
        upc_select = optional_column('upc_code', release_columns, "'пока что нет'")
        cover_file_select = optional_column('cover_file_id', release_columns, 'NULL')
        cover_local_select = optional_column('cover_local_path', release_columns, 'NULL')
        music_author_select = optional_column('music_author', release_columns, 'NULL')

        cursor.execute("""
            SELECT id, user_id, release_type, artist_name, release_name, genre,
                   release_date, status, created_at, performer_name, {upc_select},
                   {cover_file_select}, {cover_local_select}, {music_author_select}
            FROM releases
            WHERE (is_track IS NULL OR is_track = FALSE)
              AND LOWER(TRIM(COALESCE(status, ''))) = 'отгружен на площадки'
            ORDER BY COALESCE(created_at, release_date::timestamp) DESC NULLS LAST
            LIMIT %s
        """.format(
            upc_select=upc_select,
            cover_file_select=cover_file_select,
            cover_local_select=cover_local_select,
            music_author_select=music_author_select,
        ), (limit,))

        releases = []
        for row in cursor.fetchall():
            (release_id, owner_id, release_type, artist_name, release_name, genre,
             release_date, status, created_at, performer_name, upc_code,
             cover_file_id, cover_local_path, music_author) = row
            cover_url = f"/api/releases/{release_id}/media/cover-thumb?user_id={owner_id}" if cover_local_path else (
                f"/api/files/telegram/{cover_file_id}" if cover_file_id else None
            )
            releases.append({
                'id': release_id,
                'release_type': release_type,
                'artist_name': artist_name,
                'release_name': release_name,
                'genre': genre,
                'release_date': release_date.isoformat() if release_date else None,
                'status': status,
                'created_at': created_at.isoformat() if created_at else None,
                'performer_name': performer_name,
                'music_author': music_author,
                'upc_code': upc_code,
                'cover_url': cover_url,
            })

        return jsonify({'success': True, 'releases': releases, 'count': len(releases)})

    except Exception as e:
        logger.error(f"Error loading recent releases: {e}")
        return jsonify({'success': False, 'error': 'Could not load releases'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/distribution/create', methods=['POST'])
def create_distribution():
    """?????????????? ?????????? ?????? ??????????????????????"""
    try:
        # ???????????????? ???????????? ???? ??????????
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400

        # ???????????????????????? ????????
        required_fields = {
            'releaseType': '?????? ????????????',
            'releaseName': '???????????????? ????????????',
            'artistName': '?????? ??????????????',
            'releaseDate': '???????? ????????????',
            'genre': '????????',
            'performerName': '??????????????????????',
            'musicAuthor': '?????????? ????????????'
        }

        release_data = {}
        for field, name in required_fields.items():
            value = request.form.get(field)
            if not value:
                return jsonify({'success': False, 'error': f'???????? "{name}" ??????????????????????'}), 400
            release_data[field] = value

        # ???????????????????????????? ????????
        release_data['producer'] = request.form.get('producer', '')
        release_data['trackCount'] = int(request.form.get('trackCount', 1))
        release_data['featuringArtists'] = request.form.get('featuringArtists', '')
        release_data['explicitContent'] = request.form.get('explicitContent') == 'true'
        release_data['yandexSoon'] = request.form.get('yandexSoon') == 'true'
        release_data['createLinks'] = request.form.get('createLinks') == 'true'
        release_data['tiktokCommercial'] = request.form.get('tiktokCommercial') == 'true'
        release_data['tiktokFullVersion'] = request.form.get('tiktokFullVersion') == 'true'

        preview_start = request.form.get('previewStart')
        release_data['previewStart'] = int(preview_start) if preview_start else None

        def resolve_file_id(form_key, upload_key, human_name, file_type):
            value = request.form.get(form_key)
            if value:
                return value
            upload = request.files.get(upload_key)
            if upload and upload.filename:
                try:
                    return upload_file_to_telegram(upload, file_type=file_type)
                except Exception as upload_error:
                    logger.error(f"Failed to upload {human_name} to Telegram: {upload_error}")
                    raise ValueError(f"???? ?????????????? ?????????????????? {human_name} ?? Telegram")
            raise ValueError(f'?????????????????? {human_name} ?????? ?????????????? file_id')

        try:
            cover_file_id = resolve_file_id('coverFileId', 'coverFile', '??????????????', 'photo')
            audio_file_id = resolve_file_id('audioFileId', 'audioFile', '?????????? ????????', 'audio')
            contract_file_id = resolve_file_id('contractFileId', 'contractFile', '??????????????', 'document')
            # ?????????? ?????????? ????????????????????????, ???? ???????? ???????? - ????????????????????????
            lyrics_file_id = None
            try:
                lyrics_file_id = resolve_file_id('lyricsFileId', 'lyricsFile', '?????????? ??????????', 'document')
            except ValueError:
                # ?????????? ?????????? ????????????????????????
                pass
        except ValueError as file_error:
            return jsonify({'success': False, 'error': str(file_error)}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????????????????????????? ?????????????? releases
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'releases'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            # ?????????????? ?????????????? releases (???????????????????? ????????)
            cursor.execute("""
                CREATE TABLE releases (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    release_type TEXT NOT NULL CHECK (release_type IN ('Single', 'EP', 'ALBUM', 'Maxi Single')),
                    artist_name TEXT NOT NULL,
                    release_name TEXT NOT NULL,
                    producer TEXT,
                    genre TEXT NOT NULL,
                    cover_file_id TEXT,
                    audio_file_id TEXT,
                    release_date DATE NOT NULL,
                    performer_name TEXT NOT NULL,
                    music_author TEXT NOT NULL,
                    contract_file_id TEXT,
                    videoshot_url TEXT,
                    explicit_content BOOLEAN NOT NULL DEFAULT FALSE,
                    lyrics_file_id TEXT,
                    preview_start INTEGER,
                    yandex_soon BOOLEAN DEFAULT FALSE,
                    create_links BOOLEAN DEFAULT FALSE,
                    tiktok_commercial BOOLEAN DEFAULT FALSE,
                    tiktok_full_version BOOLEAN DEFAULT FALSE,
                    status TEXT DEFAULT '????????????',
                    is_album BOOLEAN DEFAULT FALSE,
                    upc_code TEXT,
                    platform_links JSONB,
                    extra_metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("?????????????? releases ??????????????")

        # ?????????????????? ???????????? ??????????????
        cursor.execute('SELECT artist FROM label WHERE telegram_id = %s', (user_id,))
        user_result = cursor.fetchone()
        is_artist = user_result and user_result[0] == 1

        # ?????????????????? ??????????
        cursor.execute("""
            INSERT INTO releases (
                user_id, release_type, artist_name, release_name, producer, genre,
                cover_file_id, audio_file_id, release_date, performer_name,
                music_author, contract_file_id, lyrics_file_id, explicit_content,
                preview_start, yandex_soon, create_links,
                tiktok_commercial, tiktok_full_version, status, is_album
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id,
            release_data['releaseType'],
            release_data['artistName'],
            release_data['releaseName'],
            release_data['producer'],
            release_data['genre'],
            cover_file_id,
            audio_file_id,
            release_data['releaseDate'],
            release_data['performerName'],
            release_data['musicAuthor'],
            contract_file_id,
            lyrics_file_id,
            release_data['explicitContent'],
            release_data['previewStart'],
            release_data['yandexSoon'],
            release_data['createLinks'],
            release_data['tiktokCommercial'],
            release_data['tiktokFullVersion'],
            'pending',
            release_data['releaseType'] in ['ALBUM', 'EP', 'Maxi Single']
        ))

        release_id = cursor.fetchone()[0]
        conn.commit()

        logger.info(f"???????????? ?????????? ID {release_id} ?????? ???????????????????????? {user_id}")

        # ???????????????????? ?????????????????????? ???????????? (?? ?????? ???? ??????????????, ?????? ?? ?? ????????)
        try:
            # ???????????????? ???????????????????? ?? ???????????????????????? ?????? ??????????????????????
            cursor.execute('SELECT name, tg FROM label WHERE telegram_id = %s', (user_id,))
            user_info = cursor.fetchone()
            user_name = user_info[0] if user_info and user_info[0] else f"???????????????????????? {user_id}"
            user_username = user_info[1] if user_info and user_info[1] else "???? ????????????"

            # ?????????????????? ?????????????????? ?? ?????????????? ?????? ?? ???????? (?????? HTML ??????????)
            from datetime import datetime
            release_date_obj = datetime.strptime(release_data['releaseDate'], '%Y-%m-%d')
            notification_message = (
                "???? ?????????? ?????????? ???? ????????????????!\n\n"
                f"???? ????????????: {user_name} (@{user_username})\n"
                f"???? ????????????????: {release_data['releaseName']}\n"
                f"???? ???????? ????????????: {release_date_obj.strftime('%d.%m.%Y')}\n"
                f"???? ID ????????????: {release_id}"
            )

            send_admin_notification(notification_message)

        except Exception as e:
            logger.error(f"???????????? ???????????????? ?????????????????????? ????????????: {e}")

        # ???????????????????? ?????????????????????? ???????????????????????? (?? ?????? ???? ??????????????, ?????? ?? ?? ????????)
        try:
            release_name = release_data['releaseName']
            user_notification = f"??? ?????????? ??{release_name}?? ?????????????? ?????????????????? ???? ??????????????????!"

            # ???????????????????? ?????????????????????? ????????????????????????
            import requests
            bot_token = TELEGRAM_BOT_TOKEN
            if not bot_token:
                logger.warning("BOT_TOKEN is not configured; user notification skipped")
                raise ValueError("BOT_TOKEN is not configured")
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': user_id,
                'text': user_notification
            }

            response = requests.post(url, data=data)
            if response.status_code == 200:
                logger.info(f"?????????????????????? ???????????????????? ???????????????????????? {user_id}")
            else:
                logger.error(f"???????????? ???????????????? ?????????????????????? ???????????????????????? {user_id}: {response.text}")

        except Exception as e:
            logger.error(f"???????????? ???????????????? ?????????????????????? ????????????????????????: {e}")

        return jsonify({
            'success': True,
            'message': '?????????? ?????????????? ????????????',
            'release_id': release_id,
            'is_free': is_artist
        })

    except Exception as e:
        logger.error(f"Error creating distribution: {e}")
        return jsonify({'success': False, 'error': '???????????? ???????????????? ????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/', methods=['GET'])
def index():
    """Serve the web cabinet as the public home page."""
    return send_from_directory(os.path.dirname(__file__), 'cabinet.html')


@app.route('/api', methods=['GET'])
def api_index():
    """Return the API endpoint index."""
    return jsonify({
        'message': 'talk with a star // label API',
        'endpoints': {
            'GET /api/reviews': '???????????????? ???????????? (??????????????????: service_type, limit)',
            'GET /api/reviews/random': '???????????????? ?????????????????? ??????????',
            'GET /api/reviews/stats': '???????????????? ???????????????????? ??????????????',
            'GET /api/auth/check': '?????????????????? ???????????? ?????????????????????? ???? ????????????',
            'POST /api/auth/verify': '?????????????????? ?????? ?????????????????????? (????????????????: code)',
            'GET /api/user/balance': '???????????????? ???????????? ???????????????????????? (????????????????: user_id)',
            'POST /api/user/balance': '???????????????? ???????????? ????????????????????????',
            'PUT /api/admin/users/{user_id}/levels': '???????????????? ???????????? ????????????????????????',
            'GET /telegram_auth': '???????????????????????????? ???? Telegram ID (????????????????: tgid)',
            'GET /api/user_releases': '???????????????? ???????????? ???????????????????????? (????????????????: user_id)',
            'POST /api/payments/yookassa/create': '?????????????? ???????????? YooKassa',
            'POST /api/payments/crypto/create': '?????????????? ???????????? Crypto Bot',
            'GET /api/payments/{system}/status/{id}': '?????????????????? ???????????? ??????????????',
            'POST /api/distribution/create': '?????????????? ?????????? ?????? ??????????????????????',
            'POST /api/releases/create': '?????????????? ?????????? ?????? ????????????',
            'POST /api/albums/create': '?????????????? ???????????? ?? ??????????????',
            'GET /api/contracts/my': '???????????????? ?????????????????? ???????????????????????? (????????????????: user_id)',
            'GET /api/reports/my': '???????????????? ???????????? ???????????????????????? (????????????????: user_id)',
            'GET /api/promo/history': '???????????????? ?????????????? ???????????????????? (????????????????: user_id)',
            'POST /api/promo/activate': 'активация промокода',
            'GET /api/distribution/price': 'расчёт стоимости дистрибуции и баланса'
        }
    })


@app.route('/cabinet', methods=['GET'])
@app.route('/cabinet/', methods=['GET'])
@app.route('/release/new', methods=['GET'])
@app.route('/release/new/', methods=['GET'])
def cabinet():
    """Serve the web cabinet and dedicated release creation page."""
    return send_from_directory(os.path.dirname(__file__), 'cabinet.html')


@app.route('/assets/<path:filename>', methods=['GET'])
def assets(filename):
    """Serve site assets such as the logo image."""
    assets_dir = Path(__file__).resolve().parent / 'assets'
    return send_from_directory(assets_dir, filename)


@app.route('/api/orders', methods=['POST'])
def create_order():
    """?????????????? ?????????? ??????????????????????"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        # ???????????????? ???????????? ???? ??????????????
        user_id = data.get('user_id')
        release_type = data.get('releaseType')
        release_name = data.get('releaseName')
        artist_name = data.get('artistName')
        producer = data.get('producer')
        genre = data.get('genre')
        track_count = data.get('trackCount')
        release_date = data.get('releaseDate')

        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????? ?????????? ?? ?????????????? orders
        cursor.execute("""
            INSERT INTO orders (user_id, service_type, amount, status, created_date)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, f"?????????????????????? {release_type}", 100.00, 'pending', datetime.now()))

        order_id = cursor.fetchone()[0]

        conn.commit()

        return jsonify({
            'success': True,
            'order_id': order_id,
            'message': '?????????? ???????????? ??????????????'
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ???????????????? ????????????: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/releases/create', methods=['POST'])
def create_release():
    """?????????????? ?????????? ?????? ????????????"""
    conn = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        user_id = data.get('user_id')
        release_type = data.get('releaseType', 'Single')
        release_name = data.get('releaseName', '')
        artist_name = data.get('artistName', '')
        producer = data.get('producer', '')
        genre = data.get('genre', '')
        release_date = data.get('releaseDate', '')
        # ???????????????????????????? ??????????????????, ?????????????? ???????? ?????????? ??????????????????
        cover_file_id = data.get('coverFileId') or data.get('cover_file_id')
        audio_file_id = data.get('audioFileId') or data.get('audio_file_id')
        contract_file_id = data.get('contractFileId') or data.get('contract_file_id')
        lyrics_file_id = data.get('lyricsFileId') or data.get('lyrics_file_id')
        videoshot_url = data.get('videoshotUrl') or data.get('videoshot_url')
        preview_start = data.get('previewStart') or data.get('preview_start')
        explicit_content = bool(data.get('explicitContent', False))
        yandex_soon = bool(data.get('yandexSoon', False))
        create_links = bool(data.get('createLinks', False))
        tiktok_commercial = bool(data.get('tiktokCommercial', False))
        tiktok_full_version = bool(data.get('tiktokFullVersion', False))
        performer_name = data.get('performerName') or artist_name
        music_author = data.get('musicAuthor') or artist_name

        # ???????????????? ???????????????????? ???????????? ?????? ??????????????
        logger.info(f"???????????????? ????????????: user_id={user_id}, release_type={release_type}, release_name={release_name}, artist_name={artist_name}, producer={producer}, genre={genre}, release_date={release_date}")

        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400
        user_id = int(user_id)
        release_type = normalize_release_type(release_type)

        # ?????????????????? ???????????????????????? ????????
        if not release_name:
            return jsonify({'success': False, 'error': '???????????????? ???????????? ???? ??????????????'}), 400
        if not artist_name:
            return jsonify({'success': False, 'error': '?????? ?????????????????????? ???? ??????????????'}), 400
        if not release_date:
            return jsonify({'success': False, 'error': '???????? ???????????? ???? ??????????????'}), 400

        # ?????????????????? ?? ???????????????????? ???????????? ????????
        try:
            from datetime import datetime
            # ???????? ???????? ?????????? ???????????? "0003-03-31", ???????????????? ???? ?????????????? ????????
            if release_date.startswith('0003-'):
                release_date = datetime.now().strftime('%Y-%m-%d')
                logger.info(f"???????????????????? ???????? ???????????? ????: {release_date}")

            # ??????????????????, ?????? ???????? ??????????????????
            datetime.strptime(release_date, '%Y-%m-%d')
        except ValueError as e:
            logger.error(f"???????????? ?????????????? ????????: {e}")
            return jsonify({'success': False, 'error': '???????????????? ???????????? ???????? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????????????????????????? ?????????????? releases
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'releases'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            # ?????????????? ?????????????? releases
            cursor.execute("""
                CREATE TABLE releases (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    release_type TEXT NOT NULL CHECK (release_type IN ('Single', 'EP', 'ALBUM', 'Maxi Single', 'TRACK')),
                    artist_name TEXT NOT NULL,
                    release_name TEXT NOT NULL,
                    producer TEXT,
                    genre TEXT NOT NULL,
                    cover_file_id TEXT,
                    audio_file_id TEXT,
                    release_date DATE NOT NULL,
                    performer_name TEXT NOT NULL,
                    music_author TEXT NOT NULL,
                    contract_file_id TEXT,
                    videoshot_url TEXT,
                    explicit_content BOOLEAN NOT NULL DEFAULT FALSE,
                    lyrics_file_id TEXT,
                    preview_start INTEGER,
                    yandex_soon BOOLEAN DEFAULT FALSE,
                    create_links BOOLEAN DEFAULT FALSE,
                    tiktok_commercial BOOLEAN DEFAULT FALSE,
                    tiktok_full_version BOOLEAN DEFAULT FALSE,
                    status TEXT DEFAULT 'pending',
                    is_album BOOLEAN DEFAULT FALSE,
                    is_track BOOLEAN DEFAULT FALSE,
                    album_id INTEGER,
                    track_number INTEGER,
                    upc_code TEXT,
                    platform_links JSONB,
                    extra_metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("?????????????? releases ?????????????? ?? ?????????????????????????????? ???????????? ?????? ????????????")

        ensure_release_extra_columns(cursor)

        logger.info(f"???????????????? ????????????: user_id={user_id}, release_type={release_type}, release_name={release_name}, artist_name={artist_name}")
        charge_result = charge_distribution(cursor, user_id, release_type, release_name)
        if not charge_result.get('success'):
            conn.rollback()
            return jsonify({
                'success': False,
                'error': charge_result.get('error') or 'Недостаточно средств на балансе',
                'payment': charge_result.get('payment'),
            }), 402

        cursor.execute("""
            INSERT INTO releases (user_id, release_type, artist_name, release_name,
                                producer, genre, cover_file_id, audio_file_id, release_date,
                                performer_name, music_author, contract_file_id, videoshot_url,
                                explicit_content, lyrics_file_id, preview_start, yandex_soon,
                                create_links, tiktok_commercial, tiktok_full_version, status,
                                is_album, is_track, upc_code, platform_links, extra_metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id,
            release_type,
            artist_name,
            release_name,
            producer,
            genre,
            cover_file_id,
            audio_file_id,
            release_date,
            performer_name,
            music_author,
            contract_file_id,
            videoshot_url,
            explicit_content,
            lyrics_file_id,
            preview_start,
            yandex_soon,
            create_links,
            tiktok_commercial,
            tiktok_full_version,
            'pending',
            False,
            False,
            data.get('upc') or data.get('distributionMeta', {}).get('upc') or 'пока что нет',
            None,
            Json(data.get('distributionMeta') or {}),
            datetime.now()
        ))

        release_id = cursor.fetchone()[0]
        conn.commit()

        return jsonify({
            'success': True,
            'release_id': release_id,
            'payment': charge_result.get('payment'),
            'order_id': charge_result.get('order_id'),
            'balance_after': charge_result.get('balance_after'),
            'message': '?????????? ???????????? ??????????????'
        })

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"???????????? ?????? ???????????????? ????????????: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/albums/create', methods=['POST'])
def create_album():
    """?????????????? ???????????? ?? ??????????????"""
    conn = None
    try:
        from datetime import datetime

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        user_id = data.get('user_id')
        release_type = data.get('releaseType')  # ALBUM ?????? EP
        release_name = data.get('releaseName')
        artist_name = data.get('artistName')
        producer = data.get('producer')
        genre = data.get('genre')
        release_date = data.get('releaseDate')
        tracks = data.get('tracks', [])
        # ???????????????????????????? media-???????? ?????? ??????????????
        album_cover_id = data.get('coverFileId') or data.get('cover_file_id')
        album_audio_id = data.get('audioFileId') or data.get('audio_file_id')
        album_contract_id = data.get('contractFileId') or data.get('contract_file_id')
        performer_name = data.get('performerName') or artist_name
        music_author = data.get('musicAuthor') or artist_name

        logger.info(f"???????????????? ??????????????: user_id={user_id}, release_type={release_type}, release_name={release_name}, artist_name={artist_name}, tracks_count={len(tracks)}")

        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400
        user_id = int(user_id)
        release_type = normalize_release_type(release_type)

        if not release_name:
            return jsonify({'success': False, 'error': '???????????????? ?????????????? ???? ??????????????'}), 400

        if not artist_name:
            return jsonify({'success': False, 'error': '?????? ?????????????????????? ???? ??????????????'}), 400

        if not release_date:
            return jsonify({'success': False, 'error': '???????? ???????????? ???? ??????????????'}), 400

        if not tracks:
            return jsonify({'success': False, 'error': '?????????? ???? ??????????????'}), 400

        # ?????????????????? ?? ???????????????????? ???????????? ????????
        try:
            # ???????? ???????? ?????????? ???????????? "0002-02-22", ???????????????? ???? ?????????????? ????????
            if release_date.startswith('0002-'):
                release_date = datetime.now().strftime('%Y-%m-%d')
                logger.info(f"???????????????????? ???????? ???????????? ????: {release_date}")

            # ??????????????????, ?????? ???????? ??????????????????
            datetime.strptime(release_date, '%Y-%m-%d')
        except ValueError as e:
            logger.error(f"???????????? ?????????????? ????????: {e}")
            return jsonify({'success': False, 'error': '???????????????? ???????????? ???????? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????????????????????????? ?????????????? releases
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'releases'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            # ?????????????? ?????????????? releases
            cursor.execute("""
                CREATE TABLE releases (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    release_type TEXT NOT NULL CHECK (release_type IN ('Single', 'EP', 'ALBUM', 'Maxi Single', 'TRACK')),
                    artist_name TEXT NOT NULL,
                    release_name TEXT NOT NULL,
                    producer TEXT,
                    genre TEXT NOT NULL,
                    cover_file_id TEXT,
                    audio_file_id TEXT,
                    release_date DATE NOT NULL,
                    performer_name TEXT NOT NULL,
                    music_author TEXT NOT NULL,
                    contract_file_id TEXT,
                    videoshot_url TEXT,
                    explicit_content BOOLEAN NOT NULL DEFAULT FALSE,
                    lyrics_file_id TEXT,
                    preview_start INTEGER,
                    yandex_soon BOOLEAN DEFAULT FALSE,
                    create_links BOOLEAN DEFAULT FALSE,
                    tiktok_commercial BOOLEAN DEFAULT FALSE,
                    tiktok_full_version BOOLEAN DEFAULT FALSE,
                    status TEXT DEFAULT 'pending',
                    is_album BOOLEAN DEFAULT FALSE,
                    is_track BOOLEAN DEFAULT FALSE,
                    album_id INTEGER,
                    track_number INTEGER,
                    upc_code TEXT,
                    platform_links JSONB,
                    extra_metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("?????????????? releases ?????????????? ?? ?????????????????????????????? ???????????? ?????? ????????????")

        ensure_release_extra_columns(cursor)
        charge_result = charge_distribution(cursor, user_id, release_type, release_name)
        if not charge_result.get('success'):
            conn.rollback()
            return jsonify({
                'success': False,
                'error': charge_result.get('error') or 'Недостаточно средств на балансе',
                'payment': charge_result.get('payment'),
            }), 402

        # ?????????????? ???????????? ??????????????
        cursor.execute("""
            INSERT INTO releases (user_id, release_type, artist_name, release_name,
                                producer, genre, cover_file_id, audio_file_id, release_date,
                                performer_name, music_author, contract_file_id, videoshot_url,
                                explicit_content, lyrics_file_id, preview_start, yandex_soon,
                                create_links, tiktok_commercial, tiktok_full_version, status,
                                is_album, upc_code, platform_links, extra_metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id, release_type, artist_name, release_name, producer,
            genre, album_cover_id, album_audio_id, release_date,
            performer_name, music_author, album_contract_id, None,
            False, None, None, False,
            False, False, False, 'pending', True,
            data.get('upc') or data.get('distributionMeta', {}).get('upc'),
            None,
            Json(data.get('distributionMeta') or {}),
            datetime.now()
        ))

        album_id = cursor.fetchone()[0]

        # ?????????????? ???????????? ????????????
        track_ids = []
        for i, track in enumerate(tracks, 1):
            t_audio = track.get('audioFileId') or track.get('audio_file_id')
            t_contract = track.get('contractFileId') or track.get('contract_file_id')
            t_cover = track.get('coverFileId') or track.get('cover_file_id')
            t_lyrics = track.get('lyricsFileId') or track.get('lyrics_file_id')
            cursor.execute("""
                INSERT INTO releases (user_id, release_type, artist_name, release_name,
                                    producer, genre, cover_file_id, audio_file_id, release_date,
                                    performer_name, music_author, contract_file_id, videoshot_url,
                                    explicit_content, lyrics_file_id, preview_start, yandex_soon,
                                    create_links, tiktok_commercial, tiktok_full_version, status,
                                    is_track, album_id, track_number, upc_code, platform_links, extra_metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                user_id, 'TRACK', artist_name, track.get('track_name'),
                track.get('producer'), track.get('genre'), t_cover, t_audio, release_date,
                performer_name, music_author, t_contract, None, False, t_lyrics, None,
                False, False, False, False, 'pending', True, album_id, i,
                None,
                None,
                Json(track.get('distributionMeta') or {}),
                datetime.now()
            ))
            track_ids.append(cursor.fetchone()[0])

        conn.commit()

        # ???????????????????? ?????????????????????? ??????????????
        try:
            # ???????????????? ???????????????????? ?? ????????????????????????
            cursor.execute('SELECT name, tg, artist FROM label WHERE telegram_id = %s', (user_id,))
            user_info = cursor.fetchone()
            user_name = user_info[0] if user_info and user_info[0] else f"???????????????????????? {user_id}"
            user_username = user_info[1] if user_info and user_info[1] else "???? ????????????"
            is_artist = user_info and len(user_info) > 2 and user_info[2] == 1

            logger.info(f"???????????????? ?????????????????????? ?????? ??????????????: {release_name}")

            # ?????????????????? ?????????????????????? ?? ?????????????? ?????? ?? ???????? (?????? HTML ??????????, ???????????? ???????????? ?? ??????????)
            notification_message = "???? ?????????? ?????????? ???? ????????????????!\n\n"
            notification_message += f"???? ????????????: {user_name} (@{user_username})\n"
            notification_message += f"???? ????????????????: {release_name}\n"

            if producer:
                notification_message += f"???? ????????????????: {producer}\n"

            notification_message += f"???? ???????????? (??????????????????????): {artist_name}\n"
            notification_message += f"???? ??????????????????????: {performer_name}\n"
            notification_message += f"?????? ?????????? ????????????: {music_author}\n"
            notification_message += f"???? ??????: {release_type}\n"
            notification_message += f"???? ????????: {genre}\n"
            notification_message += f"???? ???????? ????????????: {release_date}\n"

            notification_message += f"\n???? ???????????????????? ????????????: {len(tracks)}\n"
            notification_message += "??????????:\n"
            for i, track in enumerate(tracks, 1):
                track_name = track.get('track_name', '?????? ????????????????')
                track_producer = track.get('producer', '????????????????????')
                notification_message += f"{i}. {track_name} (prod. {track_producer})\n"

            notification_message += f"\n???? ID ????????????: {album_id}\n"
            notification_message += f"???? ??????????????????: {'??????????????????' if is_artist else '????????????'}\n"

            logger.info(f"???????????????????? ??????????????????????: {notification_message}")
            send_admin_notification(notification_message)

        except Exception as e:
            logger.error(f"???????????? ???????????????? ?????????????????????? ????????????: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

        return jsonify({
            'success': True,
            'album_id': album_id,
            'track_ids': track_ids,
            'tracks_count': len(tracks),
            'payment': charge_result.get('payment'),
            'order_id': charge_result.get('order_id'),
            'balance_after': charge_result.get('balance_after'),
            'message': '???????????? ???????????? ??????????????'
        })

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"???????????? ?????? ???????????????? ??????????????: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/contracts/my', methods=['GET'])
def get_my_contracts():
    """???????????????? ?????????????????? ????????????????????????"""
    conn = None
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400

        # ???????? ???????????????????? ???????????? ????????????, ?????? ?????? ?????????????? contracts ?????????? ???? ????????????????????????
        return jsonify({
            'success': True,
            'contracts': [],
            'count': 0,
            'message': '?????????????? ???????????????????? ?? ????????????????????'
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ????????????????????: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.route('/api/reports/my', methods=['GET'])
def get_my_reports():
    """???????????????? ???????????? ????????????????????????"""
    conn = None
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????????????????????????? ?????????????? report_requests
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'report_requests'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            return jsonify({
                'success': True,
                'reports': [],
                'count': 0,
                'message': '?????????????? ?????????????? ???? ??????????????'
            })

        # ???????????????? ???????????? ????????????????????????
        cursor.execute("""
            SELECT id, request_type, status, report_file_id,
                   created_at, completed_at, notes
            FROM report_requests
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))

        reports = cursor.fetchall()

        reports_list = []
        for report in reports:
            report_id, request_type, status, report_file_id, created_at, completed_at, notes = report
            reports_list.append({
                'id': report_id,
                'request_type': request_type or 'admin_sent',
                'status': status,
                'file_id': report_file_id,
                'created_at': created_at.isoformat() if created_at else None,
                'completed_at': completed_at.isoformat() if completed_at else None,
                'notes': notes
            })

        return jsonify({
            'success': True,
            'reports': reports_list,
            'count': len(reports_list)
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ??????????????: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/promo/history', methods=['GET'])
def get_promo_history():
    """???????????????? ?????????????? ???????????????????? ????????????????????????"""
    conn = None
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400
        user_id = int(user_id)
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'База данных недоступна'}), 500
        cursor = conn.cursor()
        ensure_promo_tables(cursor)

        cursor.execute(
            """
            SELECT p.code, p.amount, COALESCE(p.discount, 0), u.used_at
            FROM promo_code_usage u
            JOIN promo_codes p ON p.id = u.promo_code_id
            WHERE u.user_id = %s
            ORDER BY u.used_at DESC
            LIMIT 30
            """,
            (user_id,),
        )
        history = [
            {
                'code': row[0],
                'type': 'balance' if money_decimal(row[1]) > 0 else 'discount',
                'amount': money_float(row[1]),
                'discount': money_float(row[2]),
                'used_at': row[3].isoformat() if row[3] else None,
            }
            for row in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT p.id, p.code, COALESCE(p.discount, 0), udp.created_at, p.expires_at
            FROM user_discount_promos udp
            JOIN promo_codes p ON p.id = udp.promo_code_id
            WHERE udp.user_id = %s
              AND COALESCE(p.discount, 0) > 0
              AND (p.expires_at IS NULL OR p.expires_at >= CURRENT_TIMESTAMP)
            ORDER BY COALESCE(p.discount, 0) DESC, udp.created_at ASC
            """,
            (user_id,),
        )
        active_discounts = [
            {
                'promo_id': row[0],
                'code': row[1],
                'discount': money_float(row[2]),
                'created_at': row[3].isoformat() if row[3] else None,
                'expires_at': row[4].isoformat() if row[4] else None,
            }
            for row in cursor.fetchall()
        ]

        return jsonify({
            'success': True,
            'history': history,
            'active_discounts': active_discounts,
            'count': len(history),
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ?????????????????? ?????????????? ????????????????????: {e}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/promo/activate', methods=['POST'])
def activate_promo_api():
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        code = data.get('code')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя обязателен'}), 400
        payload, status = activate_promo_for_site(int(user_id), code)
        return jsonify(payload), status
    except Exception as e:
        logger.error("Could not activate promo from site: %s", e)
        return jsonify({'success': False, 'error': 'Ошибка активации промокода'}), 500


@app.route('/api/distribution/price', methods=['GET'])
def get_distribution_price():
    conn = None
    try:
        user_id = request.args.get('user_id')
        release_type = request.args.get('release_type') or request.args.get('releaseType') or 'Single'
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя обязателен'}), 400
        user_id = int(user_id)
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'База данных недоступна'}), 500
        cursor = conn.cursor()
        ensure_promo_tables(cursor)
        ensure_label_user(cursor, user_id)
        payment = calculate_distribution_payment(cursor, user_id, release_type)
        conn.commit()
        return jsonify({'success': True, 'payment': public_payment(payment)})
    except Exception as e:
        logger.error("Could not calculate distribution price: %s", e)
        return jsonify({'success': False, 'error': 'Ошибка расчёта стоимости'}), 500
    finally:
        if conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/design/order', methods=['POST'])
def create_design_order():
    """?????????????? ?????????? ?????????????? (??????????????, motion, videoshot)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        user_id = data.get('user_id')
        service = data.get('service')  # 'covers', 'motion', 'videoshot'
        details = data.get('details', '')

        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400

        if not service or service not in ['covers', 'motion', 'videoshot']:
            return jsonify({'success': False, 'error': '???????????????? ?????? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????????????????????????? ?????????????? orders
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'orders'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            cursor.execute("""
                CREATE TABLE orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    service_type VARCHAR(50) NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    payment_id VARCHAR(100) UNIQUE,
                    payment_system VARCHAR(20) DEFAULT 'site',
                    details TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("?????????????? orders ??????????????")

        # ???????????????? ???????????????????? ?? ????????????????????????
        cursor.execute('SELECT name, tg FROM label WHERE telegram_id = %s', (user_id,))
        user_info = cursor.fetchone()
        user_name = user_info[0] if user_info and user_info[0] else f"???????????????????????? {user_id}"
        user_username = user_info[1] if user_info and user_info[1] else "???? ????????????"

        # ???????????????????? ?????????????????? ????????????
        service_prices = {
            'covers': 500.00,
            'motion': 800.00,
            'videoshot': 1200.00
        }
        amount = service_prices.get(service, 500.00)

        service_labels = {
            'covers': '??????????????',
            'motion': 'Motion ??????????????',
            'videoshot': '????????????????'
        }
        service_label = service_labels.get(service, service)

        # ?????????????? ??????????
        cursor.execute("""
            INSERT INTO orders (user_id, service_type, amount, status, payment_system, details, created_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, service, amount, 'pending', 'site', details, datetime.now()))

        order_id = cursor.fetchone()[0]
        conn.commit()

        logger.info(f"???????????? ?????????? ?????????????? ID {order_id} ?????? ???????????????????????? {user_id}")

        # ???????????????????? ?????????????????????? ??????????????
        try:
            notification_message = f"""???? <b>?????????? ?????????? {service_label}!</b>

???? <b>????????????:</b> {user_name} (@{user_username})
???? <b>??????????:</b> {amount}???
???? <b>????????????????:</b>
{details if details else '???????? ???? ?????? ????????????????'}

???? <b>ID ????????????:</b> {order_id}"""

            send_admin_notification(notification_message)
        except Exception as e:
            logger.error(f"???????????? ???????????????? ?????????????????????? ????????????: {e}")

        return jsonify({
            'success': True,
            'order_id': order_id,
            'amount': amount,
            'message': '?????????? ???????????? ??????????????'
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ???????????????? ???????????? ??????????????: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/support/request', methods=['POST'])
def create_support_request():
    """?????????????? ???????????? ?? ??????????????????"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '???????????? ???? ????????????????'}), 400

        user_id = data.get('user_id')
        template_id = data.get('templateId')
        template_title = data.get('templateTitle', '????????????')
        request_data = data.get('data', {})

        if not user_id:
            return jsonify({'success': False, 'error': 'ID ???????????????????????? ???? ????????????'}), 400

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': '???????????? ?????????????????????? ?? ???????? ????????????'}), 500

        cursor = conn.cursor()

        # ?????????????????? ?????????????????????????? ?????????????? support_requests
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'support_requests'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            cursor.execute("""
                CREATE TABLE support_requests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    template_id VARCHAR(50),
                    template_title VARCHAR(255),
                    request_data JSONB,
                    status VARCHAR(20) DEFAULT '????????????',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("?????????????? support_requests ??????????????")

        # ???????????????? ???????????????????? ?? ????????????????????????
        cursor.execute('SELECT name, tg FROM label WHERE telegram_id = %s', (user_id,))
        user_info = cursor.fetchone()
        user_name = user_info[0] if user_info and user_info[0] else f"???????????????????????? {user_id}"
        user_username = user_info[1] if user_info and user_info[1] else "???? ????????????"

        # ?????????????? ????????????
        import json
        cursor.execute("""
            INSERT INTO support_requests (user_id, template_id, template_title, request_data, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, template_id, template_title, json.dumps(request_data), '????????????', datetime.now()))

        request_id = cursor.fetchone()[0]
        conn.commit()

        logger.info(f"?????????????? ???????????? ?????????????????? ID {request_id} ?????? ???????????????????????? {user_id}")

        # ???????????????????? ?????????????????????? ??????????????
        try:
            # ?????????????????? ?????????? ????????????
            request_text = f"???? <b>?????????? ???????????? ?? ??????????????????!</b>\n\n"
            request_text += f"???? <b>????????????????????????:</b> {user_name} (@{user_username})\n"
            request_text += f"???? <b>?????? ????????????:</b> {template_title}\n\n"
            request_text += "<b>???????????? ????????????:</b>\n"

            for key, value in request_data.items():
                import re
                label = re.sub(r'([A-Z])', r' \1', key).strip().capitalize()
                request_text += f"{label}: {value}\n"

            request_text += f"\n???? <b>ID ????????????:</b> {request_id}"

            send_admin_notification(request_text)
        except Exception as e:
            logger.error(f"???????????? ???????????????? ?????????????????????? ????????????: {e}")

        return jsonify({
            'success': True,
            'request_id': request_id,
            'message': '???????????? ?????????????? ??????????????'
        })

    except Exception as e:
        logger.error(f"???????????? ?????? ???????????????? ???????????? ??????????????????: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': '???????????? ??????????????'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check для мониторинга."""
    checks = {
        "status": "ok",
        "db": False,
        "timestamp": datetime.now().isoformat(),
    }
    try:
        conn = get_pg_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            checks["db"] = True
            cursor.close()
            conn.close()
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        checks["status"] = "degraded"

    status_code = 200 if checks["db"] else 503
    return jsonify(checks), status_code


# ?????????????????????? ???????????? ?????? ???????????????? JSON ???????????? HTML
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': '???????????????? ???? ????????????'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': '???????????????????? ???????????? ??????????????'}), 500

@app.errorhandler(400)
def bad_request(error):
    return jsonify({'success': False, 'error': '???????????????? ????????????'}), 400

if __name__ == '__main__':
    import ssl
    import os

    # ?????????????????? ?????????????? SSL ????????????????????????
    cert_file = "ssl_certs/cert.pem"
    key_file = "ssl_certs/key.pem"

    if os.path.exists(cert_file) and os.path.exists(key_file):
        # ?????????????? SSL ????????????????
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.load_cert_chain(cert_file, key_file)

        print("???? ???????????? API ?????????????? ?? HTTPS...")
        app.run(host='0.0.0.0', port=5000, debug=False, ssl_context=context)
    else:
        print("??????  SSL ?????????????????????? ???? ??????????????. ???????????? ?? HTTP ????????????...")
        print("   ?????? HTTPS ??????????????????: python generate_ssl.py")
        app.run(host='0.0.0.0', port=5000, debug=False)

# -*- coding: utf-8 -*-
"""Инициализация БД: колонки, таблицы, проверка экземпляра бота."""
import logging
import telebot

from utils.database import get_pg_connection, return_pg_connection
from core.bot import bot

logger = logging.getLogger(__name__)


def add_platform_links_column():
    """Добавить колонку platform_links в releases, если её нет."""
    logger.info("Adding platform_links column to releases table...")
    conn = get_pg_connection()
    if not conn:
        logger.error("Cannot add platform_links column - no connection")
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE releases ADD COLUMN IF NOT EXISTS platform_links JSONB DEFAULT '{}'")
        conn.commit()
        logger.info("✅ Added platform_links column to releases table")
        return True
    except Exception as e:
        logger.warning(f"Could not add platform_links column: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_pg_connection(conn)


def ensure_label_columns():
    """Проверить/добавить нужные колонки в таблицу label."""
    conn = get_pg_connection()
    if not conn:
        logger.error("Failed to connect to database for column check")
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        required_columns = {
            'email': 'TEXT', 'fio': 'TEXT', 'phone': 'TEXT',
            'steezy': 'INTEGER DEFAULT 0', 'bibi': 'INTEGER DEFAULT 0', 'shvepz': 'INTEGER DEFAULT 0',
            'referral_code': 'TEXT', 'referral_count': 'INTEGER DEFAULT 0', 'referral_earnings': 'NUMERIC(10, 2) DEFAULT 0'
        }
        for column, column_type in required_columns.items():
            try:
                cursor.execute(f"ALTER TABLE label ADD COLUMN IF NOT EXISTS {column} {column_type}")
            except Exception as e:
                logger.warning(f"Could not ensure column {column}: {e}")
        conn.commit()
        logger.info("✅ All required label columns verified")
        return True
    except Exception as e:
        logger.error(f"Error ensuring label columns: {e}")
        return False
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)


def create_referrals_table():
    """Создать таблицу referrals, если её нет."""
    conn = get_pg_connection()
    if not conn:
        logger.error("Cannot create referrals table - no connection")
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                referred_id BIGINT NOT NULL,
                referral_code TEXT NOT NULL,
                status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'blocked')),
                bonus_paid BOOLEAN DEFAULT FALSE,
                bonus_amount NUMERIC(10, 2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(referred_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id ON referrals(referrer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referred_id ON referrals(referred_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(referral_code)')
        conn.commit()
        logger.info("✅ referrals table created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating referrals table: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_pg_connection(conn)


def check_bot_instance():
    """Проверка на единственный экземпляр бота."""
    try:
        bot_info = bot.get_me()
        logger.info(f"✅ Bot instance check passed: @{bot_info.username}")
        return True
    except telebot.apihelper.ApiTelegramException as e:
        if "409" in str(e) or "Conflict" in str(e):
            logger.error("🚨 CRITICAL: Another bot instance is already running!")
            return False
        logger.error(f"❌ Bot instance check failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error during bot check: {e}")
        return False

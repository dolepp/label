# -*- coding: utf-8 -*-
"""Вспомогательные функции: проверки, баланс, текст."""
import logging
import re
from utils.database import get_pg_connection, return_pg_connection

logger = logging.getLogger(__name__)

def is_cancel_message(message):
    """Проверка, что сообщение — отмена (кнопка «❌ Отмена», /cancel или «отмена»)."""
    if not message or not getattr(message, "text", None) or not message.text:
        return False
    t = (message.text or "").strip().lower()
    return t in ("/cancel", "отмена", "❌ отмена")

def get_user_balance_safe(user_id: int) -> float:
    conn = get_pg_connection()
    if not conn:
        return 0.0
    try:
        cur = conn.cursor()
        cur.execute('SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s', (user_id,))
        row = cur.fetchone()
        return float(row[0]) if row else 0.0
    except Exception as e:
        logger.error(f"Failed to get balance for {user_id}: {e}")
        return 0.0
    finally:
        try:
            cur.close()
            return_pg_connection(conn)
        except Exception:
            pass

def change_user_balance(user_id: int, delta: float) -> bool:
    conn = get_pg_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute('UPDATE label SET balance = COALESCE(balance,0) + %s WHERE telegram_id = %s', (delta, user_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to change balance for {user_id} by {delta}: {e}")
        return False
    finally:
        try:
            cur.close()
            return_pg_connection(conn)
        except Exception:
            pass

def is_profile_complete(user_id: int) -> tuple[bool, str]:
    """Проверяет, заполнен ли профиль пользователя. Возвращает (is_complete, missing_field)"""
    conn = get_pg_connection()
    if not conn:
        return (False, "Ошибка подключения к базе данных")
    
    try:
        cur = conn.cursor()
        cur.execute('SELECT name FROM label WHERE telegram_id = %s', (user_id,))
        row = cur.fetchone()
        
        if not row:
            return (False, "Профиль не найден")
        
        name = row[0]
        if not name or not name.strip():
            return (False, "name")
        
        return (True, "")
    except Exception as e:
        logger.error(f"Failed to check profile for {user_id}: {e}")
        return (False, "Ошибка при проверке профиля")
    finally:
        try:
            cur.close()
            return_pg_connection(conn)
        except Exception:
            pass

def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )

def escape_markdown(text: str) -> str:
    """Escape Markdown special characters"""
    if not text:
        return ""
    special_chars = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", str(text))

def is_admin(user_id):
    """Проверка, является ли пользователь админом"""
    from core.config import ADMIN_IDS, PERMANENT_ADMINS
    if user_id in PERMANENT_ADMINS:
        return True
    conn = get_pg_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT admin FROM label WHERE telegram_id = %s', (user_id,))
        result = cursor.fetchone()
        if result and result[0] == 1:
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False
    finally:
        if conn:
            try:
                cursor.close()
                return_pg_connection(conn)
            except:
                pass

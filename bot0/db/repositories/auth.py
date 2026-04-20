"""Web authorization code persistence."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from db.pool import connection


def generate_numeric_code(length: int = 6) -> str:
    lower = 10 ** (length - 1)
    upper = (10 ** length) - 1
    return str(secrets.randbelow(upper - lower + 1) + lower)


def ensure_auth_codes_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_codes (
            id SERIAL PRIMARY KEY,
            code VARCHAR(8) UNIQUE NOT NULL,
            user_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            used_at TIMESTAMP NULL
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_codes_code ON auth_codes(code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_codes_user_id ON auth_codes(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_codes_expires_at ON auth_codes(expires_at)")


def create_auth_code(user_id: int, ttl_minutes: int = 5) -> str | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            ensure_auth_codes_table(cur)
            cur.execute("DELETE FROM auth_codes WHERE user_id = %s AND used = FALSE", (user_id,))
            expires_at = datetime.now() + timedelta(minutes=ttl_minutes)

            for _ in range(5):
                code = generate_numeric_code()
                try:
                    cur.execute(
                        "INSERT INTO auth_codes (code, user_id, expires_at) VALUES (%s, %s, %s)",
                        (code, user_id, expires_at),
                    )
                    conn.commit()
                    return code
                except Exception:
                    conn.rollback()
                    ensure_auth_codes_table(cur)
                    cur.execute("DELETE FROM auth_codes WHERE user_id = %s AND used = FALSE", (user_id,))
            return None
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

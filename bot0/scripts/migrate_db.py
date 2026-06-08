#!/usr/bin/env python3
"""Idempotent database migration for bot/site runtime schema and indexes."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "bot0" / ".env"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(ENV_FILE)

DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "label")),
    "user": os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres")),
    "password": os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "")),
    "host": os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost")),
    "port": os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432")),
}

STATEMENTS = [
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
    """,
    """
    CREATE TABLE IF NOT EXISTS promo_code_usage (
        id SERIAL PRIMARY KEY,
        promo_code_id INTEGER REFERENCES promo_codes(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL,
        used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, promo_code_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_discount_promos (
        user_id BIGINT NOT NULL,
        promo_code_id INTEGER NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, promo_code_id)
    )
    """,
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
    """,
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
    """,
    "ALTER TABLE releases ADD COLUMN IF NOT EXISTS audio_local_path TEXT",
    "ALTER TABLE releases ADD COLUMN IF NOT EXISTS cover_local_path TEXT",
    "ALTER TABLE releases ADD COLUMN IF NOT EXISTS contract_local_path TEXT",
    "ALTER TABLE releases ADD COLUMN IF NOT EXISTS lyrics_local_path TEXT",
    "ALTER TABLE releases ADD COLUMN IF NOT EXISTS extra_metadata JSONB DEFAULT '{}'::jsonb",
    "CREATE INDEX IF NOT EXISTS idx_label_telegram_id ON label(telegram_id)",
    "CREATE INDEX IF NOT EXISTS idx_label_created ON label(created_date DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_releases_user_created ON releases(user_id, created_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_releases_album_track ON releases(album_id, track_number, id)",
    "CREATE INDEX IF NOT EXISTS idx_releases_status_created ON releases(status, created_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id, created_date DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_report_requests_user_created ON report_requests(user_id, created_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_drafts_user_updated ON drafts(user_id, updated_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code)",
    "CREATE INDEX IF NOT EXISTS idx_promo_codes_active ON promo_codes(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_promo_code_usage_user_id ON promo_code_usage(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_discount_promos_user_id ON user_discount_promos(user_id)",
]


def main() -> int:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                for statement in STATEMENTS:
                    cur.execute(statement)
        print(f"Applied {len(STATEMENTS)} migration statements to {DB_CONFIG['dbname']}.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

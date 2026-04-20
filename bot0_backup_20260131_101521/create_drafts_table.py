#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
import psycopg2

# Создание таблицы drafts
conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="60606611125",
    host="localhost",
    port="5432"
)

try:
    cursor = conn.cursor()
    
    print("Создаю таблицу drafts...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drafts (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            draft_type TEXT NOT NULL,
            data JSONB,
            current_step INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON drafts(user_id)")
    
    conn.commit()
    print("✅ Таблица drafts создана успешно!")
    
    # Проверяем
    cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'drafts'")
    count = cursor.fetchone()[0]
    print(f"Таблица drafts: {'EXISTS' if count > 0 else 'NOT FOUND'}")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    conn.rollback()
finally:
    cursor.close()
    conn.close()


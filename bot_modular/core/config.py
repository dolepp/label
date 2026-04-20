# -*- coding: utf-8 -*-
"""Конфигурация модульного бота."""
import os
from dotenv import load_dotenv

load_dotenv()

# Токены и каналы
BOT_TOKEN = os.getenv('BOT_TOKEN', '6285811276:AAHoVTSOok-_Bwxe1GWSSSsN7LiP5CynYas')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@twaslabel')
OWNER_USERNAME = "@realjustci"
MANAGER_USERNAME = "@twaslabelmn"

# БД
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "60606611125"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

# Цены услуг
SERVICE_PRICES = {
    "cover": 500,
    "motion": 800,
    "videoshot": 1000,
    "distribution": 1299
}

# Админы
ADMIN_IDS = [664506846, 1429461076, 598604529, 1043989654]
PERMANENT_ADMINS = [464793425, 1398275867]

# Статусы
SUPPORT_REQUEST_STATUSES = ["принят", "требует уточнения", "решен"]
DESIGN_ORDER_STATUSES = ["в обработке", "готов", "отменён"]

# YooKassa
YOOKASSA_ACCOUNT_ID = "1215507"
YOOKASSA_SECRET_KEY = "live_8MVRYBieniDXJqm2K0KSNCOMFpUXZ0gjMebRfdl__B4"

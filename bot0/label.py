import random
from datetime import datetime, timedelta
import json
import logging
import os
import re
from sys import exception

import threading
import time
import uuid
import psycopg2
from psycopg2 import Error
from flask import Flask, request, jsonify, session, redirect, url_for

# Для создания Word документов
try:
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("python-docx module not available. Word document generation will be disabled.")

# Для создания Excel файлов
try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    XLSX_AVAILABLE = True
except ImportError:
    XLSX_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("openpyxl module not available. Excel report generation will be disabled.")

# Дополнительные импорты для работы с файлами
import tempfile
import io
from urllib.parse import quote

from db.repositories.release_files import get_release_file_id
from services import admin_access, bot_runner, contracts, notifications, payment_callbacks, payments, referral_notifications, runtime_helpers, service_artist_release, user_storage
from utils.security import escape_html, escape_markdown, validate_file_upload
from keyboards.reply import create_cancel_keyboard
from handlers.onboarding import require_channel_subscription

from handlers.legacy_distribution_steps import save_release_data_for_user
from handlers.design_admin import build_design_status_markup, format_design_request_text

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv не установлен, используем системные переменные


app = Flask(__name__)
app.secret_key = os.urandom(24)

# Проверяем доступность модуля для планировщика
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("schedule module not available. Scheduled tasks will be disabled.")

import telebot
from telebot import types

# Импорты для пула соединений PostgreSQL
from psycopg2 import pool
from psycopg2.pool import ThreadedConnectionPool

# Initialize bot
BOT_TOKEN = os.getenv('BOT_TOKEN', '6285811276:AAHoVTSOok-_Bwxe1GWSSSsN7LiP5CynYas')
bot = telebot.TeleBot(BOT_TOKEN)
referral_notifications.configure(bot)
user_storage.configure(bot)
bot.user_data = {}  # Initialize user data storage

# Инициализация broadcast_levels
bot.broadcast_levels = {}

# Проверяем доступность модуля для платежей
try:
    from yookassa import Configuration, Payment
    YOOKASSA_AVAILABLE = True
except ImportError:
    YOOKASSA_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("yookassa module not available. Payment functionality will be disabled.")

# Initialize logging with enhanced configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Add specific logger for connection issues
connection_logger = logging.getLogger('connection')
connection_logger.setLevel(logging.WARNING)


def is_cancel_message(message):
    """Проверка, что сообщение — отмена (кнопка «❌ Отмена», /cancel или «отмена»)."""
    if not message or not getattr(message, "text", None) or not message.text:
        return False
    t = (message.text or "").strip().lower()
    return t in ("/cancel", "отмена", "❌ отмена")


def is_save_draft_message(message):
    """Проверка, что сообщение — сохранение черновика."""
    if not message or not getattr(message, "text", None) or not message.text:
        return False
    t = (message.text or "").strip().lower()
    return t in ("💾 сохранить черновик", "сохранить черновик", "черновик")


# --- Balance helpers ---
def get_user_balance_safe(user_id: int) -> float:
    return runtime_helpers.get_user_balance_safe(user_id)


def change_user_balance(user_id: int, delta: float) -> bool:
    return runtime_helpers.change_user_balance(user_id, delta)


def is_profile_complete(user_id: int) -> tuple[bool, str]:
    return runtime_helpers.is_profile_complete(user_id)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot_log.log'
)
logger = logging.getLogger(__name__)

# Configure YooKassa
Configuration.account_id = "1215507"
Configuration.secret_key = "live_8MVRYBieniDXJqm2K0KSNCOMFpUXZ0gjMebRfdl__B4"

logger.info(f"YooKassa configured with account_id: {Configuration.account_id}")

# Проверка конфигурации YooKassa при запуске
try:
    if YOOKASSA_AVAILABLE:
        # Тестируем подключение к YooKassa
        test_payment = Payment.create({
            "amount": {"value": "1.00", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": "https://t.me/twaslabel_bot"},
            "capture": True,
            "description": "Test payment",
            "metadata": {"test": "true"}
        })
        logger.info("✅ YooKassa configuration test successful with new credentials")
        # Отменяем тестовый платеж
        try:
            Payment.cancel(test_payment.id)
        except:
            pass  # Игнорируем ошибки отмены тестового платежа
    else:
        logger.warning("⚠️ YooKassa module not available")
except Exception as e:
    logger.error(f"❌ YooKassa configuration test failed: {e}")
    logger.error("Check your YooKassa credentials and network connection")

def test_channel_access():
    """Тестирование доступа бота к каналу"""
    try:
        # Пытаемся получить информацию о канале
        chat_info = bot.get_chat(CHANNEL_USERNAME)
        logger.info(f"✅ Channel access test successful: {chat_info.title}")

        # Пытаемся получить информацию о боте в канале
        bot_member = bot.get_chat_member(CHANNEL_USERNAME, bot.get_me().id)
        logger.info(f"✅ Bot member status: {bot_member.status}")

        if bot_member.status in ['administrator', 'creator']:
            logger.info("✅ Bot has admin rights in channel")
            return True
        else:
            logger.warning("⚠️ Bot is not an administrator in the channel")
            return False

    except Exception as e:
        logger.error(f"❌ Channel access test failed: {e}")
        logger.error("Bot needs to be added to the channel as administrator!")
        return False

def check_yookassa_status():
    """Проверка статуса YooKassa API"""
    try:
        if not YOOKASSA_AVAILABLE:
            return False, "YooKassa module not available"

        if not Configuration.account_id or not Configuration.secret_key:
            return False, "YooKassa credentials not configured"

        # Простая проверка доступности API
        import requests
        response = requests.get("https://api.yookassa.ru/v3/me",
                              auth=(Configuration.account_id, Configuration.secret_key),
                              timeout=10)

        if response.status_code == 200:
            return True, "YooKassa API is accessible"
        else:
            return False, f"YooKassa API returned status {response.status_code}"

    except Exception as e:
        return False, f"YooKassa API check failed: {str(e)}"

# Crypto Bot Configuration
CRYPTO_BOT_TOKEN = "449150:AAhpOhS1Mwm8mUfiVuOazq6Y7YHc6wkACxj"

# Constants
CHANNEL_USERNAME = "@twaslabel"
OWNER_USERNAME = "@realjustci"
MANAGER_USERNAME = "@twaslabelmn"
SUPPORT_HOURS = "10:00-22:00 МСК"
VPN_CHANNEL = "@twasvpn"
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://twas.webhop.me")

# Service prices
PRICES = {
    "distribution": 1299,  # Single price
    "cover": 2000,
    "motion": 1500,
    "videoshot": 1000,
    "recording_first": 500,
    "recording": 800,
    "mixing": 2000,
    "ready_track": 10000
}

# User levels
USER_LEVELS = {
    "artist": 1,
    "admin": 2,
    "owner": 3,
    "creator": 4
}

# Постоянные администраторы (Telegram ID)
PERMANENT_ADMINS = [464793425, 1398275867]

SUPPORT_REQUEST_STATUSES = ["принят", "требует уточнения", "решен"]
DESIGN_ORDER_STATUSES = ["принят", "в работе", "готов", "требует уточнения"]

SUPPORT_TEMPLATES = [
    {
        "id": "moderation",
        "button": "⚡️ Ускорение модерации",
        "title": "Ускорение модерации",
        "description": "Если релиз завис на модерации, отправьте данные и мы уведомим площадки.",
        "fields": [
            "Исполнитель - название релиза"
        ]
    },
    {
        "id": "videoshot",
        "button": "🎥 Видеошот",
        "title": "Заявка на видеошот",
        "description": "Для оформления видеошота нужны технические данные и ссылка на материалы.",
        "fields": [
            "Исполнитель - название трека",
            "UPC",
            "ISRC (если трек внутри альбома)",
            "Ссылка на диск с видеошотом"
        ],
        "note": "Требования: mp4/H.264, 720p, 15 секунд, желательно вертикальный формат без синхрона губ."
    },
    {
        "id": "move_release",
        "button": "🔁 Переместить релиз",
        "title": "Перенос релиза в другую карточку",
        "description": "Поможем переместить релиз в нужную карточку артиста.",
        "fields": [
            "Ссылка на нужную карточку",
            "Ссылка на релиз",
            "UPC",
            "Никнейм"
        ]
    },
    {
        "id": "remove_release",
        "button": "🧹 Убрать релизы",
        "title": "Удалить релизы из карточки",
        "description": "Укажите карточку и релизы, которые нужно убрать.",
        "fields": [
            "Ссылка на карточку",
            "Ссылки на релизы (каждый с новой строки)",
            "Никнейм"
        ]
    },
    {
        "id": "youtube_verify",
        "button": "▶️ Верификация YouTube",
        "title": "Верификация YouTube-канала",
        "description": "Отправьте ссылки, если канал соответствует требованиям YouTube.",
        "fields": [
            "Ссылка на YouTube канал",
            "Ссылка на YouTube Topic",
            "Никнейм"
        ],
        "note": "На канале должен быть тематический контент артиста и минимум один релиз от дистрибьютора."
    },
    {
        "id": "set_photo",
        "button": "🖼 Установить фото",
        "title": "Поменять фотографию карточки",
        "description": "Загрузим новую фотографию артиста на нужной площадке.",
        "fields": [
            "Ссылка на карточку",
            "Ссылка на фотографию на диске",
            "Никнейм"
        ]
    },
    {
        "id": "missing_store",
        "button": "🚫 Нет на витрине",
        "title": "Релиз отсутствует на площадке",
        "description": "Сообщите, где не отображается релиз.",
        "fields": [
            "Исполнитель - название релиза",
            "Нет на витрине ... (указать площадку)",
            "UPC",
            "Никнейм"
        ]
    },
    {
        "id": "soundcloud_whitelist",
        "button": "☁️ Вайтлист SoundCloud",
        "title": "Добавление в вайтлист SoundCloud",
        "description": "Заявка на вайтлист для SoundCloud (YouTube не поддерживается).",
        "fields": [
            "Ссылка на профиль SoundCloud",
            "Никнейм"
        ],
        "note": "Вайтлисты YouTube не оформляем."
    }
]

DESIGN_BRIEF_TEMPLATES = {
    "cover": {
        "title": "Бриф для обложки",
        "fields": [
            "Исполнитель - релиз",
            "Идеи и пожелания",
            "Ссылка на материалы / референсы",
            "Сообщение админу"
        ],
        "note": "После оплаты администратор свяжется и пришлёт превью."
    },
    "motion": {
        "title": "Бриф для motion-обложки",
        "fields": [
            "Исполнитель - релиз",
            "Идея и желаемые эффекты",
            "Ссылка на исходную обложку / материалы",
            "Дополнительный комментарий"
        ],
        "note": "Опишите желаемую динамику и настроение. После оплаты свяжемся для согласования."
    },
    "videoshot": {
        "title": "Бриф для видеошота",
        "fields": [
            "Исполнитель - трек",
            "Идея/сюжет видеошота",
            "Ссылка на обложку",
            "Ссылка на дополнительные материалы"
        ],
        "note": "Видео должно соответствовать требованиям: mp4/H.264, 720p, 15 секунд."
    }
}

SUPPORT_REQUESTS = []
DESIGN_BRIEF_REQUESTS = []
SERVICE_LABELS = {
    "cover": "Обложки",
    "motion": "Motion",
    "videoshot": "Видеошоты"
}


def generate_request_id():
    return payment_callbacks.generate_request_id()


def format_human_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return value


def get_status_summary(items, statuses):
    summary = {status: 0 for status in statuses}
    for item in items:
        summary[item.get("status", statuses[0])] = summary.get(item.get("status", statuses[0]), 0) + 1
    total = len(items)
    parts = [f"Всего: {total}"]
    for status in statuses:
        parts.append(f"{status.title()}: {summary.get(status, 0)}")
    return "\n".join(parts)


def ensure_user_storage(user_id):
    return user_storage.ensure_user_storage(user_id)


def get_user_support_requests(user_id):
    """Получить заявки пользователя из памяти и БД"""
    requests = [req for req in SUPPORT_REQUESTS if req.get("user_id") == user_id]

    # Также загружаем из БД
    conn = get_pg_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, template_id, template_title, details, status, release_id, release_name, created_at
                FROM support_requests
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 50
            """, (user_id,))

            for row in cursor.fetchall():
                db_id, template_id, template_title, details, status, release_id, release_name, created_at = row
                # Проверяем, нет ли уже такой заявки в памяти
                request_id = f"db_{db_id}"
                if not any(req.get("id") == request_id for req in requests):
                    requests.append({
                        "id": request_id,
                        "template_id": template_id,
                        "template_title": template_title,
                        "details": details,
                        "status": status,
                        "user_id": user_id,
                        "release_id": release_id,
                        "release_name": release_name,
                        "created_at": created_at.isoformat() if created_at else datetime.now().isoformat()
                    })
        except Exception as e:
            logger.error(f"Ошибка при загрузке заявок из БД: {e}")
        finally:
            if conn:
                cursor.close()
                return_pg_connection(conn)

    return requests


def get_user_design_orders(user_id):
    return [order for order in DESIGN_BRIEF_REQUESTS if order.get("user_id") == user_id]

# Этапы диалога для создания лицензионного договора
(
    CONTRACT_NUMBER, CONTRACT_DATE, LICENSOR_NAME, LICENSOR_PSEUDONYM,
    LICENSOR_PASSPORT, LICENSOR_PASSPORT_ISSUED, LICENSOR_PASSPORT_DATE,
    LICENSOR_BIRTH_DATE, LICENSOR_BIRTH_PLACE, LICENSOR_REGISTRATION,
    LICENSOR_SNILS, LICENSOR_INN, LICENSOR_BANK_NAME, LICENSOR_BANK_ACCOUNT,
    LICENSOR_BANK_CORRESPONDENT, LICENSOR_BANK_INN, LICENSOR_BANK_BIK,
    LICENSOR_BANK_KPP, LICENSOR_SIGNATURE, WORK_ALBUM_TITLE, WORK_TRACK_TITLE,
    WORK_MUSIC_AUTHOR, WORK_TEXT_AUTHOR, WORK_PERFORMER, WORK_PHONOGRAM_PRODUCER,
    WORK_DELIVERY_YEAR
) = range(26)

# HTML шаблон для веб-интерфейса
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TWAS Label Studio</title>
  <style>
    :root {
      --primary: #6a11cb;
      --secondary: #2575fc;
      --dark: #1a1a2e;
      --light: #f8f9fa;
      --success: #28a745;
      --danger: #dc3545;
      --warning: #ffc107;
      --info: #17a2b8;
    }

    body {
      font-family: 'Montserrat', sans-serif;
      background: linear-gradient(135deg, var(--primary), var(--secondary));
      color: var(--light);
      margin: 0;
      padding: 0;
      min-height: 100vh;
    }

    .container {
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
    }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px 0;
      border-bottom: 1px solid rgba(255,255,255,0.1);
    }

    .logo {
      font-size: 28px;
      font-weight: 700;
      background: linear-gradient(to right, #fff, #ccc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .hero {
      text-align: center;
      padding: 50px 20px;
    }

    .hero h1 {
      font-size: 48px;
      margin-bottom: 20px;
      background: linear-gradient(to right, #fff, #ccc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .hero p {
      font-size: 18px;
      max-width: 800px;
      margin: 0 auto 30px;
      line-height: 1.6;
    }

    .btn {
      display: inline-block;
      background: linear-gradient(to right, var(--primary), var(--secondary));
      color: white;
      padding: 10px 20px;
      border-radius: 5px;
      text-decoration: none;
      font-weight: 500;
      transition: all 0.3s;
      border: none;
      cursor: pointer;
    }

    .btn:hover {
      opacity: 0.9;
      transform: translateY(-2px);
    }

    .services-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 20px;
      margin-top: 30px;
    }

    .service-card {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 10px;
      padding: 20px;
      transition: all 0.3s;
    }

    .service-card:hover {
      background: rgba(255,255,255,0.07);
      transform: translateY(-5px);
    }

    .service-card h3 {
      font-size: 20px;
      margin-bottom: 15px;
      color: white;
    }

    .service-card p {
      color: rgba(255,255,255,0.7);
      margin-bottom: 20px;
      line-height: 1.5;
    }

    .service-card .price {
      font-size: 24px;
      font-weight: 700;
      margin-bottom: 15px;
      color: white;
    }

    .contact-section {
      text-align: center;
      padding: 30px;
      background: rgba(255,255,255,0.05);
      border-radius: 10px;
      margin-top: 30px;
    }

    @media (max-width: 768px) {
      .hero h1 {
        font-size: 36px;
      }
      .services-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body>
<div class="container">
  <header>
    <div class="logo">TWAS LABEL STUDIO</div>
  </header>

  <div class="hero">
    <h1>Профессиональная лейбл-студия</h1>
    <p>TWAS Label Studio - это полный цикл музыкального производства: от записи и сведения до дистрибуции и продвижения. Мы помогаем артистам реализовывать свой творческий потенциал и выводить музыку на международные площадки.</p>
  </div>

  <div class="services-grid">
    <div class="service-card">
      <h3>Дистрибуция</h3>
      <p>Распространите свою музыку на всех цифровых площадках мира: Spotify, Apple Music, YouTube Music и другие. Получайте роялти и продвигайте свой бренд.</p>
      <div class="price">1 299 ₽</div>
      <a href="https://t.me/twaslabel_bot" class="btn">Заказать в боте</a>
    </div>

    <div class="service-card">
      <h3>Обложки</h3>
      <p>Профессиональные обложки для ваших релизов от наших дизайнеров. Уникальный стиль, который выделит вас среди других артистов.</p>
      <div class="price">2 000 ₽</div>
      <a href="https://t.me/twaslabel_bot" class="btn">Заказать в боте</a>
    </div>

    <div class="service-card">
      <h3>Motion обложки</h3>
      <p>Анимированные обложки для ваших релизов, которые привлекают внимание и увеличивают вовлеченность аудитории.</p>
      <div class="price">1 500 ₽</div>
      <a href="https://t.me/twaslabel_bot" class="btn">Заказать в боте</a>
    </div>

    <div class="service-card">
      <h3>Видеошот</h3>
      <p>Креативные видеошоты для ваших треков. Быстро, качественно и с гарантией попадания в рекомендации.</p>
      <div class="price">1 000 ₽</div>
      <a href="https://t.me/twaslabel_bot" class="btn">Заказать в боте</a>
    </div>

    <div class="service-card">

      <p>Профессиональная студия звукозаписи с лучшим оборудованием и звукорежиссерами. Запишите свой хит в комфортной атмосфере.</p>
      <div class="price">800 ₽/час</div>
      <a href="https://t.me/twaslabel_bot" class="btn">Записаться в боте</a>
    </div>

    <div class="service-card">
      <h3>TWAS VPN</h3>
      <p>Безопасный и быстрый VPN для доступа к международным музыкальным площадкам и сервисам.</p>
      <div class="price">Скидки для клиентов</div>
      <a href="https://t.me/twasvpn" class="btn">Перейти в @twasvpn</a>
    </div>
  </div>

  <div class="contact-section">
    <h2>Начните свой путь к успеху</h2>
    <p>Свяжитесь с нами через Telegram бот для получения консультации и заказа услуг</p>
    <a href="https://t.me/twaslabel_bot" class="btn" style="font-size: 18px; padding: 15px 30px;">Перейти в бот</a>
  </div>
</div>
</body>
</html>"""



# Release statuses
RELEASE_STATUSES = [
    "принят",
    "отправлен на площадки",
    "отгружен на площадки",
    "Релиз",
    "Отозван с площадок"
]

# Database configuration - используем переменные окружения или значения по умолчанию
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "60606611125"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

# Пул соединений PostgreSQL для оптимизации
_db_pool = None
_db_pool_lock = threading.Lock()

def init_db_pool():
    return runtime_helpers.init_db_pool()

def get_pg_connection(max_retries=3, retry_delay=0.5):
    return runtime_helpers.get_pg_connection(max_retries=max_retries, retry_delay=retry_delay)

def return_pg_connection(conn):
    return runtime_helpers.return_pg_connection(conn)


def perform_system_diagnostics():
    """Run comprehensive health checks for critical subsystems"""
    diagnostics = []

    # Telegram Bot API availability
    try:
        bot_info = bot.get_me()
        diagnostics.append({
            "name": "Telegram API",
            "ok": True,
            "details": f"Подключен как @{bot_info.username}"
        })
    except Exception as e:
        diagnostics.append({
            "name": "Telegram API",
            "ok": False,
            "details": f"Ошибка: {e}"
        })

    # Channel access (admin rights & visibility)
    try:
        channel_access = test_channel_access()
        diagnostics.append({
            "name": "Канал Telegram",
            "ok": channel_access,
            "details": "Доступ подтвержден" if channel_access else "Нет доступа к каналу или прав администратора"
        })
    except Exception as e:
        diagnostics.append({
            "name": "Канал Telegram",
            "ok": False,
            "details": f"Ошибка: {e}"
        })

    # Database connectivity
    conn = None
    cursor = None
    try:
        conn = get_pg_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            diagnostics.append({
                "name": "PostgreSQL",
                "ok": True,
                "details": "Соединение установлено"
            })
        else:
            diagnostics.append({
                "name": "PostgreSQL",
                "ok": False,
                "details": "Не удалось подключиться к базе данных"
            })
    except Exception as e:
        diagnostics.append({
            "name": "PostgreSQL",
            "ok": False,
            "details": f"Ошибка: {e}"
        })
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                return_pg_connection(conn)
        except Exception:
            pass

    # YooKassa API check
    status, description = check_yookassa_status()
    diagnostics.append({
        "name": "YooKassa API",
        "ok": status,
        "details": description
    })

    # Optional modules availability
    diagnostics.append({
        "name": "python-docx",
        "ok": DOCX_AVAILABLE,
        "details": "Модуль доступен" if DOCX_AVAILABLE else "Модуль недоступен, генерация .docx отключена"
    })

    diagnostics.append({
        "name": "openpyxl",
        "ok": XLSX_AVAILABLE,
        "details": "Модуль доступен" if XLSX_AVAILABLE else "Модуль недоступен, генерация .xlsx отключена"
    })

    diagnostics.append({
        "name": "schedule",
        "ok": SCHEDULE_AVAILABLE,
        "details": "Планировщик активен" if SCHEDULE_AVAILABLE else "Модуль schedule не найден"
    })

    overall_status = all(item["ok"] for item in diagnostics)
    return diagnostics, overall_status


def update_pg_user(username):
    """Update user's Telegram username in PostgreSQL"""
    if not username:
        logger.error("Username is empty")
        return

    conn = get_pg_connection()
    if not conn:
        logger.error("Could not connect to database")
        return

    try:
        cursor = conn.cursor()

        # Проверяем существует ли пользователь
        logger.info(f"Checking if user {username} exists...")
        cursor.execute('SELECT artist FROM label WHERE tg = %s', (username,))
        result = cursor.fetchone()

        if not result:
            # Если пользователя нет, добавляем его только со статусом artist = 1
            logger.info(f"Adding new user {username} with artist status")
            cursor.execute('INSERT INTO label (tg, artist, created_date) VALUES (%s, %s, %s)',
                           (username, 1, datetime.now()))
            logger.info(f"Successfully added user {username}")
        elif result[0] != 1:
            # Если у пользователя нет статуса артиста, устанавливаем artist = 1
            logger.info(f"Updating artist status for user {username}")
            cursor.execute('UPDATE label SET artist = %s WHERE tg = %s', (1, username))
            logger.info(f"Successfully updated artist status for user {username}")

        conn.commit()
        logger.info("Changes committed successfully")
    except Error as e:
        logger.error(f"PostgreSQL error: {e}")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)
            logger.info("Database connection closed")





import random
from datetime import datetime, timedelta
import json
import logging
import os
import re
from sys import exception

import threading
import time
import uuid
import psycopg2
from psycopg2 import Error
from flask import Flask, request, jsonify, session, redirect, url_for

# Для создания Word документов
try:
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("python-docx module not available. Word document generation will be disabled.")

# Для создания Excel файлов
try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    XLSX_AVAILABLE = True
except ImportError:
    XLSX_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("openpyxl module not available. Excel report generation will be disabled.")

# Дополнительные импорты для работы с файлами
import tempfile
import io
from urllib.parse import quote

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv не установлен, используем системные переменные

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Проверяем доступность модуля для планировщика
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("schedule module not available. Scheduled tasks will be disabled.")

import telebot
from telebot import types

# Проверяем доступность модуля для платежей
try:
    from yookassa import Configuration, Payment
    YOOKASSA_AVAILABLE = True
except ImportError:
    YOOKASSA_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("yookassa module not available. Payment functionality will be disabled.")

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Безопасная отправка медиа с обработкой неверных file_id/URL
def send_media_safely(chat_id: int, file_id: str, kind: str, caption: str | None = None) -> bool:
    if not file_id:
        return False

    # Попробуем сначала "ожидаемый" тип, затем универсальный документ
    kinds_order = ['document']
    if kind == 'photo':
        kinds_order = ['photo', 'document']
    elif kind == 'audio':
        kinds_order = ['audio', 'document']
    elif kind == 'document':
        kinds_order = ['document']

    for k in kinds_order:
        try:
            if k == 'photo':
                bot.send_photo(chat_id, file_id, caption=caption)
                return True
            if k == 'audio':
                bot.send_audio(chat_id, file_id, caption=caption)
                return True
            if k == 'document':
                bot.send_document(chat_id, file_id, caption=caption)
                return True
        except Exception as e:
            logger.info(f"send_media_safely attempt {k} failed: {e}")
            continue

    # Если это не URL — попробуем скачать по getFile и отправить как файл
    try:
        if not (isinstance(file_id, str) and file_id.lower().startswith(('http://', 'https://'))):
            tg_file = bot.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{tg_file.file_path}"
            try:
                import requests, tempfile, os
                with requests.get(file_url, stream=True, timeout=20) as r:
                    r.raise_for_status()
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                tmp.write(chunk)
                        temp_path = tmp.name
                with open(temp_path, 'rb') as f:
                    sent = False
                    # Если фото не получилось — как документ в крайнем случае
                    if kind == 'photo':
                        try:
                            bot.send_photo(chat_id, f, caption=caption)
                            sent = True
                        except Exception:
                            bot.send_document(chat_id, f, caption=caption)
                            sent = True
                    elif kind == 'audio':
                        try:
                            bot.send_audio(chat_id, f, caption=caption)
                            sent = True
                        except Exception:
                            bot.send_document(chat_id, f, caption=caption)
                            sent = True
                    else:
                        bot.send_document(chat_id, f, caption=caption)
                        sent = True
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
                if sent:
                    return True
            except Exception as e:
                logger.warning(f"send_media_safely download fallback failed: {e}")
    except Exception as e:
        logger.info(f"send_media_safely get_file failed: {e}")

    # Если это URL — отправим ссылкой, чтобы не падать
    try:
        if isinstance(file_id, str) and file_id.lower().startswith(('http://', 'https://')):
            text = caption + "\n" if caption else ""
            bot.send_message(chat_id, f"{text}{file_id}")
            return True
    except Exception as e:
        logger.warning(f"send_media_safely URL fallback failed: {e}")

    return False


def send_file_smart(chat_id, file_id, caption="", file_type_hint=None, user_id=None):
    """
    Универсальная функция для отправки файлов.
    Автоматически определяет тип файла и использует соответствующий метод.

    Args:
        chat_id: ID чата для отправки
        file_id: Telegram file_id
        caption: Подпись к файлу
        file_type_hint: Подсказка о типе файла ('photo', 'document', 'audio', 'video')
        user_id: ID пользователя для получения информации о типе файла из user_data

    Returns:
        bool: True если файл отправлен успешно, False в случае ошибки
    """
    try:
        # Сначала проверяем user_data для определения типа файла
        if user_id and hasattr(bot, 'user_data') and user_id in bot.user_data:
            user_data = bot.user_data[user_id]
            if 'cover_file_type' in user_data and user_data.get('cover_file_id') == file_id:
                file_type_hint = user_data['cover_file_type']
                logger.info(f"Using file type from user_data: {file_type_hint}")

        if file_type_hint:
            # Если есть подсказка о типе, используем её
            if file_type_hint == 'photo':
                bot.send_photo(chat_id, file_id, caption=caption)
                return True
            elif file_type_hint == 'document':
                bot.send_document(chat_id, file_id, caption=caption)
                return True
            elif file_type_hint == 'audio':
                bot.send_audio(chat_id, file_id, caption=caption)
                return True
            elif file_type_hint == 'video':
                bot.send_video(chat_id, file_id, caption=caption)
                return True

        # Если подсказки нет, пытаемся определить тип по содержимому
        # Для этого нужно получить информацию о файле
        try:
            file_info = bot.get_file(file_id)
            if file_info:
                # Определяем тип по расширению файла
                file_path = file_info.file_path.lower()
                if any(ext in file_path for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    # Это изображение - используем send_photo
                    bot.send_photo(chat_id, file_id, caption=caption)
                    return True
                elif any(ext in file_path for ext in ['.mp3', '.wav', '.flac', '.ogg', '.m4a']):
                    # Это аудио - используем send_audio
                    bot.send_audio(chat_id, file_id, caption=caption)
                    return True
                elif any(ext in file_path for ext in ['.mp4', '.avi', '.mov', '.mkv']):
                    # Это видео - используем send_video
                    bot.send_video(chat_id, file_id, caption=caption)
                    return True
                else:
                    # Для остальных файлов используем send_document
                    bot.send_document(chat_id, file_id, caption=caption)
                    return True
            else:
                # Если не удалось получить информацию о файле, используем send_document как fallback
                bot.send_document(chat_id, file_id, caption=caption)
                return True
        except Exception as e:
            logger.warning(f"Could not determine file type for {file_id}, using send_document as fallback: {e}")
            # Fallback - отправляем как документ
            bot.send_document(chat_id, file_id, caption=caption)
            return True

    except Exception as e:
        logger.error(f"Error sending file {file_id}: {e}")
        # Пытаемся отправить как документ в случае ошибки
        try:
            bot.send_document(chat_id, file_id, caption=caption)
            return True
        except Exception as fallback_error:
            logger.error(f"Fallback send_document also failed for {file_id}: {fallback_error}")
            return False


# --- Balance helpers ---
# Дублирующиеся функции get_user_balance_safe и change_user_balance удалены
# Используются функции из строк 103-140




def get_all_admins():
    return runtime_helpers.get_all_admins()


def is_admin(user_id):
    return runtime_helpers.is_admin(user_id)


def debug_user_data(user_id, step_name="unknown"):
    """Отладочная функция для проверки данных пользователя"""
    user_data = bot.user_data.get(user_id, {})
    logger.info(f"DEBUG [{step_name}] User {user_id} data: {list(user_data.keys())}")
    if 'cover_file_id' in user_data:
        logger.info(f"DEBUG [{step_name}] cover_file_id: {user_data['cover_file_id']}")
    else:
        logger.warning(f"DEBUG [{step_name}] cover_file_id NOT FOUND in user data!")
    return user_data


# Release statuses
RELEASE_STATUSES = [
    "принят",
    "отправлен на площадки",
    "отгружен на площадки",
    "Релиз",
    "Отозван с площадок"
]

# Database configuration - используем переменные окружения или значения по умолчанию
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "60606611125"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}


def init_database():
    """Initialize all database tables in PostgreSQL"""
    conn = get_pg_connection()
    if not conn:
        logger.error("Failed to initialize database")
        return

    try:
        cursor = conn.cursor()
        logger.info("Starting database initialization...")

        # Create label table (main users table)
        logger.info("Creating label table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS label (
                id SERIAL PRIMARY KEY,
                login VARCHAR(255) UNIQUE,
                passvord VARCHAR(255),
                name VARCHAR(255),
                tg VARCHAR(255),
                telegram_id BIGINT UNIQUE,
                kanal TEXT,
                admin INTEGER DEFAULT 0,
                artist INTEGER DEFAULT 1,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                balance NUMERIC(10, 2) DEFAULT 0,
                email TEXT,
                fio TEXT,
                phone VARCHAR(50)
            )
        ''')

        # Create reviews table
        logger.info("Creating reviews table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                service_type TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                text TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create releases table
        logger.info("Creating releases table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS releases (
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
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_album BOOLEAN DEFAULT FALSE,
                is_track BOOLEAN DEFAULT FALSE,
                album_id INTEGER,
                track_number INTEGER,
                upc_code TEXT DEFAULT 'пока что нет'
            )
        ''')

        # Create files table
        logger.info("Creating files table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL CHECK (type IN ('cover', 'audio', 'contract', 'lyrics', 'other')),
                file_id TEXT NOT NULL,
                file_name TEXT,
                file_size BIGINT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                uploaded_by BIGINT NOT NULL
            )
        ''')

        # Create distribution_agreements table
        logger.info("Creating distribution_agreements table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS distribution_agreements (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                agreed BOOLEAN NOT NULL DEFAULT FALSE,
                ip_address INET,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create payments table for tracking payments
        logger.info("Creating payments table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount NUMERIC(10, 2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'RUB',
                service_type TEXT NOT NULL,
                payment_id TEXT UNIQUE,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'succeeded', 'canceled', 'failed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create user_sessions table for tracking user sessions
        logger.info("Creating user_sessions table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                session_data JSONB,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create admin_logs table for admin actions
        logger.info("Creating admin_logs table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT NOT NULL,
                action TEXT NOT NULL,
                target_user_id BIGINT,
                target_release_id INTEGER,
                details JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create orders table for balance top-ups and service orders
        logger.info("Creating orders table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                service_type TEXT NOT NULL CHECK (service_type IN ('topup', 'cover', 'motion', 'videoshot', 'distribution', 'other')),
                amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled', 'failed')),
                payment_id TEXT UNIQUE,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                metadata JSONB
            )
        ''')

        # Create promo codes table
        logger.info("Creating promo codes table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_codes (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                amount NUMERIC(10, 2) NOT NULL,
                discount NUMERIC(10, 2) DEFAULT 0,
                is_used BOOLEAN DEFAULT FALSE,
                used_by BIGINT,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by BIGINT NOT NULL,
                max_uses INTEGER DEFAULT NULL,
                current_uses INTEGER DEFAULT 0,
                expires_at TIMESTAMP DEFAULT NULL,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')

        # Create report requests table
        logger.info("Creating report requests table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS report_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                release_id INTEGER,
                release_type TEXT,
                request_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'rejected')),
                admin_id BIGINT,
                report_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                updated_at TIMESTAMP,
                rejection_reason TEXT,
                notes TEXT
            )
        ''')

        # Create contracts table
        logger.info("Creating contracts table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contracts (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                contract_number VARCHAR(100),
                contract_type VARCHAR(50) DEFAULT 'license',
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'rejected')),
                contract_file_id TEXT,
                admin_id BIGINT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')

        # Create drafts table (черновики релизов)
        logger.info("Creating drafts table...")
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS drafts (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    draft_type VARCHAR(50) NOT NULL,
                    data TEXT NOT NULL,
                    current_step INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON drafts(user_id)")
        except Exception as e:
            logger.warning(f"Could not create drafts table: {e}")

        # Create user_discount_promos (промокоды на скидку, активированные пользователем)
        logger.info("Creating user_discount_promos table...")
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_discount_promos (
                    user_id BIGINT NOT NULL,
                    promo_code_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, promo_code_id),
                    FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id) ON DELETE CASCADE
                )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_discount_promos_user_id ON user_discount_promos(user_id)")
        except Exception as e:
            logger.warning(f"Could not create user_discount_promos table: {e}")

        conn.commit()
        # Add comments to orders table
        try:
            cursor.execute("COMMENT ON TABLE orders IS 'Заказы пользователей и пополнения баланса'")
            cursor.execute("COMMENT ON COLUMN orders.user_id IS 'ID пользователя Telegram'")
            cursor.execute("COMMENT ON COLUMN orders.service_type IS 'Тип услуги: topup (пополнение), cover (обложка), motion (анимация), videoshot (видеошот), distribution (дистрибуция)'")
            cursor.execute("COMMENT ON COLUMN orders.amount IS 'Сумма заказа в рублях'")
            cursor.execute("COMMENT ON COLUMN orders.status IS 'Статус заказа: pending (ожидает), completed (выполнен), cancelled (отменен), failed (ошибка)'")
            cursor.execute("COMMENT ON COLUMN orders.payment_id IS 'Уникальный ID платежа от платежной системы'")
            cursor.execute("COMMENT ON COLUMN orders.description IS 'Описание заказа'")
            cursor.execute("COMMENT ON COLUMN orders.metadata IS 'Дополнительные данные заказа в формате JSON'")
        except Exception as e:
            logger.warning(f"Could not add comments to orders table: {e}")

        # Add missing columns to existing tables
        logger.info("Adding missing columns to existing tables...")

        # Label table columns
        label_columns_to_add = [
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS balance NUMERIC(10, 2) DEFAULT 0",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS email TEXT",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS fio TEXT",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS phone VARCHAR(50)",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS owner INTEGER DEFAULT 0",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS steezy INTEGER DEFAULT 0",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS bibi INTEGER DEFAULT 0",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS shvepz INTEGER DEFAULT 0",
            "ALTER TABLE label ADD COLUMN IF NOT EXISTS creator INTEGER DEFAULT 0"
        ]

        # Report requests table columns
        report_columns_to_add = [
            "ALTER TABLE report_requests ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
            "ALTER TABLE report_requests ADD COLUMN IF NOT EXISTS rejection_reason TEXT"
        ]

        # Modify existing columns
        report_columns_to_modify = [
            "ALTER TABLE report_requests ALTER COLUMN release_type DROP NOT NULL"
        ]

        for column_sql in label_columns_to_add:
            try:
                cursor.execute(column_sql)
                logger.info(f"✅ Added column to label table: {column_sql}")
            except Exception as e:
                logger.warning(f"Could not add column to label table: {e}")

        for column_sql in report_columns_to_add:
            try:
                cursor.execute(column_sql)
                logger.info(f"✅ Added column to report_requests table: {column_sql}")
            except Exception as e:
                logger.warning(f"Could not add column to report_requests table: {e}")

        for column_sql in report_columns_to_modify:
            try:
                cursor.execute(column_sql)
                logger.info(f"✅ Modified column in report_requests table: {column_sql}")
            except Exception as e:
                logger.warning(f"Could not modify column in report_requests table: {e}")

        # Verify all required columns exist and set default values
        try:
            # Check if all required role columns exist
            required_role_columns = ['owner', 'creator']
            for column in required_role_columns:
                cursor.execute(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'label' AND column_name = '{column}'
                """)

                if not cursor.fetchone():
                    # Column doesn't exist, create it manually
                    cursor.execute(f"ALTER TABLE label ADD COLUMN {column} INTEGER DEFAULT 0")
                    logger.info(f"✅ Manually added column {column} to label table")

                # Update existing records to set default values
                cursor.execute(f"UPDATE label SET {column} = 0 WHERE {column} IS NULL")
                logger.info(f"✅ Updated default values for column {column}")

            # Migrate old role columns to new ones if they exist
            old_role_columns = ['moderator', 'support', 'premium', 'verified', 'vip']
            for old_column in old_role_columns:
                cursor.execute(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'label' AND column_name = '{old_column}'
                """)

                if cursor.fetchone():
                    # Old column exists, migrate data and drop it
                    logger.info(f"🔄 Migrating data from {old_column} column...")

                    # Map old columns to new ones (you can customize this mapping)
                    if old_column == 'moderator':
                        cursor.execute("UPDATE label SET owner = moderator WHERE owner = 0 AND moderator = 1")
                    elif old_column == 'support':
                        cursor.execute("UPDATE label SET steezy = support WHERE steezy = 0 AND support = 1")
                    elif old_column == 'premium':
                        cursor.execute("UPDATE label SET bibi = premium WHERE bibi = 0 AND premium = 1")
                    elif old_column == 'verified':
                        cursor.execute("UPDATE label SET shvepz = verified WHERE shvepz = 0 AND verified = 1")
                    elif old_column == 'vip':
                        cursor.execute("UPDATE label SET creator = vip WHERE creator = 0 AND vip = 1")

                    # Drop old column
                    cursor.execute(f"ALTER TABLE label DROP COLUMN {old_column}")
                    logger.info(f"✅ Dropped old column {old_column}")

        except Exception as e:
            logger.warning(f"Could not verify role columns: {e}")

        # Releases table columns
        releases_columns_to_add = [
            "ALTER TABLE releases ADD COLUMN IF NOT EXISTS is_album BOOLEAN DEFAULT FALSE",
            "ALTER TABLE releases ADD COLUMN IF NOT EXISTS is_track BOOLEAN DEFAULT FALSE",
            "ALTER TABLE releases ADD COLUMN IF NOT EXISTS album_id INTEGER",
            "ALTER TABLE releases ADD COLUMN IF NOT EXISTS track_number INTEGER",
            "ALTER TABLE releases ADD COLUMN IF NOT EXISTS upc_code TEXT DEFAULT 'пока что нет'"
        ]

        for column_sql in releases_columns_to_add:
            try:
                cursor.execute(column_sql)
            except Exception as e:
                logger.warning(f"Could not add column to releases table: {e}")

        # Files table columns
        files_columns_to_add = [
            "ALTER TABLE files ADD COLUMN IF NOT EXISTS file_name TEXT",
            "ALTER TABLE files ADD COLUMN IF NOT EXISTS file_size BIGINT",
            "ALTER TABLE files ADD COLUMN IF NOT EXISTS upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ]

        for column_sql in files_columns_to_add:
            try:
                cursor.execute(column_sql)
            except Exception as e:
                logger.warning(f"Could not add column to files table: {e}")

        # Orders table columns
        orders_columns_to_add = [
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS metadata JSONB"
        ]

        for column_sql in orders_columns_to_add:
            try:
                cursor.execute(column_sql)
            except Exception as e:
                logger.warning(f"Could not add column to orders table: {e}")

        # Promo codes table columns - handle existing table structure
        try:
            # Check if all required columns exist
            required_columns = ['amount', 'discount', 'is_used', 'created_by']
            for column in required_columns:
                cursor.execute(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'promo_codes' AND column_name = '{column}'
                """)

                if not cursor.fetchone():
                    # Column doesn't exist, add it
                    if column == 'amount':
                        cursor.execute("ALTER TABLE promo_codes ADD COLUMN amount NUMERIC(10, 2) DEFAULT 0")
                        cursor.execute("UPDATE promo_codes SET amount = 0 WHERE amount IS NULL")
                    elif column == 'discount':
                        cursor.execute("ALTER TABLE promo_codes ADD COLUMN discount NUMERIC(10, 2) DEFAULT 0")
                        cursor.execute("UPDATE promo_codes SET discount = 0 WHERE discount IS NULL")
                    elif column == 'is_used':
                        cursor.execute("ALTER TABLE promo_codes ADD COLUMN is_used BOOLEAN DEFAULT FALSE")
                        cursor.execute("UPDATE promo_codes SET is_used = FALSE WHERE is_used IS NULL")
                    elif column == 'created_by':
                        cursor.execute("ALTER TABLE promo_codes ADD COLUMN created_by BIGINT DEFAULT 0")
                        cursor.execute("UPDATE promo_codes SET created_by = 0 WHERE created_by IS NULL")

                    logger.info(f"✅ Added column {column} to promo_codes table")
                else:
                    logger.info(f"✅ Column {column} already exists in promo_codes table")

        except Exception as e:
            logger.warning(f"Could not handle promo_codes table structure: {e}")
            # Try to recreate the table if there are issues
            try:
                cursor.execute("DROP TABLE IF EXISTS promo_codes CASCADE")
                cursor.execute('''
                    CREATE TABLE promo_codes (
                        id SERIAL PRIMARY KEY,
                        code TEXT UNIQUE NOT NULL,
                        amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
                        discount NUMERIC(10, 2) DEFAULT 0,
                        is_used BOOLEAN DEFAULT FALSE,
                        used_by BIGINT,
                        used_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by BIGINT NOT NULL,
                        max_uses INTEGER DEFAULT NULL,
                        current_uses INTEGER DEFAULT 0,
                        expires_at TIMESTAMP DEFAULT NULL,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                ''')
                logger.info("✅ Recreated promo_codes table with correct structure")
            except Exception as recreate_error:
                logger.error(f"Failed to recreate promo_codes table: {recreate_error}")

        # Create indexes for better performance
        logger.info("Creating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_label_telegram_id ON label(telegram_id)",
            "CREATE INDEX IF NOT EXISTS idx_label_tg ON label(tg)",
            "CREATE INDEX IF NOT EXISTS idx_releases_user_id ON releases(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_releases_status ON releases(status)",
            "CREATE INDEX IF NOT EXISTS idx_releases_release_date ON releases(release_date)",
            "CREATE INDEX IF NOT EXISTS idx_releases_album_id ON releases(album_id)",
            "CREATE INDEX IF NOT EXISTS idx_files_uploaded_by ON files(uploaded_by)",
            "CREATE INDEX IF NOT EXISTS idx_files_type ON files(type)",
            "CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status)",
            "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)",
            "CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_id ON admin_logs(admin_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
            "CREATE INDEX IF NOT EXISTS idx_orders_payment_id ON orders(payment_id)",
            "CREATE INDEX IF NOT EXISTS idx_orders_created_date ON orders(created_date)",
            "CREATE INDEX IF NOT EXISTS idx_orders_service_type ON orders(service_type)",
            "CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code)",
            "CREATE INDEX IF NOT EXISTS idx_promo_codes_is_used ON promo_codes(is_used)",
            "CREATE INDEX IF NOT EXISTS idx_report_requests_user_id ON report_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_report_requests_status ON report_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_report_requests_release_id ON report_requests(release_id)"
        ]

        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
            except Exception as e:
                logger.warning(f"Could not create index: {e}")

        # Insert permanent admins if they don't exist
        logger.info("Setting up permanent admins...")
        for admin_id in PERMANENT_ADMINS:
            try:
                cursor.execute('''
                    INSERT INTO label (telegram_id, admin, artist, created_date, tg)
                    VALUES (%s, 1, 1, CURRENT_TIMESTAMP, 'admin_' || %s)
                    ON CONFLICT (telegram_id) DO UPDATE SET admin = 1
                ''', (admin_id, admin_id))
            except Exception as e:
                logger.warning(f"Could not set up admin {admin_id}: {e}")

        conn.commit()
        logger.info("✅ Database initialization completed successfully - all tables created with indexes")

    except Error as e:
        logger.error(f"❌ Error creating database tables: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        logger.error(f"❌ Unexpected error during database initialization: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            return_pg_connection(conn)


def fix_promo_codes_table():
    """Fix promo_codes table structure by ensuring all required columns exist"""
    logger.info("Fixing promo_codes table structure...")
    conn = get_pg_connection()
    if not conn:
        logger.error("Cannot fix promo_codes table - no connection")
        return False

    try:
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'promo_codes'
            )
        """)

        if not cursor.fetchone()[0]:
            logger.info("Creating promo_codes table...")
            cursor.execute('''
                CREATE TABLE promo_codes (
                    id SERIAL PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    discount NUMERIC(10, 2) DEFAULT 0,
                    is_used BOOLEAN DEFAULT FALSE,
                    used_by BIGINT,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by BIGINT NOT NULL DEFAULT 0,
                    max_uses INTEGER DEFAULT NULL,
                    current_uses INTEGER DEFAULT 0,
                    expires_at TIMESTAMP DEFAULT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            conn.commit()
            logger.info("✅ promo_codes table created successfully")
            return True

        # Add missing columns
        required_columns = {
            'amount': 'NUMERIC(10, 2) DEFAULT 0',
            'discount': 'NUMERIC(10, 2) DEFAULT 0',
            'is_used': 'BOOLEAN DEFAULT FALSE',
            'created_by': 'BIGINT DEFAULT 0',
            'used_by': 'BIGINT',
            'used_at': 'TIMESTAMP',
            'max_uses': 'INTEGER DEFAULT NULL',
            'current_uses': 'INTEGER DEFAULT 0',
            'expires_at': 'TIMESTAMP DEFAULT NULL',
            'is_active': 'BOOLEAN DEFAULT TRUE'
        }

        for column, definition in required_columns.items():
            cursor.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'promo_codes' AND column_name = '{column}'
            """)

            if not cursor.fetchone():
                logger.info(f"Adding missing column: {column}")
                cursor.execute(f"ALTER TABLE promo_codes ADD COLUMN {column} {definition}")

        conn.commit()
        logger.info("✅ promo_codes table structure fixed successfully")
        return True

    except Exception as e:
        logger.error(f"Error fixing promo_codes table: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            return_pg_connection(conn)


def check_database_integrity():
    """Check database integrity and create missing tables/columns"""
    logger.info("Checking database integrity...")
    conn = get_pg_connection()
    if not conn:
        logger.error("Cannot check database integrity - no connection")
        return False

    try:
        cursor = conn.cursor()

        # Check if all required tables exist
        required_tables = [
            'label', 'releases', 'reviews', 'files',
            'distribution_agreements', 'payments',
            'user_sessions', 'admin_logs', 'orders', 'promo_codes', 'report_requests'
        ]

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        existing_tables = [row[0] for row in cursor.fetchall()]

        missing_tables = [table for table in required_tables if table not in existing_tables]

        if missing_tables:
            logger.warning(f"Missing tables detected: {missing_tables}")
            logger.info("Reinitializing database...")
            return_pg_connection(conn)
            init_database()
            return True
        else:
            logger.info("✅ All required tables exist")

        # Check for required columns in critical tables
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'label' AND table_schema = 'public'
        """)
        label_columns = [row[0] for row in cursor.fetchall()]

        required_label_columns = ['telegram_id', 'admin', 'balance', 'created_date', 'owner', 'creator']
        missing_label_columns = [col for col in required_label_columns if col not in label_columns]

        if missing_label_columns:
            logger.warning(f"Missing columns in label table: {missing_label_columns}")
            logger.info("Adding missing columns to label table...")

            # Add missing columns
            for column in missing_label_columns:
                if column in ['owner', 'creator']:
                    try:
                        cursor.execute(f"ALTER TABLE label ADD COLUMN {column} INTEGER DEFAULT 0")
                        cursor.execute(f"UPDATE label SET {column} = 0 WHERE {column} IS NULL")
                        logger.info(f"✅ Added column {column} to label table")
                    except Exception as e:
                        logger.warning(f"Could not add column {column}: {e}")
                else:
                    try:
                        if column == 'balance':
                            cursor.execute("ALTER TABLE label ADD COLUMN balance NUMERIC(10, 2) DEFAULT 0")
                        elif column == 'created_date':
                            cursor.execute("ALTER TABLE label ADD COLUMN created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                        logger.info(f"✅ Added column {column} to label table")
                    except Exception as e:
                        logger.warning(f"Could not add column {column}: {e}")

            conn.commit()
            logger.info("✅ Label table structure updated")

        # Check orders table structure
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'orders' AND table_schema = 'public'
        """)
        orders_columns = [row[0] for row in cursor.fetchall()]

        required_orders_columns = ['id', 'user_id', 'service_type', 'amount', 'status', 'payment_id', 'created_date']
        missing_orders_columns = [col for col in required_orders_columns if col not in orders_columns]

        if missing_orders_columns:
            logger.warning(f"Missing columns in orders table: {missing_orders_columns}")
            return_pg_connection(conn)
            init_database()
            return True

        # Check promo_codes table structure
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'promo_codes' AND table_schema = 'public'
        """)
        promo_codes_columns = [row[0] for row in cursor.fetchall()]

        required_promo_codes_columns = ['id', 'code', 'amount', 'is_used', 'created_by']
        missing_promo_codes_columns = [col for col in required_promo_codes_columns if col not in promo_codes_columns]

        if missing_promo_codes_columns:
            logger.warning(f"Missing columns in promo_codes table: {missing_promo_codes_columns}")
            return_pg_connection(conn)
            init_database()
            return True

        logger.info("✅ Database integrity check passed")
        return True

    except Exception as e:
        logger.error(f"Database integrity check failed: {e}")
        return False
    finally:
        if conn:
            return_pg_connection(conn)


def migrate_orders_data():
    """Migrate any existing order data if needed"""
    logger.info("Checking for orders data migration...")
    conn = get_pg_connection()
    if not conn:
        logger.warning("Cannot check orders migration - no connection")
        return

    try:
        cursor = conn.cursor()

        # Check if orders table exists and has data
        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_count = cursor.fetchone()[0]

        if orders_count == 0:
            logger.info("Orders table is empty - no migration needed")
        else:
            logger.info(f"Found {orders_count} existing orders")

        # Add any missing columns to orders table if needed
        orders_columns_to_add = [
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS metadata JSONB"
        ]

        for column_sql in orders_columns_to_add:
            try:
                cursor.execute(column_sql)
            except Exception as e:
                logger.warning(f"Could not add column to orders table: {e}")

        conn.commit()
        logger.info("✅ Orders migration completed")

    except Exception as e:
        logger.error(f"Orders migration failed: {e}")
    finally:
        if conn:
            return_pg_connection(conn)



# Обновленная функция process_track_audio (единая логика: после аудио спрашиваем текст трека)

# Редактирование одного поля: после ввода нового значения сразу показываем превью (не цепочку шагов)
def create_admin_notification(release_info):
    """Create detailed notification message for admins"""
    return notifications.create_admin_notification_message(release_info, BOT_TOKEN)


def notify_all_admins(message_text):
    """Send notification to all admins"""
    notifications.notify_all_admins(bot, get_all_admins(), message_text, logger)



def create_main_menu():
    """Create main menu keyboard"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "🎵 Наши услуги",
        "👤 Мой профиль",
        # "📋 Получить договор",  # Временно отключено
        "⭐️ Отзывы",
        "❓ Помощь/вопросы",
        "🌐 Открыть приложение"
    ]
    markup.add(*[types.KeyboardButton(btn) for btn in buttons])
    return markup



def notify_admins_about_new_release(user_id, release_id):
    """Notify admins about new release submission"""
    notifications.notify_admins_about_new_release(
        bot,
        user_id,
        release_id,
        get_pg_connection,
        return_pg_connection,
        logger,
    )


def notify_admins_about_report_request(user_id, report_id, user_name, username):
    """Notify admins about new report request"""
    notifications.notify_admins_about_report_request(
        bot,
        user_id,
        report_id,
        user_name,
        username,
        get_pg_connection,
        return_pg_connection,
        logger,
    )



def has_access_level(user_id, required_levels):
    """Check if user has required access level using Telegram ID, not username"""
    conn = None
    cur = None
    try:
        logger.info(f"Starting access level check for user_id: {user_id}")

        # Сначала проверяем список постоянных админов
        if user_id in PERMANENT_ADMINS:
            logger.info(f"User {user_id} is a permanent admin")
            return True

        # Подключаемся к базе данных
        conn = get_pg_connection()
        if not conn:
            logger.error("Failed to connect to database")
            return False
        cur = conn.cursor()

        # Проверяем флаг admin по telegram_id
        cur.execute("SELECT admin FROM label WHERE telegram_id = %s", (user_id,))
        result = cur.fetchone()
        logger.info(f"Admin flag by telegram_id result: {result}")

        return bool(result and result[0] == 1)

    except Exception as e:
        logger.error(f"Error checking access level: {e}")
        return False
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                return_pg_connection(conn)
        except Exception:
            pass



# Дублированная функция admin_panel удалена - используется admin_panel на строке 3372


# Дублированный обработчик удален - используется admin_panel_handler на строке 3451


def handle_admin_reviews(call):
    """Show admin reviews menu with moderation and list options"""
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⏳ Ждут одобрения", callback_data="admin_reviews_pending"),
        types.InlineKeyboardButton("📚 Все отзывы", callback_data="admin_reviews_all"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
    )

    bot.edit_message_text(
        "📝 Управление отзывами:\n\nВыберите список:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )



def handle_admin_stats(call):
    """Handle statistics display"""
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных")
        return

    try:
        cursor = conn.cursor()

        # Get basic statistics
        cursor.execute('SELECT COUNT(*) FROM label WHERE telegram_id IS NOT NULL')
        result = cursor.fetchone()
        total_users = result[0] if result else 0

        # Для других статистик вам нужно будет добавить соответствующие таблицы в PostgreSQL
        cursor.execute('SELECT COUNT(*) FROM releases WHERE status = %s', ('Релиз',))
        result = cursor.fetchone()
        total_releases = result[0] if result else 0

        # Получаем количество записей в студии (с обработкой ошибок, если таблица не существует)
        total_bookings = 0
        try:
            cursor.execute('SELECT COUNT(*) FROM studio_bookings WHERE status = %s', ('completed',))
            result = cursor.fetchone()
            total_bookings = result[0] if result else 0
        except Exception as e:
            logger.warning(f"Таблица studio_bookings не найдена: {e}")
            total_bookings = 0
        # Получаем общий оборот (с обработкой ошибок, если таблица не существует)
        total_revenue = 0
        try:
            cursor.execute('SELECT SUM(amount) FROM orders WHERE status = %s', ('completed',))
            result = cursor.fetchone()
            total_revenue = float(result[0]) if result and result[0] else 0
        except Exception as e:
            logger.warning(f"Ошибка при получении оборота: {e}")
            total_revenue = 0
        # Получаем количество отзывов (с обработкой ошибок, если таблица не существует)
        total_reviews = 0
        try:
            cursor.execute('SELECT COUNT(*) FROM reviews WHERE status = %s', ('approved',))
            result = cursor.fetchone()
            total_reviews = result[0] if result else 0
        except Exception as e:
            logger.warning(f"Таблица reviews не найдена: {e}")
            total_reviews = 0
        # Get new users in last week
        week_ago = (datetime.now() - timedelta(days=7))
        # Assuming 'created_date' exists in 'label' table for user registration date
        cursor.execute('SELECT COUNT(*) FROM label WHERE created_date > %s', (week_ago,))
        result = cursor.fetchone()
        new_users_week = result[0] if result else 0

        stats_text = (
            "📊 Статистика TWAS Label\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"📀 Отгруженных релизов: {total_releases}\n"
            f"🎧 Записей в студии: {total_bookings}\n"
            f"💰 Общий оборот: {total_revenue:,.2f}₽\n"
            f"⭐️ Отзывов: {total_reviews}\n"
            f"📈 Новых пользователей за неделю: {new_users_week}\n"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        periods = [
            ("За неделю", "stats_week"),
            ("За месяц", "stats_month"),
            ("За все время", "stats_all")
        ]

        for text, callback in periods:
            markup.add(types.InlineKeyboardButton(text, callback_data=callback))

        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))

        bot.edit_message_text(
            stats_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    except Error as e:
        logger.error(f"Error in admin stats: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка при получении статистики: {e}")

    finally:
        if conn:
            return_pg_connection(conn)





def handle_level_management(call):
    """Handle level management actions"""
    action = call.data.split("_")[1]

    if action == "add":
        bot.edit_message_text(
            "Введите ID пользователя и уровень через пробел (например: 123456789 admin):",
            call.message.chat.id,
            call.message.message_id
        )
        bot.register_next_step_handler(call.message, process_level_add)

    elif action == "remove":
        bot.edit_message_text(
            "Введите ID пользователя и уровень для удаления через пробел:",
            call.message.chat.id,
            call.message.message_id
        )
        bot.register_next_step_handler(call.message, process_level_remove)

    elif action == "list":
        show_users_by_level(call.message)


def process_level_add(message):
    """Process level addition"""
    try:
        user_id_str, level = message.text.split()
        user_id = int(user_id_str)

        # Check if level exists
        if level not in USER_LEVELS:
            bot.reply_to(message, f"❌ Уровень {level} не существует")
            return

        # Check if trying to set owner level
        if level == "owner" and message.from_user.username != "realjustci":
            bot.reply_to(message, "❌ Только @realjustci может назначать уровень owner")
            return

        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
            return
        cursor = conn.cursor()

        # Get current role from label table
        cursor.execute('SELECT role FROM label WHERE telegram_id = %s', (user_id,))
        result = cursor.fetchone()

        if not result:
            bot.reply_to(message, "❌ Пользователь не найден")
            return

        current_role = result[0]  # Assuming role is a single string

        if current_role != level:  # If existing role is different from new level
            cursor.execute('UPDATE label SET role = %s WHERE telegram_id = %s', (level, user_id))
            conn.commit()
            bot.reply_to(message, f"✅ Уровень {level} успешно добавлен")
            # Notify user about level change (optional, depending on desired behavior)
            # notify_level_change(user_id, [level], [current_role]) # Needs implementation for single role
        else:
            bot.reply_to(message, f"ℹ️ Пользователь уже имеет уровень {level}")

    except ValueError:
        bot.reply_to(message, "❌ Неверный формат. Используйте: ID уровень")
    except Error as e:
        logger.error(f"PostgreSQL error in process_level_add: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при сохранении уровня.")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn:
            return_pg_connection(conn)


def process_level_remove(message):
    """Process level removal"""
    try:
        user_id_str, level = message.text.split()
        user_id = int(user_id_str)

        # Check if trying to remove owner level
        if level == "owner" and message.from_user.username != "realjustci":
            bot.reply_to(message, "❌ Только @realjustci может управлять уровнем owner")
            return

        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
            return
        cursor = conn.cursor()

        # Get current role from label table
        cursor.execute('SELECT role FROM label WHERE telegram_id = %s', (user_id,))
        result = cursor.fetchone()

        if not result:
            bot.reply_to(message, "❌ Пользователь не найден")
            return

        current_role = result[0]

        if current_role == level:  # If current role matches the level to remove
            # For now, let's set role to 'artist' if owner or admin is removed
            # You might want a more sophisticated role management or a NULL role
            new_role = "artist" if level in ["owner", "admin"] else None  # Or a default role
            cursor.execute('UPDATE label SET role = %s WHERE telegram_id = %s', (new_role, user_id))
            conn.commit()
            bot.reply_to(message, f"✅ Уровень {level} успешно удален")
            # Notify user about level change (optional)
            # notify_level_change(user_id, [new_role] if new_role else [], [current_role])
        else:
            bot.reply_to(message, f"ℹ️ У пользователя нет уровня {level}")

    except ValueError:
        bot.reply_to(message, "❌ Неверный формат. Используйте: ID уровень")
    except Error as e:
        logger.error(f"PostgreSQL error in process_level_remove: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при удалении уровня.")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn:
            return_pg_connection(conn)


def show_users_by_level(message):
    """Show users grouped by level"""
    conn = get_pg_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
        return

    try:
        cursor = conn.cursor()

        # Get all users and their roles from label table
        cursor.execute('SELECT telegram_id, tg, role FROM label WHERE role IS NOT NULL')
        users = cursor.fetchall()

        # Group users by level
        users_by_level = {}
        for user_id, username, role in users:
            if role not in users_by_level:
                users_by_level[role] = []
            users_by_level[role].append(f"@{username}" if username else f"ID: {user_id}")

        # Prepare message
        message_text = "👥 Пользователи по уровням:\n\n"
        for level in sorted(users_by_level.keys(), key=lambda x: USER_LEVELS.get(x, 999)):
            users_list = users_by_level[level]
            message_text += f"🔹 {level} ({len(users_list)}):\n"
            message_text += ", ".join(users_list) + "\n\n"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))

        bot.edit_message_text(
            message_text,
            message.chat.id,
            message.message_id,
            reply_markup=markup
        )
    except Error as e:
        logger.error(f"PostgreSQL error in show_users_by_level: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при получении списка пользователей.")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn:
            return_pg_connection(conn)



# Кнопки главного меню — для проверки выхода из пошагового ввода поддержки


def send_web_app_link(chat_id, user_id=None):
    """Отправка ссылки на веб-приложение с автоматической авторизацией"""
    # Если user_id не передан, пытаемся получить из chat_id (если это одно и то же)
    if user_id is None:
        user_id = chat_id

    # Добавляем telegram_id в URL для автоматической авторизации
    web_app_url = f"{WEB_APP_URL}?tgid={user_id}"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "🌐 Открыть приложение",
        web_app=types.WebAppInfo(url=web_app_url)
    ))
    bot.send_message(
        chat_id,
        "Запускаю приложение TWAS. Если окно не открылось, обновите Telegram до последней версии.",
        reply_markup=markup
    )


@require_channel_subscription
def handle_open_web_app(message):
    """Handle main menu button for WebApp"""
    send_web_app_link(message.chat.id, message.from_user.id)





@require_channel_subscription
def handle_services_menu(message):
    """Handle services menu"""
    services_text = (
        "🎵 Наши услуги:\n\n"
        "1. 🎵 Дистрибуция музыки - размещение вашего трека на всех площадках\n"
        "2. 🎨 Обложка - профессиональный дизайн обложки для релиза\n"
        "3. 🎬 Motion обложка - анимированная обложка для соцсетей\n"
        "4. 🎥 Видеошот - короткий вертикальный клип\n\n"
        "Выберите интересующую вас услугу:"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        ("🎵 Дистрибуция", "service_distribution"),
        ("🎨 Обложка", "service_cover"),
        ("🎬 Motion обложка", "service_motion"),
        ("🎥 Видеошот", "service_videoshot"),
    ]

    # Добавляем кнопку выгрузки релиза только для администраторов
    if is_admin(message.from_user.id):
        buttons.append(("📤 Выгрузка релиза за артиста", "service_release_for_artist"))

    buttons.append(("◀️ Назад", "services_back"))

    for text, callback in buttons:
        markup.add(types.InlineKeyboardButton(text, callback_data=callback))

    bot.reply_to(message, services_text, reply_markup=markup)

    # Напоминание о промокоде на скидку, если у пользователя есть активный
    user_id = message.from_user.id
    conn = get_pg_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM user_discount_promos udp
                JOIN promo_codes pc ON pc.id = udp.promo_code_id AND pc.is_active = TRUE
                WHERE udp.user_id = %s
                AND (pc.expires_at IS NULL OR pc.expires_at > CURRENT_TIMESTAMP)
                LIMIT 1
            """, (user_id,))
            if cursor.fetchone():
                bot.send_message(
                    message.chat.id,
                    "💡 У вас есть промокод на скидку! Он будет доступен при оплате дистрибуции (кнопка «Использовать промокод»)."
                )
            cursor.close()
        except Exception as e:
            logger.warning(f"Could not check user discount promos: {e}")
        finally:
            return_pg_connection(conn)


# Удаляем дублирующуюся функцию - она заменена на request_contract_file ниже
# @bot.callback_query_handler(func=lambda call: call.data == "admin_upload_contract")
# def handle_upload_contract(call):
#     """Handle contract upload"""
#     bot.edit_message_text(
#         "Отправьте файл договора в формате PDF или DOCX",
#         call.message.chat.id,
#         call.message.message_id
#     )
#     bot.register_next_step_handler(call.message, save_contract_file)





# ===== ФУНКЦИИ ДЛЯ СОЗДАНИЯ ЛИЦЕНЗИОННОГО ДОГОВОРА =====

def create_license_agreement(user_data):
    """Создание полного лицензионного договора согласно новому шаблону"""
    # Проверяем доступность библиотеки python-docx
    if not DOCX_AVAILABLE:
        raise ValueError("Библиотека python-docx не установлена. Обратитесь к администратору.")

    try:
        # Создаем документ
        doc = Document()
        logger.info("Document class is available")
    except Exception as e:
        logger.error(f"Error creating Document: {e}")
        raise ValueError(f"Ошибка при работе с библиотекой python-docx: {e}")

    # Проверяем наличие необходимых данных
    if not user_data:
        raise ValueError("Данные пользователя не переданы")

    # Настройка стилей
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(12)

    # Полный текст нового договора
    contract_template = """ЛИЦЕНЗИОННЫЙ ДОГОВОР № X/-XX


г. Екатеринбург                                                                                                                        01 января 2025 года

Гражданин Российской Федерации {full_name}, паспорт серия и номер: {passport} (творческий псевдоним - «{nickname}»), действующий от своего имени, именуемый в дальнейшем «Лицензиар», с одной стороны и самозанятый Чабин Илья Анатольевич в лице Генерального директора talk with a star label, действующей на основании Устава, именуемой в дальнейшем «Лицензиат», с другой стороны, вместе именуемые «Стороны», заключили настоящий Лицензионный договор (далее по тексту Договор) о нижеследующем:

Термины и определения, используемые в настоящем Договоре
Стороны пришли к соглашению о том, что указанные ниже термины (как в единственном, так и во множественном числе) будут иметь следующие значения:
1.	«Произведения» - музыкальные произведения с текстом, наименования, а также имена/творческие псевдонимы авторов текста и музыки, которых указаны в Приложении № 1 к Договору. Для целей настоящего Договора к понятию «Произведения» относятся также любые самостоятельные части «Произведений», включая их названия, которые в соответствии с действующим законодательством относятся к объектам авторского права.
2.	«Исполнения» - представление Исполнителями Произведений посредством пения, игры на музыкальных инструментах. Перечень Исполнений указан в Приложении № 1 к Договору.
3.	«Фонограммы» - звуковые записи Исполнений Произведений. Перечень Фонограмм указан в Приложении № 1 к Договору.
4.	«Дизайн-макеты» - готовые полиграфические оформления обложек Альбомов, представленные в Приложении № 2 к настоящему Договору.
5.	«Видеоклипы» - аудиовизуальные произведения (как в единственном, так и во множественном числе), состоящие из зафиксированной серии связанных между собой изображений (с сопровождением или без сопровождения звуком) и предназначенные для зрительного и слухового (в случае сопровождения звуком) восприятия с помощью соответствующих технических устройств, названия которых указаны в Приложении № 1 к Договору.
6.	«Объекты» - собирательно Произведения, Исполнения, Фонограммы, Видеоклипы и Дизайн-макеты.
7.	«Исполнители» – перечень Исполнителей указан в Приложении № 1 к Договору.
8.	«Срок» – 5 (пять) лет с даты подписания Сторонами Акта приема-передачи Объектов.
9.	«Территория» – весь мир без каких-либо изъятий и ограничений.
10.	«Альбом» – совокупность Фонограмм, содержащих записи Исполнений Произведений, представленных в определенной последовательности и длительности звучания. Содержание Альбомов указано в Приложении № 1 к Договору.
11.	«Контент» – Объекты, переработанные в цифровой формат (в том числе в форматы MP2, MP3, MP4, WMA, MMF, AAC, MIDI и любые иные форматы, которые существуют и могут быть использованы в дальнейшем в период действия настоящего Договора, для предоставления абонентам сетей передачи данных и сетей мобильной, телефонной, спутниковой, телевизионной, кабельной связи и/или посредством ресурсов сети Интернет в цифровом виде, и потребляемые с использованием компьютеров, ноутбуков и других цифровых устройств (ЭВМ).

Статья 1. Предмет Договора
1.1.	Лицензиар предоставляет Лицензиату за вознаграждение на Срок и на Территории Право на использование Объектов.
1.2.	Лицензиар разрешает Лицензиату предоставлять иным лицам на Территории в течение Срока Право на использование Объектов способами, предусмотренными настоящим Договором (заключение сублицензионных договоров), без предварительного согласия Лицензиара.

Статья 2. Гарантии Сторон
2.1.	Гарантии и обязанности Лицензиара:
2.1.1.	Лицензиар гарантирует, что он вправе распоряжаться Правом на использование Объектов, а именно предоставлять исключительную лицензию на использование Произведений, Исполнений, Фонограмм, Видеоклипов и неисключительную лицензию на использование Дизайн-макетов и иные права, предусмотренные настоящим Договором.
2.1.2.	Лицензиар гарантирует, что заключение настоящего Договора и исполнение по нему всех обязательств не противоречит и не нарушает какие-либо права и интересы третьих лиц.
2.1.3.	Лицензиар гарантирует свободное и никем не ограниченное право Лицензиата и/или его контрагентов и/или его правопреемников использовать Объекты на Территории в течение Срока.
2.1.4.	В случае если хотя бы одна из гарантий Лицензиара, указанных в пункте 2.1 настоящего Договора будет нарушена, Лицензиар обязан выплатить Лицензиату штраф в размере 500$ (Пятьсот долларов США) за каждый указанный случай и возместить все убытки Лицензиата, возникшие в результате нарушения таких гарантий.
2.1.5.	В случае предъявления Лицензиату и/или его контрагентам и/или его правопреемникам претензий или исков в связи с использованием Объектов, Лицензиар обязан урегулировать все возможные претензии и иски своими силами и за свой счет, без привлечения Лицензиата, а также обязан возместить Лицензиату все понесенные им убытки, включая упущенную выгоду.
2.1.6.	Лицензиар обязуется в течение 10 (Десяти) рабочих дней с даты заключения Договора предоставить Лицензиату копии и/или сканированные копии всех необходимых документов (договоров, лицензий, соглашений и т.п.), подтверждающих у него наличие права предоставлять Право на использование Объектов и иные права, предусмотренные настоящим Договором.
2.1.7.	В течение Срока и на Территории Лицензиар не вправе самостоятельно использовать Произведения, Исполнения, Фонограммы, Видеоклипы способами, указанными в настоящем Договоре, не вправе пользоваться правами, переданными Лицензиату в соответствии с п. 1.4 настоящего Договора.
2.1.8 Любая сделка совершенная Лицензиаром с Произведениями, указанными в Договоре, как продажа авторских прав, отчуждение своих прав и иные, считаются недействительными и являются прямым нарушением Договора.
2.2.	Гарантии и обязанности Лицензиата:
2.2.1.	Лицензиат несет ответственность перед Лицензиаром за действия сублицензиатов.
2.2.2.	Лицензиат гарантирует своевременную и полную выплату вознаграждения, согласованного Сторонами в Статье 3 настоящего Договора.
2.2.3.	Лицензиат обязуется при использовании Объектов указывать следующее: © & ℗ talk with a star label и указывать в публикации к релизу «label: talk with a star»
2.2.4.	В исключение из п. 2.2.3 настоящего Договора Стороны договорились о том, что в случае затруднительности для Лицензиата и/или его контрагентов указания данной информации, а также имени и/или творческого псевдонима Лицензиара и/или Исполнителей и/или авторов Объектов, такая информация указываться не будет.

Статья 3. Вознаграждение
3.1.	За предоставление Права на использование Объектов, а также иных прав, установленных в настоящем Договоре, Лицензиат выплачивает Лицензиару вознаграждение, согласованное Сторонами в Приложении № 3 к Договору.

Статья 4. Порядок предоставления отчетов об использовании Объектов
4.1.	Лицензиат один раз в квартал, в течение 45 (Сорока пяти) календарных дней после окончания Отчетного периода, или по факту получения платежей от контрагентов, представляет Лицензиару Отчет об использовании Объектов (далее «Отчет») .
4.2.	В Отчете Лицензиата указывается доход, полученный Лицензиатом от использования Объектов и выдачи сублицензий, а также размер вознаграждения Лицензиара.

Статья 5. Срок заключения Договора. Порядок его расторжения
5.1.	Настоящий Договор вступает в силу со дня его подписания и действует в течение Срока.
5.2.	Настоящий Договор может быть расторгнут только по взаимному соглашению обеих Сторон.

Статья 6. Прочие условия.
6.1.	Все споры между Сторонами подлежат разрешению путем совместных между Сторонами переговоров.
6.2.	Если Стороны не пришли к соглашению путем переговоров, все возникшие разногласия разрешаются в судебном порядке в соответствии с законодательством Республики Армении по месту нахождения Лицензиата.
6.3.	Стороны определили, что условия о вознаграждении Лицензиара, указанные в Приложении № 3 к настоящему Договору, являются конфиденциальными условиями и подлежат разглашению третьим лицам только с письменного согласия обеих Сторон.
6.4 За распространение ложной, вводящей в заблуждение, подстрекающей к противоправным действиям информации, распространение информации, которая выражает неуважительное и негативное отношение порочащее честь и достоинство Лицензиата, на Лицензиара накладывается штраф в размере 50.000 рублей (пятидесяти тысяч рублей).
6.5. Стороны согласовали, что после подписания договора, за передачу договора полностью, частично и/или любого его содержания третьим лицам, на Лицензиара накладывается штраф в размере 75.000 рублей (семидесяти пяти тысяч рублей).
6.6 В случае если Лицензиар передаст Новое Произведение третьей стороне до полного исполнения обязательств по данному Договору, а именно передачи Произведений, указанных в Приложении №1 к Договору, Лицензиар обязуется выплатить штраф в размере 200.000 рублей (двухсот тысяч рублей) за каждый факт нарушения.
6.7. Все приложения, изменения и дополнения к настоящему Договору, составленные в письменной форме и подписанные обеими Сторонами, являются его неотъемлемой частью.
6.8. Настоящий Договор составлен на русском языке, подписан в 2 (Двух) экземплярах, по одному экземпляру для каждой Стороны. Каждый экземпляр Договора имеет одинаковую юридическую силу.

Статья 7. Приложения к Договору
7.1.	Приложения, являющиеся неотъемлемой частью настоящего Договора:
7.1.1.	Приложение № 1 - Перечень Произведений, Исполнений, Фонограмм, Видеоклипов, исключительная лицензия на которые предоставляется Лицензиаром Лицензиату;
7.1.2.	Приложение № 2 – Дизайн-макеты, право на использование которых Лицензиар предоставляет Лицензиату;
7.1.3.	Приложение № 3 - Финансовые условия

Статья 8. Реквизиты и подписи Сторон

8.1. Лицензиар
Творческий псевдоним: {nickname}
ФИО: {full_name}
Паспорт серия и номер: {passport}
Кем выдан: {passport_issued}
Дата выдачи: {issue_date}
Код подразделения: {department_code}
Дата рождения: {birth_date}
Место рождения: {birth_place}
Адрес регистрации: {address}
СНИЛС: {snils}
ИНН: {inn}
Банковские реквизиты:
АО 'T-Банк'
р/с: 40817810000035696053
к/с: 30101810145250000974
ИНН: 7710140679
БИК: 044525974
КПП: 771301001

/ {full_name} /

8.2. Лицензиат
talk with a star label
Самозанятый Чабин Илья Анатольевич
Свердловская обл.,
г. Екатеринбург,
ул. Красноармейская, 28
Банковские реквизиты:
     АО «Т-банк»
      р/с: 40817810000035696053
      к/с: 30101810145250000974
      ИНН: 7710140679
      БИК: 044525974
      КПП: 771301001

/ Чабин И.А/"""

    # Подставляем данные пользователя в шаблон
    contract_text = contract_template.format(
        full_name=user_data.get('full_name', 'Фамилия Имя Отчество'),
        passport=user_data.get('passport', '1234 567890'),
        nickname=user_data.get('nickname', 'ПСЕВДОНИМ'),
        passport_issued=user_data.get('passport_issued', 'КЕМ ВЫДАН'),
        issue_date=user_data.get('issue_date', '01.01.2001'),
        department_code=user_data.get('department_code', '600-006'),
        birth_date=user_data.get('birth_date', '01.01.2001'),
        birth_place=user_data.get('birth_place', 'г. Москва'),
        address=user_data.get('address', 'Адрес регистрации'),
        snils=user_data.get('snils', '123-456-789 01'),
        inn=user_data.get('inn', '781432831090')
    )

    # Добавляем текст в документ по абзацам
    paragraphs = contract_text.split('\n')
    for paragraph_text in paragraphs:
        if paragraph_text.strip():
            paragraph = doc.add_paragraph(paragraph_text.strip())

            # Выравниваем заголовки по центру
            if any(header in paragraph_text for header in ['ЛИЦЕНЗИОННЫЙ ДОГОВОР', 'г. Екатеринбург']):
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if 'ЛИЦЕНЗИОННЫЙ ДОГОВОР' in paragraph_text:
                    for run in paragraph.runs:
                        run.bold = True
                        run.font.size = Pt(14)

    return doc

def add_attachments(doc, user_data):
    """Добавление приложений к договору"""
    # Приложение 1
    doc.add_page_break()
    app_title = doc.add_paragraph('Приложение №1')
    app_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    app_title = doc.add_paragraph('к Лицензионному договору № X/-XX')
    app_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    app_title = doc.add_paragraph(f'от {user_data["date"]}')
    app_title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    app_content = doc.add_paragraph('Перечень Произведений, Исполнений, Фонограмм и Видеоклипов, исключительная лицензия на которые предоставляется Лицензиаром Лицензиату')
    app_content.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Создаем таблицу
    table = doc.add_table(rows=2, cols=8)
    table.style = 'Table Grid'

    # Заголовки столбцов
    headers = ['Название релиза', 'Название трека', 'Автор музыки', 'Автор текста', 'Исполнитель', 'Изготовитель Фонограмм', 'Доля авторских/смежных прав', 'Срок сдачи']
    for i, header in enumerate(headers):
        table.cell(0, i).text = header
        table.cell(0, i).paragraphs[0].runs[0].bold = True

    # Данные
    table.cell(1, 0).text = user_data['release_name']
    table.cell(1, 1).text = user_data['track_name']
    table.cell(1, 2).text = user_data['music_author']
    table.cell(1, 3).text = user_data['text_author']
    table.cell(1, 4).text = user_data['performer']
    table.cell(1, 5).text = user_data['phonogram_producer']
    table.cell(1, 6).text = '100% / 100%'
    table.cell(1, 7).text = '2025'

    # Подписи сторон
    doc.add_page_break()
    signs_title = doc.add_paragraph('Подписи сторон:')
    signs_title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Таблица для подписей
    signs_table = doc.add_table(rows=2, cols=2)
    signs_table.style = 'Table Grid'

    # Лицензиар
    signs_table.cell(0, 0).text = 'Лицензиар'
    signs_table.cell(1, 0).text = f'Творческий псевдоним: {user_data["nickname"]}\n'
    signs_table.cell(1, 0).add_paragraph(f'ФИО: {user_data["full_name"]} Паспорт серия и номер: {user_data["passport"]} Кем выдан: {user_data["passport_issued"]}')
    signs_table.cell(1, 0).add_paragraph(f'Дата выдачи: {user_data["issue_date"]}')
    signs_table.cell(1, 0).add_paragraph(f'Код подразделения: {user_data["department_code"]}')
    signs_table.cell(1, 0).add_paragraph(f'Дата рождения: {user_data["birth_date"]}')
    signs_table.cell(1, 0).add_paragraph(f'Место рождения: {user_data["birth_place"]}')
    signs_table.cell(1, 0).add_paragraph(f'Адрес регистрации: {user_data["address"]}')
    signs_table.cell(1, 0).add_paragraph(f'СНИЛС: {user_data["snils"]}')
    signs_table.cell(1, 0).add_paragraph(f'ИНН: {user_data["inn"]}')

    # Лицензиат
    signs_table.cell(0, 1).text = 'Лицензиат'
    signs_table.cell(1, 1).text = 'talk with a star label\n'
    signs_table.cell(1, 1).add_paragraph('Самозанятый Чабин Илья Анатольевич')
    signs_table.cell(1, 1).add_paragraph('Свердловская обл., г. Екатеринбург, ул. Красноармейская, 28')
    signs_table.cell(1, 1).add_paragraph('Банковские реквизиты: АО «Т-банк»')
    signs_table.cell(1, 1).add_paragraph('р/с: 40817810000035696053')
    signs_table.cell(1, 1).add_paragraph('к/с: 30101810145250000974')
    signs_table.cell(1, 1).add_paragraph('ИНН: 7710140679')
    signs_table.cell(1, 1).add_paragraph('БИК: 044525974')
    signs_table.cell(1, 1).add_paragraph('КПП: 771301001')
    signs_table.cell(1, 1).add_paragraph('/ Чабин И.А/')

    # Добавляем остальные приложения аналогичным образом...
    # (здесь должен быть код для добавления приложений 2 и 3, а также акта приема-передачи)

def create_excel_report(user_data, releases_data=None):
    """Создание Excel отчета по пользователю и его релизам"""
    if not XLSX_AVAILABLE:
        raise ValueError("Библиотека openpyxl не установлена. Обратитесь к администратору.")

    # Создаем новую книгу Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Отчет по пользователю"

    # Стили для заголовков
    header_font = Font(bold=True, size=14, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    # Стили для подзаголовков
    subheader_font = Font(bold=True, size=12, color="000000")
    subheader_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    # Стили для обычного текста
    normal_font = Font(size=11)

    # Границы
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Заголовок отчета
    ws.merge_cells('A1:H1')
    ws['A1'] = f"ОТЧЕТ ПО ПОЛЬЗОВАТЕЛЮ: {user_data.get('name', 'Неизвестно')}"
    ws['A1'].font = header_font
    ws['A1'].fill = header_fill
    ws['A1'].alignment = header_alignment

    # Информация о пользователе
    ws['A3'] = "ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ"
    ws['A3'].font = subheader_font
    ws['A3'].fill = subheader_fill

    user_info_rows = [
        ["Имя:", user_data.get('name', 'Не указано')],
        ["Telegram ID:", str(user_data.get('telegram_id', 'Не указано'))],
        ["Username:", user_data.get('tg', 'Не указано')],
        ["Email:", user_data.get('email', 'Не указано')],
        ["Дата регистрации:", str(user_data.get('created_at', 'Не указано'))],
        ["Статус:", user_data.get('status', 'Не указано')],
        ["Роль:", user_data.get('role', 'Не указано')]
    ]

    for i, (label, value) in enumerate(user_info_rows, start=4):
        ws[f'A{i}'] = label
        ws[f'B{i}'] = value
        ws[f'A{i}'].font = Font(bold=True)
        ws[f'A{i}'].border = thin_border
        ws[f'B{i}'].border = thin_border

    # Информация о релизах
    if releases_data:
        start_row = len(user_info_rows) + 6
        ws[f'A{start_row}'] = "РЕЛИЗЫ ПОЛЬЗОВАТЕЛЯ"
        ws[f'A{start_row}'].font = subheader_font
        ws[f'A{start_row}'].fill = subheader_fill

        # Заголовки таблицы релизов
        release_headers = [
            "ID", "Название", "Тип", "Статус", "Дата создания",
            "Дата обновления", "Количество треков", "Описание"
        ]

        for col, header in enumerate(release_headers, start=1):
            cell = ws.cell(row=start_row + 2, column=col, value=header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")

        # Данные релизов
        for row_idx, release in enumerate(releases_data, start=start_row + 3):
            for col_idx, value in enumerate([
                release.get('id', ''),
                release.get('name', ''),
                release.get('type', ''),
                release.get('status', ''),
                str(release.get('created_at', '')),
                str(release.get('updated_at', '')),
                release.get('track_count', 0),
                release.get('description', '')
            ], start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="left", vertical="top")

        # Автоматическая ширина столбцов
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width

    # Добавляем статистику
    stats_row = start_row + len(releases_data) + 5 if releases_data else len(user_info_rows) + 6
    ws[f'A{stats_row}'] = "СТАТИСТИКА"
    ws[f'A{stats_row}'].font = subheader_font
    ws[f'A{stats_row}'].fill = subheader_fill

    stats_data = [
        ["Общее количество релизов:", len(releases_data) if releases_data else 0],
        ["Активных релизов:", len([r for r in (releases_data or []) if r.get('status') == 'active'] or 0)],
        ["Дата генерации отчета:", datetime.now().strftime("%d.%m.%Y %H:%M:%S")]
    ]

    for i, (label, value) in enumerate(stats_data, start=stats_row + 1):
        ws[f'A{i}'] = label
        ws[f'B{i}'].font = Font(bold=True)
        ws[f'A{i}'].border = thin_border
        ws[f'B{i}'].border = thin_border

    return wb


# Клавиатура для подтверждения
def create_confirmation_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('Да, всё верно'))
    keyboard.add(types.KeyboardButton('Нет, начать заново'))
    return keyboard

def handle_contract_request(message):
    """Start contract creation flow"""
    user_id = message.from_user.id

    # Инициализируем данные пользователя для договора
    if user_id not in bot.user_data:
        bot.user_data[user_id] = {}

    # Очищаем предыдущие данные договора
    bot.user_data[user_id]['contract_data'] = {}

    # Логируем начало создания договора
    logger.info(f"Начало создания договора для пользователя {user_id}")

    bot.reply_to(
        message,
        "📋 Создание лицензионного договора\n\n"
        "Давайте заполним все необходимые данные для договора.\n\n"
        "Введите дату договора (например: 01 января 2025 года):"
    )
    bot.register_next_step_handler(message, process_date_step)

def process_date_step(message):
    """Handle contract date input"""
    user_id = message.from_user.id

    # Проверяем корректность введенной даты
    date_text = message.text.strip()
    if not date_text:
        bot.reply_to(
            message,
            "❌ Дата не может быть пустой. Введите дату договора (например: 01 января 2025 года):"
        )
        bot.register_next_step_handler(message, process_date_step)
        return

    bot.user_data[user_id]['contract_data']['date'] = date_text

    # Логируем ввод даты
    logger.info(f"Пользователь {user_id} ввел дату: {date_text}")

    bot.reply_to(
        message,
        "Введите ФИО лицензиара:"
    )
    bot.register_next_step_handler(message, process_full_name_step)

def process_full_name_step(message):
    """Handle full name input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного ФИО
    full_name = message.text.strip()
    if not full_name:
        bot.reply_to(
            message,
            "❌ ФИО не может быть пустым. Введите ФИО лицензиара:"
        )
        bot.register_next_step_handler(message, process_full_name_step)
        return

    bot.user_data[user_id]['contract_data']['full_name'] = full_name

    # Логируем ввод ФИО
    logger.info(f"Пользователь {user_id} ввел ФИО: {full_name}")

    bot.reply_to(
        message,
        "Введите серию и номер паспорта (например: 1234 567890):"
    )
    bot.register_next_step_handler(message, process_passport_step)

def process_passport_step(message):
    """Handle passport input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного паспорта
    passport = message.text.strip()
    if not passport:
        bot.reply_to(
            message,
            "❌ Данные паспорта не могут быть пустыми. Введите серию и номер паспорта (например: 1234 567890):"
        )
        bot.register_next_step_handler(message, process_passport_step)
        return

    bot.user_data[user_id]['contract_data']['passport'] = passport

    # Логируем ввод паспорта
    logger.info(f"Пользователь {user_id} ввел паспорт: {passport}")

    bot.reply_to(
        message,
        "Введите творческий псевдоним:"
    )
    bot.register_next_step_handler(message, process_nickname_step)

def process_nickname_step(message):
    """Handle nickname input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного псевдонима
    nickname = message.text.strip()
    if not nickname:
        bot.reply_to(
        message,
            "❌ Псевдоним не может быть пустым. Введите творческий псевдоним:"
        )
        bot.register_next_step_handler(message, process_nickname_step)
        return

    bot.user_data[user_id]['contract_data']['nickname'] = nickname

    # Логируем ввод псевдонима
    logger.info(f"Пользователь {user_id} ввел псевдоним: {nickname}")

    bot.reply_to(
        message,
        "Кем выдан паспорт:"
    )
    bot.register_next_step_handler(message, process_passport_issued_step)

def process_passport_issued_step(message):
    """Handle passport issued input"""
    user_id = message.from_user.id

    # Проверяем корректность введенных данных
    passport_issued = message.text.strip()
    if not passport_issued:
        bot.reply_to(
        message,
            "❌ Данные о выдаче паспорта не могут быть пустыми. Кем выдан паспорт:"
        )
        bot.register_next_step_handler(message, process_passport_issued_step)
        return

    bot.user_data[user_id]['contract_data']['passport_issued'] = passport_issued

    # Логируем ввод данных о выдаче паспорта
    logger.info(f"Пользователь {user_id} ввел данные о выдаче паспорта: {passport_issued}")

    bot.reply_to(
        message,
        "Дата выдачи паспорта (в формате ДД.ММ.ГГГГ):"
    )
    bot.register_next_step_handler(message, process_issue_date_step)

def process_issue_date_step(message):
    """Handle issue date input"""
    user_id = message.from_user.id

    # Проверяем корректность введенной даты выдачи
    issue_date = message.text.strip()
    if not issue_date:
        bot.reply_to(
        message,
            "❌ Дата выдачи паспорта не может быть пустой. Дата выдачи паспорта (в формате ДД.ММ.ГГГГ):"
        )
        bot.register_next_step_handler(message, process_issue_date_step)
        return

    bot.user_data[user_id]['contract_data']['issue_date'] = issue_date

    # Логируем ввод даты выдачи
    logger.info(f"Пользователь {user_id} ввел дату выдачи паспорта: {issue_date}")

    bot.reply_to(
        message,
        "Код подразделения (например: 600-006):"
    )
    bot.register_next_step_handler(message, process_department_code_step)

def process_department_code_step(message):
    """Handle department code input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного кода подразделения
    department_code = message.text.strip()
    if not department_code:
        bot.reply_to(
        message,
            "❌ Код подразделения не может быть пустым. Код подразделения (например: 600-006):"
        )
        bot.register_next_step_handler(message, process_department_code_step)
        return

    bot.user_data[user_id]['contract_data']['department_code'] = department_code

    # Логируем ввод кода подразделения
    logger.info(f"Пользователь {user_id} ввел код подразделения: {department_code}")

    bot.reply_to(
        message,
        "Дата рождения (в формате ДД.ММ.ГГГГ):"
    )
    bot.register_next_step_handler(message, process_birth_date_step)

def process_birth_date_step(message):
    """Handle birth date input"""
    user_id = message.from_user.id

    # Проверяем корректность введенной даты рождения
    birth_date = message.text.strip()
    if not birth_date:
        bot.reply_to(
        message,
            "❌ Дата рождения не может быть пустой. Дата рождения (в формате ДД.ММ.ГГГГ):"
        )
        bot.register_next_step_handler(message, process_birth_date_step)
        return

    bot.user_data[user_id]['contract_data']['birth_date'] = birth_date

    # Логируем ввод даты рождения
    logger.info(f"Пользователь {user_id} ввел дату рождения: {birth_date}")

    bot.reply_to(
        message,
        "Место рождения:"
    )
    bot.register_next_step_handler(message, process_birth_place_step)

def process_birth_place_step(message):
    """Handle birth place input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного места рождения
    birth_place = message.text.strip()
    if not birth_place:
        bot.reply_to(
        message,
            "❌ Место рождения не может быть пустым. Место рождения:"
        )
        bot.register_next_step_handler(message, process_birth_place_step)
        return

    bot.user_data[user_id]['contract_data']['birth_place'] = birth_place

    # Логируем ввод места рождения
    logger.info(f"Пользователь {user_id} ввел место рождения: {birth_place}")

    bot.reply_to(
        message,
        "Адрес регистрации:"
    )
    bot.register_next_step_handler(message, process_address_step)

def process_address_step(message):
    """Handle address input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного адреса
    address = message.text.strip()
    if not address:
        bot.reply_to(
        message,
            "❌ Адрес не может быть пустым. Адрес регистрации:"
        )
        bot.register_next_step_handler(message, process_address_step)
        return

    bot.user_data[user_id]['contract_data']['address'] = address

    # Логируем ввод адреса
    logger.info(f"Пользователь {user_id} ввел адрес: {address}")

    bot.reply_to(
        message,
        "СНИЛС (в формате XXX-XXX-XXX XX):"
    )
    bot.register_next_step_handler(message, process_snils_step)

def process_snils_step(message):
    """Handle SNILS input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного СНИЛС
    snils = message.text.strip()
    if not snils:
        bot.reply_to(
        message,
            "❌ СНИЛС не может быть пустым. СНИЛС (в формате XXX-XXX-XXX XX):"
        )
        bot.register_next_step_handler(message, process_snils_step)
        return

    bot.user_data[user_id]['contract_data']['snils'] = snils

    # Логируем ввод СНИЛС
    logger.info(f"Пользователь {user_id} ввел СНИЛС: {snils}")

    bot.reply_to(
        message,
        "ИНН:"
    )
    bot.register_next_step_handler(message, process_inn_step)

def process_inn_step(message):
    """Handle INN input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного ИНН
    inn = message.text.strip()
    if not inn:
        bot.reply_to(
        message,
            "❌ ИНН не может быть пустым. ИНН:"
        )
        bot.register_next_step_handler(message, process_inn_step)
        return

    bot.user_data[user_id]['contract_data']['inn'] = inn

    # Логируем ввод ИНН
    logger.info(f"Пользователь {user_id} ввел ИНН: {inn}")

    bot.reply_to(
        message,
        "Название релиза:"
    )
    bot.register_next_step_handler(message, process_release_name_step)

def process_release_name_step(message):
    """Handle release name input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного названия релиза
    release_name = message.text.strip()
    if not release_name:
        bot.reply_to(
            message,
            "❌ Название релиза не может быть пустым. Название релиза:"
        )
        bot.register_next_step_handler(message, process_release_name_step)
        return

    bot.user_data[user_id]['contract_data']['release_name'] = release_name

    # Логируем ввод названия релиза
    logger.info(f"Пользователь {user_id} ввел название релиза: {release_name}")

    bot.reply_to(
        message,
        "Название трека:"
    )
    bot.register_next_step_handler(message, process_track_name_step)

def process_track_name_step(message):
    """Handle track name input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного названия трека
    track_name = message.text.strip()
    if not track_name:
        bot.reply_to(
            message,
            "❌ Название трека не может быть пустым. Название трека:"
        )
        bot.register_next_step_handler(message, process_track_name_step)
        return

    bot.user_data[user_id]['contract_data']['track_name'] = track_name

    # Логируем ввод названия трека
    logger.info(f"Пользователь {user_id} ввел название трека: {track_name}")

    bot.reply_to(
        message,
        "Автор музыки:"
    )
    bot.register_next_step_handler(message, process_music_author_step)

def process_music_author_step(message):
    """Handle music author input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного автора музыки
    music_author = message.text.strip()
    if not music_author:
        bot.reply_to(
            message,
            "❌ Автор музыки не может быть пустым. Автор музыки:"
        )
        bot.register_next_step_handler(message, process_music_author_step)
        return

    bot.user_data[user_id]['contract_data']['music_author'] = music_author

    # Логируем ввод автора музыки
    logger.info(f"Пользователь {user_id} ввел автора музыки: {music_author}")

    bot.reply_to(
        message,
        "Автор текста:"
    )
    bot.register_next_step_handler(message, process_text_author_step)

def process_text_author_step(message):
    """Handle text author input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного автора текста
    text_author = message.text.strip()
    if not text_author:
        bot.reply_to(
            message,
            "❌ Автор текста не может быть пустым. Автор текста:"
        )
        bot.register_next_step_handler(message, process_text_author_step)
        return

    bot.user_data[user_id]['contract_data']['text_author'] = text_author

    # Логируем ввод автора текста
    logger.info(f"Пользователь {user_id} ввел автора текста: {text_author}")

    bot.reply_to(
        message,
        "Исполнитель:"
    )
    bot.register_next_step_handler(message, process_performer_step)

def process_performer_step(message):
    """Handle performer input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного исполнителя
    performer = message.text.strip()
    if not performer:
        bot.reply_to(
            message,
            "❌ Исполнитель не может быть пустым. Исполнитель:"
        )
        bot.register_next_step_handler(message, process_performer_step)
        return

    bot.user_data[user_id]['contract_data']['performer'] = performer

    # Логируем ввод исполнителя
    logger.info(f"Пользователь {user_id} ввел исполнителя: {performer}")

    bot.reply_to(
        message,
        "Изготовитель фонограммы:"
    )
    bot.register_next_step_handler(message, process_phonogram_producer_step)

def process_phonogram_producer_step(message):
    """Handle phonogram producer input"""
    user_id = message.from_user.id

    # Проверяем корректность введенного изготовителя фонограммы
    phonogram_producer = message.text.strip()
    if not phonogram_producer:
        bot.reply_to(
            message,
            "❌ Изготовитель фонограммы не может быть пустым. Изготовитель фонограммы:"
        )
        bot.register_next_step_handler(message, process_phonogram_producer_step)
        return

    bot.user_data[user_id]['contract_data']['phonogram_producer'] = phonogram_producer

    # Логируем ввод изготовителя фонограммы
    logger.info(f"Пользователь {user_id} ввел изготовителя фонограммы: {phonogram_producer}")

    # Проверяем корректность всех данных перед отображением
    contract_data = bot.user_data[user_id]['contract_data']
    summary = contracts.build_contract_summary(contract_data)

    bot.reply_to(
        message,
        summary,
        reply_markup=create_confirmation_keyboard()
    )
    bot.register_next_step_handler(message, process_confirmation_step)

def process_confirmation_step(message):
    """Handle confirmation step"""
    user_id = message.from_user.id

    if message.text.lower() == 'да, всё верно':
        # Проверяем корректность данных перед генерацией
        contract_data = bot.user_data[user_id].get('contract_data', {})
        if not contract_data:
            bot.reply_to(
                message,
                "❌ Ошибка: данные договора не найдены. Попробуйте начать заново.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            bot.user_data[user_id]['contract_data'] = {}
            bot.register_next_step_handler(message, process_date_step)
            return

        # Логируем данные для отладки
        logger.info(f"Подтверждение договора для пользователя {user_id}")
        logger.info(f"Данные договора: {contract_data}")

        bot.reply_to(
            message,
            "🎉 Отлично! Генерирую документ...",
            reply_markup=types.ReplyKeyboardRemove()
        )
        generate_contract_document_new(message)
    else:
        bot.reply_to(
            message,
            "🔄 Хорошо, начнем заново. Введите дату договора (например: 01 января 2025 года):",
            reply_markup=types.ReplyKeyboardRemove()
        )
        # Сбрасываем данные и начинаем заново
        bot.user_data[user_id]['contract_data'] = {}
        bot.register_next_step_handler(message, process_date_step)


def replace_placeholder_in_doc(doc, placeholder, value):
    """Замена плейсхолдера во всем документе Word с сохранением форматирования"""
    try:
        # Замена в параграфах
        for paragraph in doc.paragraphs:
            if placeholder in paragraph.text:
                # Сохраняем оригинальное форматирование
                for run in paragraph.runs:
                    if placeholder in run.text:
                        run.text = run.text.replace(placeholder, str(value))

        # Замена в таблицах
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if placeholder in paragraph.text:
                            for run in paragraph.runs:
                                if placeholder in run.text:
                                    run.text = run.text.replace(placeholder, str(value))

        # Замена в верхних и нижних колонтитулах
        for section in doc.sections:
            for paragraph in section.header.paragraphs:
                if placeholder in paragraph.text:
                    for run in paragraph.runs:
                        if placeholder in run.text:
                            run.text = run.text.replace(placeholder, str(value))
            for paragraph in section.footer.paragraphs:
                if placeholder in paragraph.text:
                    for run in paragraph.runs:
                        if placeholder in run.text:
                            run.text = run.text.replace(placeholder, str(value))

        logger.info(f"Successfully replaced placeholder '{placeholder}' with '{value}'")

    except Exception as e:
        logger.error(f"Error replacing placeholder '{placeholder}': {e}")


def generate_contract_document_new(message):
    """Generate contract document using new template system"""
    user_id = message.from_user.id
    contract_data = bot.user_data[user_id].get('contract_data', {})

    try:
        # Проверяем наличие необходимых данных
        if not contract_data:
            raise ValueError("Данные договора не найдены")

        # Логируем данные для отладки
        logger.info(f"Создание документа для пользователя {user_id}")
        logger.info(f"Данные договора: {contract_data}")

        contract_data = contracts.normalize_contract_data(contract_data)

        # Проверяем доступность модуля для создания документов
        if not DOCX_AVAILABLE:
            bot.reply_to(
                message,
                "❌ Создание документов временно недоступно\n\n"
                "📝 Модуль для работы с Word документами не установлен на сервере.\n"
                "💡 Обратитесь к администратору для решения проблемы.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return

                # Создаем документ
        try:
            doc = create_license_agreement(contract_data)
        except Exception as doc_error:
            logger.error(f"Ошибка при создании документа: {doc_error}")
            bot.reply_to(
                message,
                f"❌ Ошибка при создании документа: {str(doc_error)}\n\n"
                f"💡 Обратитесь к администратору для решения проблемы.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return

        # Сохраняем в байтовый поток
        try:
            doc_bytes = io.BytesIO()
            doc.save(doc_bytes)
            doc_bytes.seek(0)
            logger.info("Документ успешно сохранен в байтовый поток")
        except Exception as save_error:
            logger.error(f"Ошибка при сохранении документа: {save_error}")
            bot.reply_to(
                message,
                f"❌ Ошибка при сохранении документа: {str(save_error)}\n\n"
                f"💡 Обратитесь к администратору для решения проблемы.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return

        # Отправка документа
        try:
            filename = contracts.contract_filename(contract_data.get('nickname', 'N/A'))

            bot.send_document(
                message.chat.id,
                doc_bytes,
                visible_file_name=filename
            )
            logger.info("Документ успешно отправлен пользователю")
        except Exception as send_error:
            logger.error(f"Ошибка при отправке документа: {send_error}")
            bot.reply_to(
                message,
                f"❌ Ошибка при отправке документа: {str(send_error)}\n\n"
                f"💡 Обратитесь к администратору для решения проблемы.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return

            bot.reply_to(
                message,
            "🎉 Документ готов! Если нужно создать еще один, используйте кнопку '📋 Создать договор'",
            reply_markup=types.ReplyKeyboardRemove()
            )

        # Создаем запись в базе данных и уведомляем администраторов
        try:
            conn = get_pg_connection()
            if conn:
                cursor = conn.cursor()

                # Создаем запись о договоре
                cursor.execute('''
                    INSERT INTO contracts (user_id, contract_number, contract_type, status, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (user_id, contract_data.get('date', 'N/A'), 'license', 'pending', datetime.now()))

                contract_id = cursor.fetchone()[0] if cursor.fetchone() else None
                conn.commit()

                if contract_id:
                    # Уведомляем администраторов
                    admin_ids = get_all_admins()
                    for admin_id in admin_ids:
                        try:
                            markup = types.InlineKeyboardMarkup()
                            markup.add(
                                types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
                                types.InlineKeyboardButton("📋 Управление договорами", callback_data="admin_contracts")
                            )

                            bot.send_message(
                                admin_id,
                                f"📋 Новый запрос договора!\n\n"
                                f"👤 Пользователь: @{message.from_user.username or 'без username'}\n"
                                f"📄 Дата договора: {contract_data.get('date', 'N/A')}\n"
                                f"📋 Тип: Лицензионный договор\n\n"
                                f"💡 Используйте кнопки ниже для быстрого доступа:",
                                reply_markup=markup
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify admin {admin_id}: {e}")

                    # Отправляем сообщение пользователю о том, что договор отправлен на рассмотрение
                    markup = types.InlineKeyboardMarkup()
                    markup.add(
                        types.InlineKeyboardButton("📋 Мои договоры", callback_data="my_contracts"),
                        types.InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_main")
                    )

                    bot.send_message(
                        message.chat.id,
                        "📋 Договор отправлен на рассмотрение администратору!\n\n"
                        "Ожидайте уведомления о готовности договора.",
                        reply_markup=markup
                    )

                cursor.close()
                return_pg_connection(conn)

        except Exception as e:
            logger.error(f"Error saving contract to database: {e}")

        # Очищаем данные договора
        if user_id in bot.user_data and 'contract_data' in bot.user_data[user_id]:
            del bot.user_data[user_id]['contract_data']

        # Возвращаемся в главное меню
        bot.send_message(
            message.chat.id,
            "Выберите действие:",
            reply_markup=create_main_menu()
        )

    except Exception as e:
        logger.error(f"Ошибка при генерации документа: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        logger.error(f"Данные договора: {contract_data}")
        bot.reply_to(
            message,
            f"❌ Произошла ошибка при создании документа: {str(e)}\n\nПопробуйте снова или обратитесь к администратору."
        )


def create_profile_menu():
    """Create profile menu keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📝 Мои данные", "profile_data"),
        ("💰 Мои финансы", "profile_finance"),
        ("📀 Мои релизы", "profile_releases"),
        ("📋 Черновики", "profile_drafts"),
        ("🎧 Мои записи", "profile_bookings"),
        ("🛍 Мои заказы", "profile_orders"),
        ("👥 Пригласи друга", "profile_referral")
    ]

    for text, callback in buttons:
        markup.add(types.InlineKeyboardButton(text, callback_data=callback))

    return markup


def notify_referrer_about_visit(referral_code, visitor_id, visitor_username):
    return referral_notifications.notify_referrer_about_visit(referral_code, visitor_id, visitor_username)


def handle_referral_registration(cursor, user_id, referral_code, conn):
    from db.repositories.referrals import handle_referral_registration as _handle_referral_registration

    return _handle_referral_registration(cursor, user_id, referral_code, conn)
        # Не прерываем регистрацию пользователя из-за ошибки реферальной системы


@require_channel_subscription
def handle_profile(message):
    """Handle profile menu with improved error handling"""
    user_id = message.from_user.id

    conn = None
    cursor = None

    # Retry logic для временных ошибок БД
    max_retries = 2
    for attempt in range(max_retries):
        try:
            conn = get_pg_connection()
            if not conn:
                if attempt < max_retries - 1:
                    time.sleep(0.3)
                    continue
                logger.error(f"Failed to get DB connection after {max_retries} attempts for user {user_id}")
                bot.reply_to(message, "❌ Ошибка подключения к базе данных. Попробуйте через несколько секунд.")
                return

            cursor = conn.cursor()
            cursor.execute('''
                SELECT name, kanal, fio, email, COALESCE(balance, 0)
                FROM label
                WHERE telegram_id = %s
            ''', (user_id,))
            user_info = cursor.fetchone()

            if user_info:
                name, kanal, fio, email, balance = user_info
                profile_text = "👤 Мой профиль:\n\n"
                profile_text += f"🎤 Имя артиста: {name or 'Не указано'}\n"
                profile_text += f"📺 Канал: {kanal or 'Не указан'}\n"
                profile_text += f"👥 ФИО: {fio or 'Не указано'}\n"
                profile_text += f"📧 Email: {email or 'Не указан'}\n"
                profile_text += f"💰 Баланс: {balance:,.2f}₽"

                # Кнопки профиля в два столбца
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                markup.add(
                    types.KeyboardButton("✏️ Редактировать профиль"),
                    types.KeyboardButton("📀 Мои релизы")
                )
                markup.add(
                    types.KeyboardButton("📋 Черновики"),
                    types.KeyboardButton("📊 Мои отчеты")
                )
                markup.add(
                    types.KeyboardButton("🆘 Мои заявки"),
                    types.KeyboardButton("🛒 Мои заказы")
                )
                markup.add(
                    types.KeyboardButton("💳 Пополнить баланс"),
                    types.KeyboardButton("🎟 Ввести промокод")
                )
                markup.add(
                    types.KeyboardButton("👥 Пригласи друга"),
                    types.KeyboardButton("◀️ Назад в меню")
                )

                bot.reply_to(message, profile_text, reply_markup=markup)
            else:
                start_link = "https://t.me/twaslabel_bot?start=start"
                safe_link = escape_markdown(start_link)
                bot.reply_to(
                    message,
                    "❌ Пожалуйста, зарегистрируйтесь, введя команду /start.\n\n"
                    f"[Нажмите /start]({safe_link})",
                    parse_mode="Markdown"
                )

            # Успешное выполнение, выходим из цикла retry
            break

        except psycopg2.OperationalError as db_error:
            # Временные ошибки БД - пробуем повторить
            logger.warning(f"DB operational error on attempt {attempt + 1}/{max_retries} for user {user_id}: {db_error}")
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            logger.error(f"DB operational error after {max_retries} attempts: {db_error}")
            bot.reply_to(message, "❌ Временная ошибка базы данных. Попробуйте через несколько секунд.")
            return
        except psycopg2.Error as db_error:
            # Критические ошибки БД - не повторяем
            logger.error(f"DB error handling profile for user {user_id}: {type(db_error).__name__}: {db_error}")
            bot.reply_to(message, "❌ Ошибка базы данных. Обратитесь в поддержку, если проблема сохраняется.")
            return
        except Exception as e:
            # Неожиданные ошибки
            logger.error(f"Unexpected error handling profile for user {user_id}: {type(e).__name__}: {e}", exc_info=True)
            if attempt < max_retries - 1:
                time.sleep(0.3)
                continue
            bot.reply_to(message, "❌ Произошла ошибка при обработке профиля. Попробуйте позже или обратитесь в поддержку.")
            return
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                return_pg_connection(conn)
                conn = None



def _draft_display_label(draft_type, data_json, created_at):
    """Формирует человекочитаемую подпись для черновика: исполнитель — название (дата)."""
    date_str = created_at.strftime('%d.%m.%Y') if hasattr(created_at, 'strftime') else str(created_at)
    if data_json:
        try:
            data = json.loads(data_json) if isinstance(data_json, str) else data_json
            artist = (data.get('artist_name') or data.get('album_artist') or '').strip()
            name = (data.get('release_name') or data.get('album_name') or '').strip()
            if artist and name:
                return f"📝 {artist} — {name} ({date_str})"
            if name:
                return f"📝 {name} ({date_str})"
            if artist:
                return f"📝 {artist} ({date_str})"
        except Exception:
            pass
    type_label = "Дистрибуция" if draft_type == "distribution_legacy" else (draft_type or "Черновик")
    return f"📝 {type_label} ({date_str})"



def process_promo_input(message):
    """Process promo code input"""
    if is_cancel_message(message):
        # Return to profile
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✏️ Редактировать профиль"))
        markup.add(types.KeyboardButton("📀 Мои релизы"))
        markup.add(types.KeyboardButton("📊 Мои отчеты"))
        markup.add(types.KeyboardButton("💳 Пополнить баланс"))
        markup.add(types.KeyboardButton("🎟 Ввести промокод"))
        markup.add(types.KeyboardButton("◀️ Назад в меню"))

        bot.reply_to(message, "Возвращаемся в профиль", reply_markup=markup)
        return

    promo_code = message.text.strip().upper()
    user_id = message.from_user.id

    conn = get_pg_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных")
        return

    try:
        cursor = conn.cursor()

        # Check if promo_codes table exists, create if not
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'promo_codes'
            )
        """)

        if not cursor.fetchone()[0]:
            logger.info("Creating promo_codes table...")
            cursor.execute("""
                CREATE TABLE promo_codes (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL,
                    discount NUMERIC(10, 2) DEFAULT 0,
                    is_used BOOLEAN DEFAULT FALSE,
                    created_by BIGINT,
                    used_by BIGINT,
                    used_at TIMESTAMP,
                    max_uses INTEGER DEFAULT NULL,
                    current_uses INTEGER DEFAULT 0,
                    expires_at TIMESTAMP DEFAULT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            logger.info("✅ promo_codes table created")

        # Check if promo_code_usage table exists, create if not
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'promo_code_usage'
            )
        """)

        if not cursor.fetchone()[0]:
            logger.info("Creating promo_code_usage table...")
            cursor.execute("""
                CREATE TABLE promo_code_usage (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    promo_code_id INTEGER NOT NULL,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, promo_code_id),
                    FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
            logger.info("✅ promo_code_usage table created")

            # Create indexes for better performance
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_promo_codes_active ON promo_codes(is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_promo_code_usage_user_id ON promo_code_usage(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_promo_code_usage_promo_id ON promo_code_usage(promo_code_id)")
                conn.commit()
                logger.info("✅ Promo code indexes created")
            except Exception as e:
                logger.warning(f"Could not create promo code indexes: {e}")

        # Verify table structure and add missing columns if needed
        logger.info("Verifying promo_codes table structure...")

        # Структура таблицы промокодов проверяется при инициализации БД

        # Check if all required columns exist, if not - create them
        required_columns = ['amount', 'discount', 'is_used', 'created_by', 'used_by', 'used_at', 'max_activations', 'current_activations', 'expires_at', 'is_active']
        logger.info(f"Checking required columns: {required_columns}")

        for column in required_columns:
            cursor.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'promo_codes' AND column_name = '{column}'
            """)

            if not cursor.fetchone():
                # Column doesn't exist, add it
                if column == 'amount':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN amount NUMERIC(10, 2) DEFAULT 0")
                    cursor.execute("UPDATE promo_codes SET amount = 0 WHERE amount IS NULL")
                elif column == 'discount':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN discount NUMERIC(10, 2) DEFAULT 0")
                    cursor.execute("UPDATE promo_codes SET discount = 0 WHERE discount IS NULL")
                elif column == 'is_used':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN is_used BOOLEAN DEFAULT FALSE")
                    cursor.execute("UPDATE promo_codes SET is_used = FALSE WHERE is_used IS NULL")
                elif column == 'created_by':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN created_by BIGINT DEFAULT 0")
                    cursor.execute("UPDATE promo_codes SET created_by = 0 WHERE created_by IS NULL")
                elif column == 'used_by':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN used_by BIGINT")
                elif column == 'used_at':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN used_at TIMESTAMP")
                elif column == 'max_activations':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN max_activations INTEGER DEFAULT NULL")
                elif column == 'current_activations':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN current_activations INTEGER DEFAULT 0")
                elif column == 'expires_at':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN expires_at TIMESTAMP DEFAULT NULL")
                elif column == 'is_active':
                    cursor.execute("ALTER TABLE promo_codes ADD COLUMN is_active BOOLEAN DEFAULT TRUE")

                logger.info(f"✅ Added column {column} to promo_codes table during promo input")

        # Commit column additions before proceeding
        conn.commit()
        logger.info("✅ All required columns verified/added successfully")

        # Check if promo code exists and is valid (id, amount, discount, limit columns, expires_at, is_active)
        cursor.execute('''
            SELECT id, amount, COALESCE(discount, 0),
                   COALESCE(max_activations, max_uses) AS max_act,
                   COALESCE(current_activations, current_uses) AS cur_act,
                   max_uses, current_uses, expires_at, is_active
            FROM promo_codes
            WHERE code = %s AND is_active = TRUE
        ''', (promo_code,))

        result = cursor.fetchone()

        if not result:
            bot.reply_to(
                message,
                "❌ Промокод не найден или неактивен",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🎟 Ввести промокод").add("◀️ Назад в профиль")
            )
            return

        promo_id, amount, discount, max_act, cur_act, max_uses, current_uses, expires_at, is_active = result
        amount = float(amount or 0)
        discount = float(discount or 0)

        # Check if promo code has expired
        if expires_at and expires_at < datetime.now():
            cursor.execute('UPDATE promo_codes SET is_active = FALSE WHERE code = %s', (promo_code,))
            conn.commit()
            bot.reply_to(
                message,
                "❌ Промокод истек",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🎟 Ввести промокод").add("◀️ Назад в профиль")
            )
            return

        # Limit check: for discount use max_uses/current_uses, for balance use max_act/cur_act
        if discount > 0:
            if max_uses is not None and (current_uses or 0) >= max_uses:
                cursor.execute('UPDATE promo_codes SET is_active = FALSE WHERE code = %s', (promo_code,))
                conn.commit()
                bot.reply_to(
                    message,
                    "❌ Промокод достиг лимита активаций",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🎟 Ввести промокод").add("◀️ Назад в профиль")
                )
                return
        else:
            if max_act is not None and (cur_act or 0) >= max_act:
                cursor.execute('UPDATE promo_codes SET is_active = FALSE WHERE code = %s', (promo_code,))
                conn.commit()
                bot.reply_to(
                    message,
                    "❌ Промокод достиг лимита использований",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🎟 Ввести промокод").add("◀️ Назад в профиль")
                )
                return

        # Check if user exists in label table
        cursor.execute('SELECT telegram_id FROM label WHERE telegram_id = %s', (user_id,))
        user_exists = cursor.fetchone()

        if not user_exists:
            cursor.execute('''
                INSERT INTO label (telegram_id, created_date, balance)
                VALUES (%s, CURRENT_TIMESTAMP, 0)
                ON CONFLICT (telegram_id) DO NOTHING
            ''', (user_id,))
            logger.info(f"Created new user record for {user_id} during promo activation")

        profile_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        profile_markup.add(types.KeyboardButton("✏️ Редактировать профиль"))
        profile_markup.add(types.KeyboardButton("📀 Мои релизы"))
        profile_markup.add(types.KeyboardButton("📊 Мои отчеты"))
        profile_markup.add(types.KeyboardButton("💳 Пополнить баланс"))
        profile_markup.add(types.KeyboardButton("🎟 Ввести промокод"))
        profile_markup.add(types.KeyboardButton("◀️ Назад в меню"))

        # Промокод на скидку: не пополняем баланс, добавляем в user_discount_promos
        if discount > 0:
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'user_discount_promos'
                    )
                """)
                if not cursor.fetchone()[0]:
                    cursor.execute("""
                        CREATE TABLE user_discount_promos (
                            user_id BIGINT NOT NULL,
                            promo_code_id INTEGER NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (user_id, promo_code_id),
                            FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id) ON DELETE CASCADE
                        )
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_discount_promos_user_id ON user_discount_promos(user_id)")
                    conn.commit()
                cursor.execute('SELECT 1 FROM user_discount_promos WHERE user_id = %s AND promo_code_id = %s', (user_id, promo_id))
                if cursor.fetchone():
                    bot.reply_to(
                        message,
                        "❌ Вы уже активировали этот промокод на скидку. Он будет доступен при оплате дистрибуции.",
                        reply_markup=profile_markup
                    )
                    return
                cursor.execute('INSERT INTO user_discount_promos (user_id, promo_code_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (user_id, promo_id))
                cursor.execute(
                    'UPDATE promo_codes SET current_uses = COALESCE(current_uses, 0) + 1, used_by = %s, used_at = CURRENT_TIMESTAMP WHERE id = %s',
                    (user_id, promo_id)
                )
                conn.commit()
                bot.reply_to(
                    message,
                    f"✅ Промокод на скидку активирован!\n\n"
                    f"Скидка {discount:.0f}% будет доступна при оплате дистрибуции (кнопка «Использовать промокод»).",
                    reply_markup=profile_markup
                )
                logger.info(f"Discount promo {promo_code} activated for user {user_id}")
            except Exception as e:
                logger.warning(f"Discount promo activation: {e}")
                conn.rollback()
                bot.reply_to(message, "❌ Ошибка активации промокода на скидку.", reply_markup=profile_markup)
            return

        # Промокод на пополнение: проверка "уже использован" и зачисление на баланс
        cursor.execute('''
            SELECT pcu.id FROM promo_code_usage pcu
            JOIN promo_codes pc ON pcu.promo_code_id = pc.id
            WHERE pcu.user_id = %s AND pc.code = %s
        ''', (user_id, promo_code))

        if cursor.fetchone():
            bot.reply_to(
                message,
                "❌ Вы уже использовали этот промокод! Каждый промокод можно использовать только один раз.",
                reply_markup=profile_markup
            )
            return

        cursor.execute('''
            UPDATE promo_codes
            SET current_activations = COALESCE(current_activations, 0) + 1,
                used_by = %s,
                used_at = CURRENT_TIMESTAMP,
                is_used = CASE WHEN max_activations IS NOT NULL AND COALESCE(current_activations, 0) + 1 >= max_activations THEN TRUE ELSE is_used END
            WHERE code = %s
        ''', (user_id, promo_code))

        cursor.execute('''
            UPDATE label
            SET balance = COALESCE(balance, 0) + %s
            WHERE telegram_id = %s
        ''', (amount, user_id))

        cursor.execute('''
            INSERT INTO promo_code_usage (user_id, promo_code_id)
            SELECT %s, id FROM promo_codes WHERE code = %s
        ''', (user_id, promo_code))

        conn.commit()

        bot.reply_to(
            message,
            f"✅ Промокод активирован!\n\nНа ваш баланс зачислено: {amount:,.2f}₽",
            reply_markup=profile_markup
        )

        logger.info(f"Promo code {promo_code} activated for user {user_id}, amount: {amount}")

    except Error as e:
        logger.error(f"PostgreSQL error in promo input: {e}")
        error_msg = str(e)
        if "столбец" in error_msg.lower():
            error_msg = "❌ Ошибка структуры базы данных: отсутствуют необходимые столбцы. Попробуйте еще раз или обратитесь к администратору."
        bot.reply_to(
            message,
            f"❌ Ошибка базы данных: {error_msg}",
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🎟 Ввести промокод").add("◀️ Назад в профиль")
        )
    except Exception as e:
        logger.error(f"Unexpected error in promo input: {e}")
        bot.reply_to(
            message,
            f"❌ Неожиданная ошибка: {str(e)}",
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🎟 Ввести промокод").add("◀️ Назад в профиль")
        )
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




def cleanup_old_orders():
    """Clean up old pending orders"""
    conn = get_pg_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        # Отменяем заказы старше 2 часов
        cursor.execute('''
            UPDATE orders
            SET status = 'failed'
            WHERE status = 'pending'
            AND created_date < %s
        ''', (datetime.now() - timedelta(hours=2),))

        cleaned_count = cursor.rowcount
        conn.commit()

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old pending orders")

    except Exception as e:
        logger.error(f"Failed to cleanup old orders: {e}")
    finally:
        cursor.close()
        conn.close()


def handle_crypto_payment(call):
    """Handle Crypto Bot payment creation"""
    payment_id = call.data.split("_")[2]

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT amount FROM orders WHERE payment_id = %s', (payment_id,))
        result = cursor.fetchone()

        if not result:
            bot.answer_callback_query(call.id, "❌ Заказ не найден", show_alert=True)
            return

        amount = result[0]

        # Create Crypto Bot payment link
        # Note: This is a placeholder. You'll need to integrate with actual Crypto Bot API
        crypto_payment_url = f"https://t.me/CryptoBot?start=pay_{payment_id}_{amount}"

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("₿ Оплатить через Crypto Bot", url=crypto_payment_url),
            types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{payment_id}")
        )

        bot.edit_message_text(
            f"Пополнение на {amount}₽ через Crypto Bot\n\n"
            f"Нажмите кнопку ниже для перехода к оплате в Crypto Bot.\n"
            f"После оплаты нажмите 'Проверить оплату'.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    except Error as e:
        logger.error(f"DB error in Crypto payment: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)



def show_profile(chat_id, user_id, username):
    """Show user profile"""
    conn = get_pg_connection()
    if not conn:
        bot.send_message(chat_id, "❌ Ошибка подключения к базе данных. Попробуйте позже.")
        return

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, kanal, fio, email, COALESCE(balance, 0)
            FROM label
            WHERE telegram_id = %s
        ''', (user_id,))
        user_info = cursor.fetchone()

        profile_text = "👤 Мой профиль:\n\n"
        if user_info:
            name, kanal, fio, email, balance = user_info
            profile_text += f"🎤 Имя артиста: {name or 'Не указано'}\n"
            profile_text += f"📺 Канал: {kanal or 'Не указан'}\n"
            profile_text += f"👥 ФИО: {fio or 'Не указано'}\n"
            profile_text += f"📧 Email: {email or 'Не указан'}\n"
            profile_text += f"💰 Баланс: {balance:,.2f}₽"
        else:
            profile_text = "❌ Ваш профиль не найден в базе данных"

        # Create profile menu
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(types.KeyboardButton("✏️ Редактировать профиль"), types.KeyboardButton("📀 Мои релизы"))
        markup.add(types.KeyboardButton("📋 Черновики"), types.KeyboardButton("📊 Мои отчеты"))
        markup.add(types.KeyboardButton("🆘 Мои заявки"), types.KeyboardButton("🛒 Мои заказы"))
        markup.add(types.KeyboardButton("💳 Пополнить баланс"), types.KeyboardButton("🎟 Ввести промокод"))
        markup.add(types.KeyboardButton("👥 Пригласи друга"), types.KeyboardButton("◀️ Назад в меню"))

        bot.send_message(chat_id, profile_text, reply_markup=markup)

    except Exception as e:
        logger.error(f"Error showing profile: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при загрузке профиля. Попробуйте позже.")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)









# Обработчик нажатия кнопки редактирования профиля

def save_email(message):
    """Save new email with validation"""
    new_email = message.text.strip()
    user_id = message.from_user.id

    # Проверка формата email с помощью регулярного выражения
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", new_email):
        msg = bot.reply_to(
            message,
            "❌ Неверный формат email. Пожалуйста, введите действительный email адрес:"
        )
        bot.register_next_step_handler(msg, save_email)
        return

    try:
        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
            return

        cursor = conn.cursor()
        cursor.execute(
            'UPDATE label SET email = %s WHERE telegram_id = %s',
            (new_email, user_id)
        )
        conn.commit()

        # Обновляем клавиатуру профиля
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✏️ Редактировать профиль"))
        markup.add(types.KeyboardButton("📀 Мои релизы"))
        markup.add(types.KeyboardButton("📊 Мои отчеты"))
        markup.add(types.KeyboardButton("💳 Пополнить баланс"))
        markup.add(types.KeyboardButton("🎟 Ввести промокод"))
        markup.add(types.KeyboardButton("◀️ Назад в меню"))

        bot.reply_to(
            message,
            f"✅ Email успешно обновлен на: {new_email}",
            reply_markup=markup
        )

        # Логируем изменение
        logger.info(f"User {user_id} updated email to: {new_email}")

    except Exception as e:
        logger.error(f"Error saving email: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при сохранении email. Попробуйте позже.")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn:
            return_pg_connection(conn)


# Обработчики изменения конкретных полей

def save_artist_name(message):
    """Save new artist name"""
    new_name = message.text.strip()
    user_id = message.from_user.id

    try:
        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
            return

        cursor = conn.cursor()
        cursor.execute(
            'UPDATE label SET name = %s WHERE telegram_id = %s',
            (new_name, user_id)
        )
        conn.commit()

        # Возвращаем в меню профиля
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✏️ Редактировать профиль"))
        markup.add(types.KeyboardButton("📀 Мои релизы"))
        markup.add(types.KeyboardButton("📊 Мои отчеты"))
        markup.add(types.KeyboardButton("💳 Пополнить баланс"))
        markup.add(types.KeyboardButton("🎟 Ввести промокод"))
        markup.add(types.KeyboardButton("◀️ Назад в меню"))

        bot.reply_to(
            message,
            "✅ Имя артиста успешно обновлено!",
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error saving artist name: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при сохранении.")

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn:
            return_pg_connection(conn)


def save_channel_edit(message):
    """Save new channel"""
    new_channel = message.text.strip()
    user_id = message.from_user.id

    try:
        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
            return

        cursor = conn.cursor()
        cursor.execute(
            'UPDATE label SET kanal = %s WHERE telegram_id = %s',
            (new_channel, user_id)
        )
        conn.commit()

        # Возвращаем в меню профиля
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✏️ Редактировать профиль"))
        markup.add(types.KeyboardButton("📀 Мои релизы"))
        markup.add(types.KeyboardButton("📊 Мои отчеты"))
        markup.add(types.KeyboardButton("💳 Пополнить баланс"))
        markup.add(types.KeyboardButton("🎟 Ввести промокод"))
        markup.add(types.KeyboardButton("◀️ Назад в меню"))

        bot.reply_to(
            message,
            "✅ Канал успешно обновлен!",
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error saving channel: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при сохранении.")

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn:
            return_pg_connection(conn)


def save_fio(message):
    """Save new FIO"""
    new_fio = message.text.strip()
    user_id = message.from_user.id

    try:
        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
            return

        cursor = conn.cursor()
        cursor.execute(
            'UPDATE label SET fio = %s WHERE telegram_id = %s',
            (new_fio, user_id)
        )
        conn.commit()

        # Возвращаем в меню профиля
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✏️ Редактировать профиль"))
        markup.add(types.KeyboardButton("📀 Мои релизы"))
        markup.add(types.KeyboardButton("📊 Мои отчеты"))
        markup.add(types.KeyboardButton("💳 Пополнить баланс"))
        markup.add(types.KeyboardButton("🎟 Ввести промокод"))
        markup.add(types.KeyboardButton("◀️ Назад в меню"))

        bot.reply_to(
            message,
            "✅ ФИО успешно обновлено!",
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error saving FIO: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при сохранении.")

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn:
            return_pg_connection(conn)


# Обработчик возврата в профиль




# Обработчик возврата в главное меню

# Добавим новый обработчик для callback-запросов релизов в админ-панели

# Модифицируем функцию просмотра релизов пользователя для администратора

# Функция handle_admin_start_distribution удалена - перенесена в услуги


# Функция handle_admin_create_release_on_behalf удалена - перенесена в услуги


def handle_successful_payment(call, payment):
    return payment_callbacks.handle_successful_payment(call, payment)


def notify_admins(message, levels):
    return payment_callbacks.notify_admins(message, levels)


def handle_distribution_payment(call, payment):
    return payment_callbacks.handle_distribution_payment(call, payment)


def handle_design_payment(call, payment, service):
    return payment_callbacks.handle_design_payment(call, payment, service)



@require_channel_subscription
def handle_reviews(message):
    """Handle reviews section with action selection"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👀 Посмотреть отзывы", callback_data="reviews_view_menu"),
        types.InlineKeyboardButton("✍️ Оставить отзыв", callback_data="reviews_create_menu")
    )

    bot.reply_to(
        message,
        "⭐️ Отзывы\n\nВыберите действие:",
        reply_markup=markup
    )



def show_random_review(message):
    """Show random approved review"""
    conn = get_pg_connection()
    if not conn:
        bot.edit_message_text(
            "❌ Ошибка подключения к базе данных. Попробуйте позже.",
            message.chat.id,
            message.message_id
        )
        return

    try:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT l.name, r.service_type, r.rating, r.text, r.created_date
            FROM reviews r
            JOIN label l ON r.user_id = l.telegram_id
            WHERE r.status = %s
            ORDER BY RANDOM()
            LIMIT 1
        ''',
                       ("approved",))

        review = cursor.fetchone()

        if not review:
            review_text = "😔 Пока нет отзывов"
        else:
            artist_name, service_type, rating, text, date = review
            stars = "⭐️" * rating
            review_text = (
                f"🎵 Отзыв о {service_type}\n\n"
                f"👤 {artist_name}\n"
                f"{stars}\n"
                f"💭 {text}\n"
                f"📅 {date}"
            )

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔄 Еще отзыв", callback_data="reviews_random"),
            types.InlineKeyboardButton("◀️ Назад", callback_data="reviews_back_main")
        )

        bot.edit_message_text(
            review_text,
            message.chat.id,
            message.message_id,
            reply_markup=markup
        )
    except Error as e:
        logger.error(f"PostgreSQL error in show_random_review: {e}")
        bot.edit_message_text(
            "❌ Произошла ошибка при получении случайного отзыва.",
            message.chat.id,
            message.message_id
        )
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)


def show_category_reviews(message, category):
    """Show approved reviews for specific category"""
    conn = get_pg_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных. Попробуйте позже.")
        return

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT l.name, r.rating, r.text, r.created_date
            FROM reviews r
            JOIN label l ON r.user_id = l.telegram_id
            WHERE r.service_type = %s AND r.status = %s
            ORDER BY r.created_date DESC
            LIMIT 5
        ''', (category, "approved"))

        reviews = cursor.fetchall()

        # Форматирование отзывов
        reviews_text = f"⭐️ Отзывы о {category}:\n\n"
        for name, rating, text, date in reviews:
            stars = "⭐️" * rating
            date_str = date.strftime('%d.%m.%Y')
            reviews_text += f"👤 {name}\n{stars}\n💬 {text}\n📅 {date_str}\n\n"

        # Создание клавиатуры
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="reviews_back"))

        bot.send_message(message.chat.id, reviews_text, reply_markup=markup)

    except Error as e:
        logger.error(f"Ошибка при получении отзывов: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при загрузке отзывов.")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)



def notify_admins_about_new_review(review_id):
    """Notify admins about new review with moderation buttons"""
    conn = get_pg_connection()
    if not conn:
        logger.error("Database connection failed")
        return

    try:
        cursor = conn.cursor()
        # Получаем детали отзыва
        cursor.execute('''
            SELECT r.rating, r.text, l.name, l.tg
            FROM reviews r
            JOIN label l ON r.user_id = l.telegram_id
            WHERE r.id = %s
        ''', (review_id,))
        review = cursor.fetchone()

        if not review:
            logger.error(f"Review {review_id} not found")
            return

        rating, text, artist_name, username = review
        stars = "⭐️" * rating

        # Формируем сообщение
        message_text = (
            "📝 Новый отзыв на модерацию!\n\n"
            f"👤 Артист: {artist_name} (@{username})\n"
            f"⭐️ Оценка: {stars}\n"
            f"💬 Текст: {text[:200]}{'...' if len(text) > 200 else ''}"
        )

        # Создаем кнопки для модерации
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_review_{review_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_review_{review_id}")
        )

        # Получаем всех администраторов
        cursor.execute("SELECT telegram_id FROM label WHERE admin = 1")
        admins = cursor.fetchall()

        if not admins:
            logger.warning("No admins found in database")
            return

        # Отправляем уведомление каждому администратору
        for admin in admins:
            try:
                bot.send_message(
                    admin[0],  # Здесь была ошибка - лишний код
                    message_text,
                    reply_markup=markup
                )
                logger.info(f"Review notification sent to admin {admin[0]}")
            except Exception as e:
                logger.error(f"Failed to send to admin {admin[0]}: {e}")

    except Exception as e:
        logger.error(f"Error notifying admins: {e}")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)





def create_rating_keyboard():
    """Create rating selection keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=5)
    buttons = [types.InlineKeyboardButton(f"{i}⭐️", callback_data=f"rating_{i}") for i in range(1, 6)]
    markup.add(*buttons)
    return markup


# В функции handle_rating добавьте сохранение рейтинга

# Обновите функцию save_review
def save_review(message):
    """Save review to database and notify admins"""
    text = message.text.strip()
    user_id = message.from_user.id

    if not hasattr(bot, 'review_category') or not hasattr(bot, 'review_rating'):
        bot.reply_to(message, "❌ Ошибка данных отзыва. Пожалуйста, начните процесс заново.")
        return

    if not text:
        bot.reply_to(message, "❌ Текст отзыва не может быть пустым. Пожалуйста, напишите ваш отзыв:")
        bot.register_next_step_handler(message, save_review)
        return

    conn = get_pg_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных. Не удалось сохранить отзыв.")
        return

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reviews (user_id, service_type, rating, text, status, created_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            user_id,
            bot.review_category,
            bot.review_rating,
            text,
            "pending",
            datetime.now()
        ))

        review_id = cursor.fetchone()[0]
        conn.commit()
        notify_admins_about_new_review(review_id)

        delattr(bot, 'review_category')
        delattr(bot, 'review_rating')

        bot.reply_to(
            message,
            "✅ Спасибо за ваш отзыв! Он будет опубликован после проверки модератором."
        )

    except Exception as e:
        logger.error(f"Error saving review: {e}")
        bot.reply_to(message, f"❌ Произошла ошибка при сохранении отзыва: {str(e)}")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)



def check_pending_reviews():
    """Check and notify about pending reviews"""
    conn = get_pg_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM reviews WHERE status = %s', ("pending",))
        count = cursor.fetchone()[0]

        if count > 0:
            # Получаем список админов
            cursor.execute('SELECT telegram_id FROM label WHERE admin = 1')
            admins = cursor.fetchall()

            for admin in admins:
                try:
                    bot.send_message(
                        admin[0],
                        f"🆕 Есть {count} отзывов на модерацию!\n"
                        "Используйте /admin -> Отзывы для просмотра"
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить админа: {e}")

    except Error as e:
        logger.error(f"Ошибка проверки отзывов: {e}")
    finally:
        if conn:
            return_pg_connection(conn)


def get_display_username(user):
    return payment_callbacks.get_display_username(user)


def get_support_template(template_id):
    return next((tpl for tpl in SUPPORT_TEMPLATES if tpl["id"] == template_id), None)


def build_support_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for template in SUPPORT_TEMPLATES:
        markup.add(types.InlineKeyboardButton(
            template["button"],
            callback_data=f"support_template:{template['id']}"
        ))
    markup.add(types.InlineKeyboardButton(
        "💬 Написать менеджеру",
        url=f"https://t.me/{MANAGER_USERNAME[1:]}"
    ))
    return markup


def create_support_cancel_inline_keyboard():
    """Кнопка «Отмена» для раздела поддержки."""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="support_cancel"))
    return markup


def build_support_status_markup(request_id, active_status=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for status in SUPPORT_REQUEST_STATUSES:
        prefix = "✅ " if status == active_status else ""
        markup.add(types.InlineKeyboardButton(
            f"{prefix}{status.title()}",
            callback_data=f"support_status:{request_id}:{status}"
        ))
    return markup


def format_support_request_text(request):
    text = (
        f"🆘 Заявка поддержки\n"
        f"Шаблон: {request['template_title']}\n"
        f"Пользователь: {request['user_display']}\n"
    )

    if request.get('release_name'):
        text += f"🎵 Релиз: {request['release_name']}\n"

    text += (
        f"Статус: {request['status']}\n"
        f"Создано: {format_human_datetime(request['created_at'])}\n\n"
        f"Сообщение:\n{request['details']}"
    )

    return text


def notify_admins_support(request):
    text = format_support_request_text(request)
    markup = build_support_status_markup(request['id'], request['status'])
    for admin_id in PERMANENT_ADMINS:
        try:
            bot.send_message(admin_id, text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Failed to send support request to admin {admin_id}: {e}")


def notify_admins_design(order):
    return payment_callbacks.notify_admins_design(order)


def get_user_releases_for_support(user_id):
    """Получить список релизов пользователя для выбора в поддержке"""
    conn = get_pg_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, release_name, release_date, release_type, status
            FROM releases
            WHERE user_id = %s AND (is_track IS NULL OR is_track = FALSE)
            ORDER BY release_date DESC
            LIMIT 20
        ''', (user_id,))
        releases = cursor.fetchall()
        return releases
    except Exception as e:
        logger.error(f"Ошибка при получении релизов для поддержки: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)


def get_release_data_for_support(release_id):
    """Получить данные релиза для автоматического заполнения заявки"""
    conn = get_pg_connection()
    if not conn:
        return {}

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT release_name, release_date, platform_links, artist_name, upc_code
            FROM releases
            WHERE id = %s
        ''', (release_id,))
        release_data = cursor.fetchone()

        if not release_data:
            return {}

        name, date, platform_links, artist_name, upc_code = release_data

        result = {
            'release_name': name,
            'release_date': date.strftime('%d.%m.%Y') if date else None,
            'artist_name': artist_name,
            'upc_code': upc_code
        }

        # Парсим platform_links для получения ссылок на карточки
        if platform_links:
            try:
                if isinstance(platform_links, str):
                    links_data = json.loads(platform_links)
                else:
                    links_data = platform_links

                if isinstance(links_data, dict):
                    # Ищем ссылку на карточку (обычно Яндекс.Музыка или первая доступная)
                    card_link = links_data.get('Яндекс.Музыка') or links_data.get('Яндекс Музыка') or \
                               links_data.get('Spotify') or links_data.get('Apple Music') or \
                               next(iter(links_data.values()), None)
                    if card_link:
                        result['card_link'] = card_link
            except Exception as e:
                logger.error(f"Ошибка при парсинге platform_links: {e}")

        return result
    except Exception as e:
        logger.error(f"Ошибка при получении данных релиза: {e}")
        return {}
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)


def get_user_data_for_support(user_id):
    """Получить данные пользователя для автоматического заполнения заявки"""
    conn = get_pg_connection()
    if not conn:
        return {}

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT name, tg FROM label WHERE telegram_id = %s', (user_id,))
        user_data = cursor.fetchone()

        if not user_data:
            return {}

        name, tg = user_data
        result = {}

        # Приоритет: tg (username) > name
        if tg:
            # Убираем @ если уже есть
            tg_clean = tg.lstrip('@')
            result['nickname'] = f"@{tg_clean}"
        elif name:
            result['nickname'] = name

        return result
    except Exception as e:
        logger.error(f"Ошибка при получении данных пользователя: {e}")
        return {}
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)


def get_auto_filled_data(template_id, release_id=None, user_id=None):
    """Получить автоматически заполненные данные для заявки"""
    auto_data = {}

    # Получаем данные пользователя
    if user_id:
        user_data = get_user_data_for_support(user_id)
        auto_data.update(user_data)

    # Получаем данные релиза
    if release_id:
        release_data = get_release_data_for_support(release_id)
        auto_data.update(release_data)

    return auto_data


def map_field_to_auto_data(field_name):
    """Сопоставить название поля с ключом в автоматически заполненных данных"""
    field_mapping = {
        'Никнейм': 'nickname',
        'Ссылка на карточку': 'card_link',
        'Ссылка на карточку:': 'card_link',
        'UPC': 'upc_code',
        'UPC:': 'upc_code',
        'Исполнитель': 'artist_name',
        'Исполнитель - название релиза': 'artist_name',
        'Название релиза': 'release_name',
        'Исполнитель - релиз': 'artist_name'
    }

    # Нормализуем название поля (убираем двоеточие и лишние пробелы)
    normalized_field = field_name.strip().rstrip(':').strip()

    # Проверяем точное совпадение
    if normalized_field in field_mapping:
        return field_mapping[normalized_field]

    # Проверяем частичное совпадение (ключевые слова)
    field_lower = normalized_field.lower()

    if 'никнейм' in field_lower or 'псевдоним' in field_lower:
        return 'nickname'
    elif 'карточк' in field_lower or 'ссылка на карточку' in field_lower:
        return 'card_link'
    elif 'upc' in field_lower:
        return 'upc_code'
    elif 'исполнитель' in field_lower and 'артист' not in field_lower:
        return 'artist_name'
    elif 'название релиза' in field_lower or 'релиз' in field_lower:
        return 'release_name'

    return None


def prompt_support_details(chat_id, template, user_id=None):
    if not template:
        bot.send_message(chat_id, "❌ Шаблон не найден. Попробуйте выбрать снова.")
        return

    if user_id is None:
        # Пытаемся получить user_id из контекста (если есть)
        user_id = chat_id

    # Для move_release сначала запрашиваем данные по полям (кроме ссылки на релиз и UPC)
    if template['id'] == 'move_release':
        # Показываем форму только с полями, которые нужно заполнить вручную
        fields_to_ask = [f for f in template['fields'] if f not in ['Ссылка на релиз', 'UPC']]
        prompt_support_input_step(chat_id, template, fields_to_ask, user_id)
        return

    # Для videoshot - пошаговый ввод (оставляем как есть)
    if template['id'] == 'videoshot':
        user_data = ensure_user_storage(user_id)
        user_data['videoshot_state'] = {
            'template_id': template['id'],
            'current_field_index': 0,
            'answers': {},
            'release_id': None  # Will be set if user selects a release
        }
        # Получаем релизы пользователя
        releases = get_user_releases_for_support(user_id)

        if releases:
            text = (
                f"📝 {template['title']}\n\n"
                f"{template['description']}\n\n"
                "🎵 Выберите релиз, с которым связана заявка (или пропустите):"
            )

            markup = types.InlineKeyboardMarkup(row_width=1)
            for release_id_item, name, date, release_type, status in releases:
                date_str = date.strftime('%d.%m.%Y') if date else 'Дата не указана'
                btn_text = f"💿 {name} ({date_str})"
                markup.add(types.InlineKeyboardButton(
                    btn_text,
                    callback_data=f"videoshot_select_release:{template['id']}:{release_id_item}"
                ))
            markup.add(types.InlineKeyboardButton(
                "⏭ Пропустить",
                callback_data=f"videoshot_skip_release:{template['id']}"
            ))
            markup.add(types.InlineKeyboardButton(
                "🚫 Отмена",
                callback_data="support_cancel"
            ))

            bot.send_message(chat_id, text, reply_markup=markup)
        else:
            # Если релизов нет, сразу переходим к первому вопросу
            ask_videoshot_question(chat_id, user_id, template['id'], 0)
        return

    # Для всех остальных шаблонов - универсальный поэтапный ввод
    user_data = ensure_user_storage(user_id)
    user_data['support_state'] = {
        'template_id': template['id'],
        'current_field_index': 0,
        'answers': {},
        'release_id': None,
        'auto_filled': {}
    }

    # Получаем релизы пользователя
    releases = get_user_releases_for_support(user_id)

    # Если есть релизы, предлагаем выбрать релиз
    if releases:
        text = (
            f"📝 {template['title']}\n\n"
            f"{template['description']}\n\n"
            "🎵 Выберите релиз, с которым связана заявка (или пропустите):"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        for release_id_item, name, date, release_type, status in releases:
            date_str = date.strftime('%d.%m.%Y') if date else 'Дата не указана'
            btn_text = f"💿 {name} ({date_str})"
            markup.add(types.InlineKeyboardButton(
                btn_text,
                callback_data=f"support_select_release:{template['id']}:{release_id_item}"
            ))
        markup.add(types.InlineKeyboardButton(
            "⏭ Пропустить",
            callback_data=f"support_skip_release:{template['id']}"
        ))
        markup.add(types.InlineKeyboardButton(
            "🚫 Отмена",
            callback_data="support_cancel"
        ))

        bot.send_message(chat_id, text, reply_markup=markup)
    else:
        # Если релизов нет, сразу переходим к поэтапному вводу
        ask_support_question(chat_id, user_id, template['id'], 0)


def prompt_support_input_step(chat_id, template, fields_to_ask, user_id=None):
    """Показать форму ввода для поддержки по шагам (для move_release)"""
    instructions = [
        f"📝 {template['title']}",
        template['description'],
        "",
        "Отправьте одним сообщением по шаблону:"
    ]
    for field in fields_to_ask:
        instructions.append(f"{field}: ...")
    if template.get("note"):
        instructions.extend(["", template["note"]])

    instructions.append("")

    msg = bot.send_message(chat_id, "\n".join(instructions), reply_markup=create_support_cancel_inline_keyboard())
    # Сохраняем поля для обработки
    bot.register_next_step_handler(msg, process_support_input_step_response, template["id"], fields_to_ask, user_id)


def process_support_input_step_response(message, template_id, fields_to_ask, user_id=None):
    """Обработка ответа на вопросы шаблона, затем показ списка релизов"""
    uid = user_id or message.from_user.id
    user_data = ensure_user_storage(uid)
    # Первым делом: если пользователь уже нажал «Отмена», любое следующее сообщение — только «Заявка отменена» и меню
    if user_data.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    # Если отмена уже сбросила состояние — не продолжаем, показываем главное меню
    if template_id == 'move_release' and 'support_request_data' not in user_data:
        user_data.pop("_support_cancelled", None)
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:
        user_data.pop("support_request_data", None)
        handle_main_menu(message)
        return
    if not message.text:
        bot.reply_to(message, "Пожалуйста, отправьте текстовое сообщение.", reply_markup=create_support_cancel_inline_keyboard())
        template = get_support_template(template_id)
        if template:
            prompt_support_input_step(message.chat.id, template, fields_to_ask, user_id or message.from_user.id)
        return

    if is_cancel_message(message):
        user_data = ensure_user_storage(message.from_user.id)
        if 'support_request_data' in user_data:
            del user_data['support_request_data']
        bot.reply_to(message, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return

    template = get_support_template(template_id)
    if not template:
        bot.reply_to(message, "❌ Шаблон не найден. Попробуйте снова.", reply_markup=build_support_keyboard())
        return

    # Сохраняем ответы пользователя во временное хранилище
    user_data = ensure_user_storage(message.from_user.id)
    if 'support_request_data' not in user_data:
        user_data['support_request_data'] = {}

    user_data['support_request_data']['template_id'] = template_id
    user_data['support_request_data']['fields_data'] = message.text.strip()
    user_data['support_request_data']['fields_to_ask'] = fields_to_ask

    # Для move_release - показываем обязательный выбор релиза
    if template_id == 'move_release':
        releases = get_user_releases_for_support(user_id or message.from_user.id)

        if not releases:
            bot.reply_to(message, "❌ У вас пока нет релизов. Сначала создайте релиз.")
            return

        text = (
            f"📝 {template['title']}\n\n"
            "🎵 Теперь выберите релиз, который нужно переместить:"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        for release_id, name, date, release_type, status in releases:
            date_str = date.strftime('%d.%m.%Y') if date else 'Дата не указана'
            btn_text = f"💿 {name} ({date_str})"
            markup.add(types.InlineKeyboardButton(
                btn_text,
                callback_data=f"support_select_release_move:{release_id}"
            ))
        markup.add(types.InlineKeyboardButton(
            "🚫 Отмена",
            callback_data="support_cancel"
        ))

        bot.send_message(message.chat.id, text, reply_markup=markup)
    else:
        # Для других шаблонов - стандартная обработка
        prompt_support_input(message.chat.id, template, None)


def ask_videoshot_question(chat_id, user_id, template_id, field_index):
    """Задать следующий вопрос для videoshot заявки"""
    template = get_support_template(template_id)
    if not template:
        bot.send_message(chat_id, "❌ Шаблон не найден. Попробуйте выбрать снова.")
        return

    user_data = ensure_user_storage(user_id)
    # Первым делом: если пользователь уже нажал «Отмена», любое следующее сообщение — только «Заявка отменена» и меню
    if user_data.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    # Если состояние уже сброшено (например, пользователь нажал «Отмена»), не продолжаем сбор
    if 'videoshot_state' not in user_data:
        bot.send_message(chat_id, "❌ Ошибка: состояние заявки не найдено. Начните заново.")
        return

    user_data['videoshot_state']['current_field_index'] = field_index
    fields = template['fields']

    if field_index < len(fields):
        current_field = fields[field_index]
        question_text = f"📝 Заявка на видеошот\n\n" \
                        f"Вопрос {field_index + 1}/{len(fields)}:\n" \
                        f"{current_field}:"

        if template.get("note") and field_index == len(fields) - 1:  # Add note only for the last question
            question_text += f"\n\n{template['note']}"

        msg = bot.send_message(chat_id, question_text, reply_markup=create_support_cancel_inline_keyboard())
        bot.register_next_step_handler(msg, process_videoshot_answer, template_id, user_id)
    else:
        # All questions asked, process submission
        process_videoshot_submission(chat_id, user_id, template_id)


def process_videoshot_answer(message, template_id, user_id):
    """Обработать ответ на вопрос videoshot заявки"""
    user_data = ensure_user_storage(user_id)
    if 'videoshot_state' not in user_data:
        user_data.pop("_support_cancelled", None)
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:
        user_data.pop("videoshot_state", None)
        handle_main_menu(message)
        return
    if is_cancel_message(message):
        bot.reply_to(message, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        if 'videoshot_state' in user_data:
            del user_data['videoshot_state']
        return

    if 'videoshot_state' not in user_data:
        bot.reply_to(message, "❌ Ошибка: состояние заявки не найдено. Начните заново.", reply_markup=build_support_keyboard())
        return

    state = user_data['videoshot_state']
    template = get_support_template(template_id)
    if not template:
        bot.reply_to(message, "❌ Шаблон не найден. Попробуйте снова.")
        return

    fields = template['fields']
    current_field_index = state['current_field_index']

    if current_field_index < len(fields):
        field_name = fields[current_field_index]
        state['answers'][field_name] = message.text.strip()

        # Move to next question
        next_field_index = current_field_index + 1
        if next_field_index < len(fields):
            ask_videoshot_question(message.chat.id, user_id, template_id, next_field_index)
        else:
            # All questions answered, proceed to submission
            process_videoshot_submission(message.chat.id, user_id, template_id)
    else:
        # Should not happen if logic is correct
        bot.reply_to(message, "❌ Неожиданная ошибка в процессе. Попробуйте начать заново.")
        if 'videoshot_state' in user_data:
            del user_data['videoshot_state']


def process_videoshot_submission(chat_id, user_id, template_id):
    """Сформировать и сохранить заявку videoshot после всех ответов"""
    user_data = ensure_user_storage(user_id)
    if 'videoshot_state' not in user_data:
        bot.send_message(chat_id, "❌ Ошибка: состояние заявки не найдено. Начните заново.")
        return

    state = user_data['videoshot_state']
    template = get_support_template(template_id)
    if not template:
        bot.send_message(chat_id, "❌ Шаблон не найден. Попробуйте снова.")
        return

    # Compile all answers into a single details string
    details_lines = []
    for field in template['fields']:
        answer = state['answers'].get(field, 'Не указано')
        details_lines.append(f"{field}: {answer}")

    if template.get("note"):
        details_lines.append(f"\n{template['note']}")

    details_text = "\n".join(details_lines)

    # Get release info if selected
    release_name = None
    if state['release_id']:
        conn = get_pg_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT release_name, release_date FROM releases WHERE id = %s', (state['release_id'],))
                release_data = cursor.fetchone()
                if release_data:
                    name, date = release_data
                    date_str = date.strftime('%d.%m.%Y') if date else 'Дата не указана'
                    release_name = f"{name} ({date_str})"
            except Exception as e:
                logger.error(f"Ошибка при получении информации о релизе: {e}")
            finally:
                if conn:
                    cursor.close()
                    return_pg_connection(conn)

    request = {
        "id": generate_request_id(),
        "template_id": template_id,
        "template_title": template["title"],
        "details": details_text,
        "status": "принят",
        "user_id": user_id,
        "chat_id": chat_id,
        "user_display": get_display_username(bot.get_chat_member(chat_id, user_id).user),
        "created_at": datetime.now().isoformat(),
        "release_id": state['release_id'],
        "release_name": release_name
    }
    SUPPORT_REQUESTS.append(request)

    # Save to DB
    save_support_request_to_db(
        user_id=user_id,
        template_id=template_id,
        template_title=template["title"],
        details=details_text,
        release_id=state['release_id'],
        release_name=release_name
    )

    bot.send_message(
        chat_id,
        f"✅ Заявка «{template['title']}» принята. Текущий статус: принят.\n"
        "Мы уведомили администратора и сообщим об обновлениях."
    )

    notify_admins_support(request)

    # Clear state
    if 'videoshot_state' in user_data:
        del user_data['videoshot_state']


def ask_support_question(chat_id, user_id, template_id, field_index):
    """Задать следующий вопрос для заявки поддержки (универсальная функция)"""
    template = get_support_template(template_id)
    if not template:
        bot.send_message(chat_id, "❌ Шаблон не найден. Попробуйте выбрать снова.")
        return

    user_data = ensure_user_storage(user_id)
    # Проверяем, не была ли заявка отменена
    if user_data.pop("_support_cancelled", None):
        bot.send_message(chat_id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return

    # Если состояние еще не создано (например, при отсутствии релизов), создаем его
    if 'support_state' not in user_data:
        user_data['support_state'] = {
            'template_id': template_id,
            'current_field_index': 0,
            'answers': {},
            'release_id': None,
            'auto_filled': {}
        }
        # Получаем автоматически заполненные данные только из профиля пользователя
        auto_data = get_auto_filled_data(template_id, None, user_id)
        user_data['support_state']['auto_filled'] = auto_data

    state = user_data['support_state']
    state['current_field_index'] = field_index
    fields = template['fields']

    if field_index < len(fields):
        current_field = fields[field_index]

        # Проверяем, есть ли автоматически заполненное значение для этого поля
        auto_data_key = map_field_to_auto_data(current_field)
        auto_value = None
        if auto_data_key and auto_data_key in state.get('auto_filled', {}):
            auto_value = state['auto_filled'][auto_data_key]

        # Формируем текст вопроса
        question_text = f"📝 {template['title']}\n\n"

        # Показываем информацию о выбранном релизе, если есть
        if state.get('release_id'):
            release_data = get_release_data_for_support(state['release_id'])
            if release_data.get('release_name'):
                date_str = release_data.get('release_date', '')
                question_text += f"🎵 Выбранный релиз: {release_data['release_name']}"
                if date_str:
                    question_text += f" ({date_str})"
                question_text += "\n\n"

        question_text += f"Вопрос {field_index + 1}/{len(fields)}:\n{current_field}:"

        # Если есть автоматически заполненное значение, показываем его
        if auto_value:
            question_text += f"\n\n✅ Автоматически заполнено: {auto_value}\n\nВы можете оставить это значение (отправьте \"+\", \"да\" или \"ок\") или ввести новое:"
            # Не предзаполняем сразу, дадим пользователю выбор
        else:
            question_text += "\n"

        if template.get("note") and field_index == len(fields) - 1:
            question_text += f"\n{template['note']}"

        msg = bot.send_message(chat_id, question_text, reply_markup=create_support_cancel_inline_keyboard())
        bot.register_next_step_handler(msg, process_support_answer, template_id, user_id)
    else:
        # Все вопросы заданы, обрабатываем заявку
        process_support_submission_final(chat_id, user_id, template_id)


def process_support_answer(message, template_id, user_id):
    """Обработать ответ на вопрос заявки поддержки"""
    user_data = ensure_user_storage(user_id)

    if 'support_state' not in user_data:
        user_data.pop("_support_cancelled", None)
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return

    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:
        user_data.pop("support_state", None)
        handle_main_menu(message)
        return

    if is_cancel_message(message):
        bot.reply_to(message, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        if 'support_state' in user_data:
            del user_data['support_state']
        return

    state = user_data['support_state']
    template = get_support_template(template_id)
    if not template:
        bot.reply_to(message, "❌ Шаблон не найден. Попробуйте снова.")
        return

    fields = template['fields']
    current_field_index = state['current_field_index']

    if current_field_index < len(fields):
        field_name = fields[current_field_index]
        user_input = message.text.strip()

        # Проверяем, есть ли автоматически заполненное значение для этого поля
        auto_data_key = map_field_to_auto_data(field_name)
        auto_value = None
        if auto_data_key and auto_data_key in state.get('auto_filled', {}):
            auto_value = state['auto_filled'][auto_data_key]

        # Если пользователь отправил "+", "да" или "ок", используем предзаполненное значение
        if user_input.lower() in ['+', 'да', 'yes', 'ok', 'ок', 'оставить', 'оставить как есть'] and auto_value:
            state['answers'][field_name] = auto_value
        else:
            # Пользователь ввел новое значение
            state['answers'][field_name] = user_input

        # Переходим к следующему вопросу
        next_field_index = current_field_index + 1
        if next_field_index < len(fields):
            ask_support_question(message.chat.id, user_id, template_id, next_field_index)
        else:
            # Все вопросы отвечены, обрабатываем заявку
            process_support_submission_final(message.chat.id, user_id, template_id)
    else:
        bot.reply_to(message, "❌ Неожиданная ошибка в процессе. Попробуйте начать заново.")
        if 'support_state' in user_data:
            del user_data['support_state']


def process_support_submission_final(chat_id, user_id, template_id):
    """Сформировать и сохранить заявку поддержки после всех ответов"""
    user_data = ensure_user_storage(user_id)
    if 'support_state' not in user_data:
        bot.send_message(chat_id, "❌ Ошибка: состояние заявки не найдено. Начните заново.")
        return

    state = user_data['support_state']
    template = get_support_template(template_id)
    if not template:
        bot.send_message(chat_id, "❌ Шаблон не найден. Попробуйте снова.")
        return

    # Формируем детали заявки из ответов
    details_lines = []
    for field in template['fields']:
        answer = state['answers'].get(field, 'Не указано')
        details_lines.append(f"{field}: {answer}")

    if template.get("note"):
        details_lines.append(f"\n{template['note']}")

    details_text = "\n".join(details_lines)

    # Получаем информацию о релизе, если выбран
    release_name = None
    release_id = state.get('release_id')
    if release_id:
        release_data = get_release_data_for_support(release_id)
        if release_data.get('release_name'):
            date_str = release_data.get('release_date', '')
            release_name = release_data['release_name']
            if date_str:
                release_name += f" ({date_str})"

    request = {
        "id": generate_request_id(),
        "template_id": template_id,
        "template_title": template["title"],
        "details": details_text,
        "status": "принят",
        "user_id": user_id,
        "chat_id": chat_id,
        "user_display": get_display_username(bot.get_chat_member(chat_id, user_id).user),
        "created_at": datetime.now().isoformat(),
        "release_id": release_id,
        "release_name": release_name
    }
    SUPPORT_REQUESTS.append(request)

    # Сохраняем в БД
    save_support_request_to_db(
        user_id=user_id,
        template_id=template_id,
        template_title=template["title"],
        details=details_text,
        release_id=release_id,
        release_name=release_name
    )

    bot.send_message(
        chat_id,
        f"✅ Заявка «{template['title']}» принята. Текущий статус: принят.\n"
        "Мы уведомили администратора и сообщим об обновлениях."
    )

    notify_admins_support(request)

    # Очищаем состояние
    if 'support_state' in user_data:
        del user_data['support_state']


def prompt_support_input(chat_id, template, release_id=None):
    """Показать форму ввода для поддержки (старая функция, оставлена для совместимости)"""
    # Эта функция больше не используется для новых заявок, но оставлена для обратной совместимости
    release_info = ""
    if release_id:
        conn = get_pg_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT release_name, release_date FROM releases WHERE id = %s', (release_id,))
                release_data = cursor.fetchone()
                if release_data:
                    name, date = release_data
                    date_str = date.strftime('%d.%m.%Y') if date else 'Дата не указана'
                    release_info = f"\n🎵 Выбранный релиз: {name} ({date_str})\n"
            except Exception as e:
                logger.error(f"Ошибка при получении информации о релизе: {e}")
            finally:
                if conn:
                    cursor.close()
                    return_pg_connection(conn)

    instructions = [
        f"📝 {template['title']}",
        release_info,
        template['description'],
        "",
        "Отправьте одним сообщением по шаблону:"
    ]
    for field in template['fields']:
        instructions.append(f"{field}: ...")
    if template.get("note"):
        instructions.extend(["", template["note"]])

    instructions.append("")

    msg = bot.send_message(chat_id, "\n".join(instructions), reply_markup=create_support_cancel_inline_keyboard())
    bot.register_next_step_handler(msg, process_support_submission, template["id"], release_id)


def save_support_request_to_db(user_id, template_id, template_title, details, release_id=None, release_name=None):
    """Сохранить заявку поддержки в базу данных"""
    conn = get_pg_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для сохранения заявки")
        return None

    try:
        cursor = conn.cursor()

        # Проверяем существование таблицы
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'support_requests'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            # Создаем таблицу, если её нет
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_requests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    template_id VARCHAR(50),
                    template_title VARCHAR(255),
                    details TEXT,
                    request_data JSONB,
                    status VARCHAR(20) DEFAULT 'принят',
                    release_id INTEGER,
                    release_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

        # Сохраняем заявку
        request_data = {
            "details": details,
            "release_id": release_id,
            "release_name": release_name
        }

        cursor.execute("""
            INSERT INTO support_requests
            (user_id, template_id, template_title, details, request_data, status, release_id, release_name, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, template_id, template_title, details, json.dumps(request_data), 'принят', release_id, release_name, datetime.now()))

        request_db_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"Заявка поддержки сохранена в БД с ID: {request_db_id}")
        return request_db_id

    except Exception as e:
        logger.error(f"Ошибка при сохранении заявки в БД: {e}")
        conn.rollback()
        return None
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)


def process_support_submission(message, template_id, release_id=None):
    user_data = ensure_user_storage(message.from_user.id)
    # Первым делом: если пользователь уже нажал «Отмена», любое следующее сообщение — только «Заявка отменена» и меню
    if user_data.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    # Если состояние сброшено отменой — не продолжаем
    if template_id == 'move_release' and 'support_request_data' not in user_data:
        user_data.pop("_support_cancelled", None)
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:
        user_data.pop("support_request_data", None)
        handle_main_menu(message)
        return
    if not message.text:
        bot.reply_to(message, "Пожалуйста, отправьте текстовое сообщение.", reply_markup=create_support_cancel_inline_keyboard())
        template = get_support_template(template_id)
        if template:
            prompt_support_input(message.chat.id, template, release_id)
        return

    if is_cancel_message(message):
        bot.reply_to(message, "🚫 Заявка отменена.")
        return

    template = get_support_template(template_id)
    if not template:
        bot.reply_to(message, "❌ Шаблон не найден. Попробуйте снова.")
        return

    # Получаем информацию о релизе, если выбран
    release_name = None
    if release_id:
        conn = get_pg_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT release_name, release_date FROM releases WHERE id = %s', (release_id,))
                release_data = cursor.fetchone()
                if release_data:
                    name, date = release_data
                    date_str = date.strftime('%d.%m.%Y') if date else 'Дата не указана'
                    release_name = f"{name} ({date_str})"
            except Exception as e:
                logger.error(f"Ошибка при получении информации о релизе: {e}")
            finally:
                if conn:
                    cursor.close()
                    return_pg_connection(conn)

    request = {
        "id": generate_request_id(),
        "template_id": template_id,
        "template_title": template["title"],
        "details": message.text.strip(),
        "status": "принят",
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "user_display": get_display_username(message.from_user),
        "created_at": datetime.now().isoformat(),
        "release_id": release_id,
        "release_name": release_name
    }
    SUPPORT_REQUESTS.append(request)

    # Сохраняем в БД
    save_support_request_to_db(
        user_id=message.from_user.id,
        template_id=template_id,
        template_title=template["title"],
        details=message.text.strip(),
        release_id=release_id,
        release_name=release_name
    )

    bot.reply_to(
        message,
        f"✅ Заявка «{template['title']}» принята. Текущий статус: принят.\n"
        "Мы уведомили администратора и сообщим об обновлениях."
    )

    notify_admins_support(request)



def _clear_support_next_step_handlers(chat_id, user_id):
    """Сбрасывает все возможные ключи next_step для данного чата/пользователя (pyTelegramBotAPI может использовать chat_id или (chat_id, user_id))."""
    try:
        if not hasattr(bot, 'next_step_backend') or not hasattr(bot.next_step_backend, 'clear_handlers'):
            return
        backend = bot.next_step_backend
        backend.clear_handlers(chat_id)
        backend.clear_handlers((chat_id, user_id))
        backend.clear_handlers(user_id)
        if hasattr(backend, 'handlers') and isinstance(backend.handlers, dict):
            for key in list(backend.handlers.keys()):
                if key == chat_id or key == user_id or key == (chat_id, user_id):
                    backend.handlers.pop(key, None)
    except Exception:
        pass



def handle_admin_support_main(call):
    """Entry point for admin support section"""
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.")
        return

    support_summary = get_status_summary(SUPPORT_REQUESTS, SUPPORT_REQUEST_STATUSES)

    text = (
        "🆘 Раздел поддержки\n\n"
        "📩 Заявки поддержки:\n"
        f"{support_summary}\n\n"
        "Выберите, что посмотреть:"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🆘 Список заявок поддержки", callback_data="admin_support_list"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )


def show_support_list(call):
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(call.id, "У вас нет доступа.")
        return

    if not SUPPORT_REQUESTS:
        text = "🆘 Заявок поддержки пока нет."
    else:
        text_lines = ["🆘 Заявки поддержки (последние 10):", ""]
        for request in sorted(SUPPORT_REQUESTS, key=lambda x: x["created_at"], reverse=True)[:10]:
            text_lines.append(
                f"• {request['template_title']} | {request['status']} | "
                f"{format_human_datetime(request['created_at'])}"
            )
        text_lines.append("\nВыберите заявку для подробностей.")
        text = "\n".join(text_lines)

    markup = types.InlineKeyboardMarkup(row_width=1)
    for request in sorted(SUPPORT_REQUESTS, key=lambda x: x["created_at"], reverse=True)[:10]:
        caption = f"{request['template_title']} ({request['status']})"
        markup.add(types.InlineKeyboardButton(
            caption,
            callback_data=f"support_detail_{request['id']}"
        ))
    markup.add(
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_support")
    )

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )


def handle_admin_orders_main(call):
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.")
        return

    lines = ["🛒 Заказы по услугам:\n"]
    for key, label in SERVICE_LABELS.items():
        filtered = [order for order in DESIGN_BRIEF_REQUESTS if order["service"] == key]
        summary = get_status_summary(filtered, DESIGN_ORDER_STATUSES)
        lines.append(f"{label}:\n{summary}\n")

    if DESIGN_BRIEF_REQUESTS:
        lines.append("Последние заявки:\n")
        recent = sorted(DESIGN_BRIEF_REQUESTS, key=lambda x: x["created_at"], reverse=True)[:5]
        for order in recent:
            label = SERVICE_LABELS.get(order["service"], order["service"])
            lines.append(
                f"{label}: {order['user_display']} • {order['status']} • {format_human_datetime(order['created_at'])}"
            )
        lines.append("\nВыберите категорию, чтобы открыть полный список.")
    else:
        lines.append("Пока заказов нет.")

    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, label in SERVICE_LABELS.items():
        markup.add(types.InlineKeyboardButton(f"{label}", callback_data=f"admin_orders_{key}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))

    bot.edit_message_text(
        "\n".join(lines),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )


def show_orders_list(call, service):
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(call.id, "У вас нет доступа.")
        return

    label = SERVICE_LABELS.get(service, service)
    orders = [order for order in DESIGN_BRIEF_REQUESTS if order["service"] == service]

    if not orders:
        text = f"🛒 Заказов для категории «{label}» пока нет."
    else:
        text_lines = [f"🛒 {label} – последние заявки:\n"]
        for order in sorted(orders, key=lambda x: x["created_at"], reverse=True)[:10]:
            text_lines.append(
                f"• {order['status']} | {format_human_datetime(order['created_at'])}"
            )
        text_lines.append("\nВыберите заказ для подробностей.")
        text = "\n".join(text_lines)

    markup = types.InlineKeyboardMarkup(row_width=1)
    for order in sorted(orders, key=lambda x: x["created_at"], reverse=True)[:10]:
        markup.add(types.InlineKeyboardButton(
            f"{order['status'].title()} ({format_human_datetime(order['created_at'])})",
            callback_data=f"order_detail_{order['id']}"
        ))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_orders"))

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )


def show_support_detail(call, request_id):
    request = next((req for req in SUPPORT_REQUESTS if req["id"] == request_id), None)
    if not request:
        bot.answer_callback_query(call.id, "Заявка не найдена", show_alert=True)
        return

    text = format_support_request_text(request)
    markup = build_support_status_markup(request_id, request["status"])
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_support_list"))

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )



@require_channel_subscription
def handle_help(message):
    """Handle help/support section"""
    help_text = (
        "❓ Помощь и поддержка\n\n"
        "Выберите готовый шаблон обращения или напишите менеджеру напрямую.\n"
        "Все заявки получают статусы: принят / требует уточнения / решен.\n\n"
        "💡 Команды:\n"
        "/start – главная страница\n"
        "/main – вернуться в меню\n"
        "/cancel – отмена текущего ввода\n"
        "/admin – панель администратора\n\n"
        f"⏰ Менеджер работает с {SUPPORT_HOURS}\n"
        "❗️ Формулируйте вопрос одним сообщением.\n"
        f"💬 Менеджер: {MANAGER_USERNAME}"
    )

    bot.reply_to(message, help_text, reply_markup=build_support_keyboard())


@require_channel_subscription
def handle_statistics(message):
    """Handle statistics section"""
    user_id = message.from_user.id

    conn = get_pg_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
        return

    try:
        cursor = conn.cursor()

        # Получаем статистику пользователя
        cursor.execute('SELECT COUNT(*) FROM releases WHERE user_id = %s', (user_id,))
        releases_count = cursor.fetchone()[0]

        cursor.execute('SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s', (user_id,))
        balance_result = cursor.fetchone()
        balance = balance_result[0] if balance_result else 0

        cursor.execute('SELECT COUNT(*) FROM orders WHERE user_id = %s AND status = %s', (user_id, 'completed'))
        orders_count = cursor.fetchone()[0]

        stats_text = (
            f"📊 Ваша статистика\n\n"
            f"🎵 Релизов: {releases_count}\n"
            f"💰 Баланс: {balance:,.2f}₽\n"
            f"✅ Завершенных заказов: {orders_count}\n\n"
            f"📈 Продолжайте развиваться!"
        )

        bot.reply_to(message, stats_text)

    except Exception as e:
        logger.error(f"Error getting user statistics: {e}")
        bot.reply_to(message, "❌ Ошибка при получении статистики.")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)


@require_channel_subscription
def handle_support(message):
    """Handle support section"""
    support_text = (
        f"📞 Поддержка TWAS Label Studio\n\n"
        f"⏰ Время работы: {SUPPORT_HOURS}\n"
        f"💬 Менеджер: {MANAGER_USERNAME}\n"
        f"👑 Владелец: {OWNER_USERNAME}\n\n"
        "⬇️ Можете выбрать готовый шаблон обращения ниже или написать менеджеру напрямую."
    )

    markup = build_support_keyboard()
    markup.add(types.InlineKeyboardButton(
        "👑 Связаться с владельцем",
        url=f"https://t.me/{OWNER_USERNAME[1:]}"
    ))

    bot.reply_to(message, support_text, reply_markup=markup)



def process_free_support_question(message):
    """Обработка свободного вопроса в поддержку"""
    user_data = ensure_user_storage(message.from_user.id)
    if user_data.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:
        handle_main_menu(message)
        return
    if not message.text:
        bot.reply_to(message, "Пожалуйста, отправьте текстовое сообщение.", reply_markup=create_support_cancel_inline_keyboard())
        bot.register_next_step_handler(message, process_free_support_question)
        return

    if is_cancel_message(message):
        bot.reply_to(message, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return

    request = {
        "id": generate_request_id(),
        "template_id": "free_question",
        "template_title": "Свободный вопрос",
        "details": message.text.strip(),
        "status": "принят",
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "user_display": get_display_username(message.from_user),
        "created_at": datetime.now().isoformat(),
        "release_id": None,
        "release_name": None
    }
    SUPPORT_REQUESTS.append(request)

    bot.reply_to(
        message,
        "✅ Ваш вопрос принят. Текущий статус: принят.\n"
        "Мы уведомили администратора и сообщим об обновлениях."
    )

    notify_admins_support(request)


@require_channel_subscription
def handle_about(message):
    """Handle about section"""
    about_text = (
        f"ℹ️ О TWAS Label Studio\n\n"
        f"🎵 Мы работаем с 2019 года\n"
        f"🌍 Дистрибуция на всех мировых площадках\n"
        f"🎨 Профессиональный дизайн обложек\n"
        f"🎬 Motion обложки для соцсетей\n"
        f"🎤 Студия звукозаписи\n\n"
        f"📢 Наш канал: {CHANNEL_USERNAME}\n"
        f"🔗 Сайт: {WEB_APP_URL}\n\n"
        f"💼 Лицензионные договоры\n"
        f"📊 Детальная статистика\n"
        f"💰 Прозрачные выплаты"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "📢 Подписаться на канал",
        url=f"https://t.me/{CHANNEL_USERNAME[1:]}"
    ))
    markup.add(types.InlineKeyboardButton(
        "🌐 Открыть приложение",
        web_app=types.WebAppInfo(url=f"{WEB_APP_URL}?tgid={message.from_user.id}")
    ))

    bot.reply_to(message, about_text, reply_markup=markup)



# Дублированный обработчик удален - используется handle_admin_back на строке 8663



# Admin report file upload flow migrated to handlers/admin_report_flow.py.


def handle_my_releases(message, user_id=None, admin_mode=False):
    """Show user's releases with albums and tracks (admin mode support)"""
    logger.info(f"handle_my_releases called with user_id={user_id}, admin_mode={admin_mode}")
    if user_id is None:
        user_id = message.from_user.id

    conn = get_pg_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
        return

    try:
        cursor = conn.cursor()

        # Get albums
        cursor.execute('''
            SELECT id, release_name, release_date, status
            FROM releases
            WHERE user_id = %s AND is_album = TRUE
            ORDER BY release_date DESC
        ''', (user_id,))
        albums = cursor.fetchall()

        # Get single tracks (not part of album)
        cursor.execute('''
            SELECT id, release_name, release_date, status
            FROM releases
            WHERE user_id = %s AND is_album = FALSE AND is_track = FALSE
            ORDER BY release_date DESC
        ''', (user_id,))
        singles = cursor.fetchall()

        response_text = "📀 Релизы пользователя:\n" if admin_mode else "📀 Ваши релизы:"

        # Create inline keyboard
        markup = types.InlineKeyboardMarkup(row_width=1)

        # Add albums
        for album in albums:
            album_id, name, date, status = album
            date_str = date.strftime('%d.%m.%Y') if date else "дата не указана"
            btn_text = f"💿 {name} ({date_str}) - {status}"
            callback_data = f"album_detail_{album_id}_admin" if admin_mode else f"album_detail_{album_id}"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))

        # Add singles
        for single in singles:
            release_id, name, date, status = single
            date_str = date.strftime('%d.%m.%Y') if date else "дата не указана"
            btn_text = f"🎵 {name} ({date_str}) - {status}"
            callback_data = f"my_release_detail_{release_id}_admin" if admin_mode else f"my_release_detail_{release_id}"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))

        # Add back button - ИСПРАВЛЕНИЕ ЗДЕСЬ
        if admin_mode:
            markup.add(types.InlineKeyboardButton(
                "◀️ Назад к списку пользователей",  # Измененный текст
                callback_data="admin_releases"  # Возврат к списку пользователей в разделе Релизы
            ))
        else:
            markup.add(types.InlineKeyboardButton(
                "◀️ Назад в профиль",
                callback_data="back_to_profile"
            ))

        try:
            if isinstance(message, types.Message) and message.from_user.id != bot.get_me().id:
                bot.send_message(message.chat.id, response_text, reply_markup=markup)
            else:
                bot.edit_message_text(response_text, message.chat.id, message.message_id, reply_markup=markup)
        except Exception as e:
            logger.debug(f"Could not edit message, sending new one: {e}")
            bot.send_message(message.chat.id, response_text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in handle_my_releases: {e}")
        error_msg = "❌ Произошла ошибка при получении списка релизов."
        try:
            bot.send_message(message.chat.id, error_msg)
        except:
            pass
            bot.reply_to(message, error_msg)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)



def show_album_details(call, album_id, admin_mode=False):
    """Show details of an album and its tracks (admin mode support)"""
    logger.info(f"show_album_details called with admin_mode={admin_mode}, album_id={album_id}")
    user_id = call.from_user.id if not admin_mode else None

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()

        # Get album info
        query = '''
            SELECT release_name, release_date, status, user_id, upc_code, platform_links
            FROM releases
            WHERE id = %s
        '''
        params = (album_id,)

        if not admin_mode:
            query += ' AND user_id = %s'
            params = (album_id, user_id)

        cursor.execute(query, params)
        album = cursor.fetchone()

        if not album:
            bot.answer_callback_query(call.id, "❌ Альбом не найден", show_alert=True)
            return

        album_name, album_date, album_status, owner_id, upc_code, platform_links = album
        user_id = owner_id  # For admin mode

        # Determine platform links availability
        parsed_platform_links = {}
        if platform_links:
            if isinstance(platform_links, str):
                try:
                    parsed_platform_links = json.loads(platform_links)
                except json.JSONDecodeError:
                    parsed_platform_links = {}
            elif isinstance(platform_links, dict):
                parsed_platform_links = platform_links
        has_platform_links = bool(parsed_platform_links)

        # Get tracks in album
        cursor.execute('''
            SELECT id, release_name, track_number
            FROM releases
            WHERE album_id = %s
            ORDER BY track_number
        ''', (album_id,))
        tracks = cursor.fetchall()

        # Format album details
        details = (
            f"💿 Альбом: {album_name}\n\n"
            f"📅 Дата релиза: {album_date.strftime('%d.%m.%Y') if album_date else 'дата не указана'}\n"
            f"🟢 Статус: {album_status}\n"
            f"🔖 UPC код: {upc_code or 'не указан'}\n\n"
            "🎵 Треки в альбоме:"
        )

        # Create inline keyboard for tracks
        markup = types.InlineKeyboardMarkup(row_width=1)

        # Add admin controls for album if in admin mode
        if admin_mode:
            markup.add(types.InlineKeyboardButton(
                "🔄 Изменить статус альбома",
                callback_data=f"album_status_update_{album_id}"
            ))
            markup.add(types.InlineKeyboardButton(
                "🏷️ Изменить UPC код альбома",
                callback_data=f"album_upc_update_{album_id}"
            ))
            markup.add(types.InlineKeyboardButton(
                "🔗 Изменить ссылку",
                callback_data=f"quick_link_menu_{album_id}"
            ))
            markup.add(types.InlineKeyboardButton("", callback_data="separator"))  # Separator

        for track in tracks:
            track_id, track_name, track_number = track
            btn_text = f"{track_number}. {track_name}"
            callback_data = f"my_release_detail_{track_id}_admin" if admin_mode else f"my_release_detail_{track_id}"
            markup.add(types.InlineKeyboardButton(
                btn_text,
                callback_data=callback_data
            ))

        # Report requests are now only available in user profile

        # Add back button
        if admin_mode:
            markup.add(types.InlineKeyboardButton(
                "◀️ Назад к релизам",
                callback_data=f"user_releases_{user_id}"
            ))
        else:
            markup.add(types.InlineKeyboardButton(
                "◀️ Назад к моим релизам",
                callback_data="back_to_my_releases"
            ))

        bot.edit_message_text(
            f"<code>{details}</code>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )

    except Exception as e:
        logger.error(f"Error fetching album details: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)





def show_my_release_details(call, release_id, admin_mode=False):
    """Show details of user's release (with admin-only options)"""
    user_id = call.from_user.id if not admin_mode else None
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        query = '''
            SELECT
                release_type, artist_name, release_name, producer, genre,
                release_date, performer_name, music_author, explicit_content,
                yandex_soon, create_links, tiktok_commercial, tiktok_full_version, status,
                upc_code, user_id, platform_links, preview_start
            FROM releases
            WHERE id = %s
        '''
        params = (release_id,)

        if not admin_mode:
            query += ' AND user_id = %s'
            params = (release_id, user_id)

        cursor.execute(query, params)
        release = cursor.fetchone()

        if not release:
            bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
            return

        # Unpack release data
        (
            release_type, artist_name, release_name, producer, genre,
            release_date, performer_name, music_author, explicit_content,
            yandex_soon, create_links, tiktok_commercial, tiktok_full_version, status,
            upc_code, user_id, platform_links, preview_start
        ) = release

        owner_id = user_id  # For admin mode

        # Determine platform links availability
        parsed_platform_links = {}
        if platform_links:
            if isinstance(platform_links, str):
                try:
                    parsed_platform_links = json.loads(platform_links)
                except json.JSONDecodeError:
                    parsed_platform_links = {}
            elif isinstance(platform_links, dict):
                parsed_platform_links = platform_links
        has_platform_links = bool(parsed_platform_links)

        # Format release details
        tiktok_seconds_text = f"{preview_start} сек" if preview_start else "Не указано"
        details = (
            f"📀 Детали релиза: {release_name}\n\n"
            f"🎵 Тип: {release_type}\n"
            f"🎤 Артист: {artist_name}\n"
            f"🎹 Продюсер: {producer or 'Не указан'}\n"
            f"🎼 Жанр: {genre}\n"
            f"📅 Дата релиза: {release_date.strftime('%d.%m.%Y')}\n"
            f"👤 Исполнитель: {performer_name}\n"
            f"✍️ Автор музыки: {music_author}\n"
            f"🔞 Explicit: {'Да' if explicit_content else 'Нет'}\n"
            f"🟢 Яндекс 'Скоро': {'Да' if yandex_soon else 'Нет'}\n"
            f"🔗 Создать ссылки: {'Да' if create_links else 'Нет'}\n"
            f"📱 TikTok коммерч.: {'Да' if tiktok_commercial else 'Нет'}\n"
            f"🎵 TikTok полная версия: {'Да' if tiktok_full_version else 'Нет'}\n"
            f"⏱️ Секунды TikTok: {tiktok_seconds_text}\n"
            f"🟢 Статус: {status}\n"
            f"🔖 UPC код: {upc_code or 'пока что нет'}\n"
        )

        # Create inline keyboard for actions
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "📎 Показать вложения",
                callback_data=f"show_attachments_{release_id}_admin" if admin_mode else f"show_attachments_{release_id}"
            )
        )
        # Add edit release button for users
        if not admin_mode and status in ["В обработке", "Готов к отгрузке"]:
            markup.add(
                types.InlineKeyboardButton(
                    "✏️ Редактировать релиз",
                    callback_data=f"edit_release_{release_id}"
                )
            )

        # Add admin-only buttons
        if admin_mode:
            markup.add(
                types.InlineKeyboardButton(
                    "🔄 Изменить статус",
                    callback_data=f"change_status_{release_id}"
                ),
                types.InlineKeyboardButton(
                    "🔖 Изменить UPC код",
                    callback_data=f"change_upc_{release_id}"
                )
            )

            markup.add(
                types.InlineKeyboardButton(
                    "🔗 Изменить ссылку",
                    callback_data=f"quick_link_menu_{release_id}"
                )
            )

        # Add back button
        if admin_mode:
            markup.add(types.InlineKeyboardButton(
                "◀️ Назад к релизам",
                callback_data=f"user_releases_{user_id}"
            ))
        else:
            markup.add(types.InlineKeyboardButton(
                "◀️ Назад к моим релизам",
                callback_data="back_to_my_releases"
            ))

        bot.edit_message_text(
            details,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error fetching release details: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)



def create_status_selection_keyboard(release_id):
    """Create keyboard with status options for a specific release"""
    markup = types.InlineKeyboardMarkup(row_width=1)

    for status in RELEASE_STATUSES:
        markup.add(types.InlineKeyboardButton(
            f"🔄 {status.capitalize()}",
            callback_data=f"status_update_{release_id}_{status}"
        ))

    return markup



def handle_service_release_for_artist(call):
    return service_artist_release.handle_service_release_for_artist(call)


def process_artist_user_id(message):
    return service_artist_release.process_artist_user_id(message)


def modify_distribution_for_artist_release(admin_id: int, target_user_id: int):
    return service_artist_release.modify_distribution_for_artist_release(admin_id, target_user_id)




def handle_admin_finance(call):
    """Handle finance management"""
    conn = get_pg_connection()
    if not conn:
        bot.edit_message_text(
            "❌ Ошибка подключения к базе данных. Попробуйте позже.",
            call.message.chat.id,
            call.message.message_id
        )
        return

    try:
        cursor = conn.cursor()

        # Get total revenue
        cursor.execute('SELECT SUM(amount) FROM orders WHERE status = %s', ("completed",))
        result_total = cursor.fetchone()
        total_revenue = result_total[0] if result_total and result_total[0] is not None else 0

        # Get today's revenue
        today = datetime.now().date()  # Get only date part
        cursor.execute('SELECT SUM(amount) FROM orders WHERE status = %s AND DATE(created_date) = %s',
                       ("completed", today,))
        result_today = cursor.fetchone()
        today_revenue = result_today[0] if result_today and result_today[0] is not None else 0

        finance_text = (
            "💰 Финансовая статистика\n\n"
            f"Общий доход: {total_revenue:,.2f}₽\n"
            f"Доход за сегодня: {today_revenue:,.2f}₽"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📊 Подробная статистика", callback_data="finance_stats"),
            types.InlineKeyboardButton("💳 История платежей", callback_data="finance_history"),
            types.InlineKeyboardButton("🎟 Управление промокодами", callback_data="finance_promo"),
            types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
        )

        bot.edit_message_text(
            finance_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Error as e:
        logger.error(f"PostgreSQL error in handle_admin_finance: {e}")
        bot.edit_message_text(
            "❌ Произошла ошибка при получении финансовой статистики.",
            call.message.chat.id,
            call.message.message_id
        )
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)



def handle_admin_promo(call):
    """Handle promo codes management"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Создать промокод", callback_data="promo_create"),
        types.InlineKeyboardButton("📊 Статистика промокодов", callback_data="promo_stats"),
        types.InlineKeyboardButton("❌ Удалить промокод", callback_data="promo_delete"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
    )

    bot.edit_message_text(
        "🎟 Управление промокодами",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )



# Обработчик handle_promo_fix_structure удален


# Обработчик handle_fix_promo_table удален



def handle_admin_schedule(call):
    """Handle studio schedule management"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📅 Расписание на сегодня", callback_data="schedule_today"),
        types.InlineKeyboardButton("➕ Добавить слот", callback_data="schedule_add"),
        types.InlineKeyboardButton("❌ Удалить слот", callback_data="schedule_delete"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
    )

    bot.edit_message_text(
        "📅 Управление расписанием студии",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )


def notify_level_change(user_id, new_levels, old_levels=None):
    """Notify user about level changes"""
    if old_levels is None:
        old_levels = []

    # Convert to sets for easy comparison
    new_set = set(new_levels)
    old_set = set(old_levels)

    # Find added and removed levels
    added_levels = new_set - old_set
    removed_levels = old_set - new_set

    # Prepare message
    message_parts = []
    if added_levels:
        message_parts.append(f"🎉 Вам добавлены уровни: {', '.join(added_levels)}")
    if removed_levels:
        message_parts.append(f"❌ У вас удалены уровни: {', '.join(removed_levels)}")

    if message_parts:
        message = "\n".join(message_parts)
        message += "\n\nТекущие уровни: " + ", ".join(new_levels)
        bot.send_message(user_id, message)


def update_user_levels(user_id, new_level):
    """Update user levels and notify about changes"""
    conn = get_pg_connection()
    if not conn:
        logger.error("Could not connect to database in update_user_levels")
        return

    try:
        cursor = conn.cursor()

        # Get current role
        cursor.execute('SELECT role FROM label WHERE telegram_id = %s', (user_id,))
        result = cursor.fetchone()
        old_level = result[0] if result else None

        # Update role
        cursor.execute('UPDATE label SET role = %s WHERE telegram_id = %s',
                       (new_level, user_id))
        conn.commit()

        # Notify user about changes
        notify_level_change(user_id, [new_level], [old_level] if old_level else [])
    except Error as e:
        logger.error(f"PostgreSQL error in update_user_levels: {e}")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)


def handle_admin_levels(call):
    """Handle user level management"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить уровень пользователю", callback_data="level_add"),
        types.InlineKeyboardButton("➖ Удалить уровень у пользователя", callback_data="level_remove"),
        types.InlineKeyboardButton("👥 Список пользователей по уровням", callback_data="level_list"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
    )

    bot.edit_message_text(
        "Управление уровнями пользователей:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )



# =================== WEB AUTHORIZATION COMMANDS ===================




# Start the bot
# ========================= FLASK WEB SERVER =========================

@app.route('/')
def home():
    """Главная страница"""
    return HTML_TEMPLATE


@app.route('/api/stats')
def api_stats():
    """API для получения статистики"""
    conn = get_pg_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()

        # Получаем статистику
        cursor.execute("SELECT COUNT(*) FROM releases WHERE status != 'pending'")
        releases_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM label")
        users_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM reviews WHERE status = 'approved'")
        reviews_count = cursor.fetchone()[0]

        stats = {
            "releases": releases_count,
            "users": users_count,
            "reviews": reviews_count
        }

        return jsonify({"success": True, "stats": stats})

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({"error": "Failed to get stats"}), 500
    finally:
        conn.close()


@app.route('/api/health')
def health_check():
    """Проверка работоспособности сервиса"""
    return jsonify({
        "status": "healthy",
        "bot": "running",
        "database": "connected" if get_pg_connection() else "disconnected"
    })


# ========================= STARTUP FUNCTIONS =========================

def run_bot():
    """Запуск Telegram бота"""
    logger.info("Starting Telegram bot...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            logger.error(f"Бот остановлен из-за ошибки: {e}")
            time.sleep(5)
            logger.info("Перезапуск бота...")


def run_web_server():
    """Запуск веб-сервера"""
    logger.info("Starting web server...")
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)



def main():
    """Главная функция запуска"""
    import threading

    logger.info("🚀 Starting Musical Label Bot...")

    # Initialize and check database
    logger.info("🔧 Initializing database...")
    try:
        init_database()
        logger.info("✅ Database initialization completed")

        # Additional integrity check
        logger.info("🔍 Performing database integrity check...")
        if check_database_integrity():
            logger.info("✅ Database integrity verified")
        else:
            logger.error("❌ Database integrity check failed")
            return

        # Migrate orders data if needed
        logger.info("🔄 Checking orders data migration...")
        migrate_orders_data()

        # Структура таблицы промокодов проверяется при инициализации БД
        logger.info("✅ Promo codes table structure checked")

    except Exception as e:
        logger.error(f"❌ Database setup failed: {e}")
        return

    # Запускаем веб-сервер в отдельном потоке
    logger.info("🌐 Starting web server...")
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("✅ Web server started in background")

    # Запускаем бота в основном потоке
    logger.info("🤖 Starting Telegram bot...")
    run_bot()


# Report request handlers migrated to handlers/admin_report_flow.py.


# Profile callback handlers

# Удален дублирующий обработчик back_to_profile - оставлен только один на строке 12298


def add_platform_links_column():
    """Add platform_links column to releases table if it doesn't exist"""
    logger.info("Adding platform_links column to releases table...")
    conn = get_pg_connection()
    if not conn:
        logger.error("Cannot add platform_links column - no connection")
        return False

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
        if conn:
            cursor.close()
            return_pg_connection(conn)


def ensure_label_columns():
    """Ensure all required columns exist in label table"""
    conn = get_pg_connection()
    if not conn:
        logger.error("Failed to connect to database for column check")
        return False

    try:
        cursor = conn.cursor()

        # Required columns with their types
        required_columns = {
            'email': 'TEXT',
            'fio': 'TEXT',
            'phone': 'TEXT',
            'steezy': 'INTEGER DEFAULT 0',
            'bibi': 'INTEGER DEFAULT 0',
            'shvepz': 'INTEGER DEFAULT 0',
            'referral_code': 'TEXT',
            'referral_count': 'INTEGER DEFAULT 0',
            'referral_earnings': 'NUMERIC(10, 2) DEFAULT 0'
        }

        for column, column_type in required_columns.items():
            try:
                cursor.execute(f"ALTER TABLE label ADD COLUMN IF NOT EXISTS {column} {column_type}")
                logger.info(f"✅ Ensured column {column} exists in label table")
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
    """Create referrals table if it doesn't exist"""
    conn = get_pg_connection()
    if not conn:
        logger.error("Cannot create referrals table - no connection")
        return False

    try:
        cursor = conn.cursor()

        # Create referrals table
        logger.info("Creating referrals table...")
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

        # Create indexes for referrals table
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
        if conn:
            return_pg_connection(conn)


def generate_referral_code(user_id):
    """Generate unique referral code for user"""
    import string
    import random

    # Generate random code
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    conn = get_pg_connection()
    if not conn:
        logger.error("Cannot generate referral code - no connection")
        return None

    try:
        cursor = conn.cursor()

        # Check if code already exists
        cursor.execute('SELECT telegram_id FROM label WHERE referral_code = %s', (code,))
        if cursor.fetchone():
            # If exists, generate new one
            return generate_referral_code(user_id)

        # Update user's referral code
        cursor.execute('''
            UPDATE label
            SET referral_code = %s
            WHERE telegram_id = %s
        ''', (code, user_id))

        conn.commit()
        logger.info(f"Generated referral code {code} for user {user_id}")
        return code

    except Exception as e:
        logger.error(f"Error generating referral code: {e}")
        return None
    finally:
        if conn:
            return_pg_connection(conn)


def process_referral_registration(user_id, referral_code):
    """Process referral registration and give bonuses"""
    conn = get_pg_connection()
    if not conn:
        logger.error("Cannot process referral - no connection")
        return False

    try:
        cursor = conn.cursor()

        # Ищем пользователя с таким реферальным кодом
        cursor.execute('SELECT telegram_id FROM label WHERE referral_code = %s', (referral_code,))
        referrer_result = cursor.fetchone()

        if referrer_result and referrer_result[0] != user_id:
            referrer_id = referrer_result[0]

            # Добавляем запись в таблицу referrals
            cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id, referral_code, status, bonus_amount)
                VALUES (%s, %s, %s, 'active', 100)
            ''', (referrer_id, user_id, referral_code))

            # Обновляем счетчики рефералов
            cursor.execute('''
                UPDATE label
                SET referral_count = COALESCE(referral_count, 0) + 1,
                    referral_earnings = COALESCE(referral_earnings, 0) + 100
                WHERE telegram_id = %s
            ''', (referrer_id,))

            # Даем бонус новому пользователю
            cursor.execute('''
                UPDATE label
                SET balance = COALESCE(balance, 0) + 100
                WHERE telegram_id = %s
            ''', (user_id,))

            conn.commit()
            logger.info(f"Referral bonus processed: {referrer_id} -> {user_id}")
            return True
        else:
            logger.warning(f"Invalid referral code: {referral_code} for user {user_id}")
            return False

    except Exception as e:
        logger.error(f"Error processing referral: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            return_pg_connection(conn)


# =================== WEB AUTHORIZATION HANDLERS ===================
# Старый код удален - используем новые команды /код и /webauth выше


# =================== DRAFT SAVE HANDLER ===================
def check_bot_instance():
    """Проверка на единственный экземпляр бота"""
    try:
        # Пробуем получить информацию о боте
        bot_info = bot.get_me()
        logger.info(f"✅ Bot instance check passed: @{bot_info.username}")
        return True
    except telebot.apihelper.ApiTelegramException as e:
        if "409" in str(e) or "Conflict" in str(e):
            logger.error("🚨 CRITICAL: Another bot instance is already running!")
            logger.error("🛑 Please stop all other bot instances before starting this one")
            return False
        else:
            logger.error(f"❌ Bot instance check failed: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Unexpected error during bot check: {e}")
        return False


def start_bot_with_retry():
    return bot_runner.start_bot_with_retry(bot, get_connection=get_pg_connection, return_connection=return_pg_connection)



if __name__ == "__main__":
    # Initialize database
    logger.info("🔧 Initializing database...")
    try:
        init_database()
        logger.info("✅ Database initialization completed")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        exit(1)

    # Ensure all required columns exist
    logger.info("🔧 Ensuring database columns...")
    try:
        ensure_label_columns()
        logger.info("✅ Database columns ensured")
    except Exception as e:
        logger.error(f"❌ Failed to ensure database columns: {e}")

    # Add platform_links column
    logger.info("🔧 Adding platform links column...")
    try:
        add_platform_links_column()
        logger.info("✅ Platform links column added")
    except Exception as e:
        logger.error(f"❌ Failed to add platform links column: {e}")

    # Create referrals table
    logger.info("🔧 Creating referrals table...")
    try:
        create_referrals_table()
        logger.info("✅ Referrals table created")
    except Exception as e:
        logger.error(f"❌ Failed to create referrals table: {e}")

    # Test bot token and check for conflicts
    logger.info("🔧 Testing bot token and checking for conflicts...")
    try:
        bot_info = bot.get_me()
        logger.info(f"✅ Bot connected: @{bot_info.username}")

        # Дополнительная проверка на конфликт экземпляров
        if not check_bot_instance():
            logger.error("❌ Bot instance conflict detected. Exiting...")
            exit(1)

    except Exception as e:
        logger.error(f"❌ Bot token test failed: {e}")
        exit(1)

    # Start bot with retry mechanism
    logger.info("🚀 Starting bot with enhanced error handling...")
    # Test channel access before starting bot
    logger.info("🔧 Testing channel access...")
    if test_channel_access():
        logger.info("✅ Channel access test passed, starting bot...")
        start_bot_with_retry()
    else:
        logger.error("❌ Channel access test failed!")
        logger.error("Please add the bot to the channel as administrator:")
        logger.error(f"1. Go to {CHANNEL_USERNAME}")
        logger.error("2. Channel settings → Administrators → Add administrator")
        logger.error("3. Find @twaslabel_bot and add it")
        logger.error("4. Give the bot admin rights")
        exit(1)


def create_edit_release_keyboard(release_id):
    """Create keyboard for editing release"""
    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "🎵 Название релиза",
            callback_data=f"edit_release_name_{release_id}"
        ),
        types.InlineKeyboardButton(
            "🎤 Имя артиста",
            callback_data=f"edit_artist_name_{release_id}"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "🎹 Продюсер",
            callback_data=f"edit_producer_{release_id}"
        ),
        types.InlineKeyboardButton(
            "🎼 Жанр",
            callback_data=f"edit_genre_{release_id}"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "📅 Дата релиза",
            callback_data=f"edit_release_date_{release_id}"
        ),
        types.InlineKeyboardButton(
            "👤 Исполнитель",
            callback_data=f"edit_performer_{release_id}"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "✍️ Автор музыки",
            callback_data=f"edit_music_author_{release_id}"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "◀️ Назад к релизу",
            callback_data=f"show_my_release_{release_id}"
        )
    )

    return markup

def handle_edit_release_name(call):
    """Handle edit release name request"""
    release_id = call.data.split("_")[3]

    bot.edit_message_text(
        "✏️ Введите новое название релиза:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_edit_release_name, release_id)

def process_edit_release_name(message, release_id):
    """Process new release name"""
    new_name = message.text.strip()

    if not new_name:
        bot.reply_to(message, "❌ Название релиза не может быть пустым")
        return

    conn = get_pg_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных")
        return

    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE releases SET release_name = %s WHERE id = %s AND user_id = %s",
            (new_name, release_id, message.from_user.id)
        )

        if cursor.rowcount == 0:
            bot.reply_to(message, "❌ Релиз не найден или у вас нет прав для его редактирования")
            return

        conn.commit()
        bot.reply_to(message, f"✅ Название релиза изменено на: {new_name}")

        # Show updated release details
        show_my_release_details_after_edit(message, release_id)

    except Exception as e:
        logger.error(f"Error updating release name: {e}")
        bot.reply_to(message, f"❌ Ошибка при обновлении: {str(e)}")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)

def show_my_release_details_after_edit(message, release_id):
    """Show release details after edit"""
    # Create a fake call object for the existing function
    class FakeCall:
        def __init__(self, message):
            self.from_user = message.from_user
            self.message = message
            self.data = f"show_my_release_{release_id}"

    fake_call = FakeCall(message)
    show_my_release_details(fake_call, release_id, admin_mode=False)

# ==================== УЛУЧШЕННАЯ ДИСТРИБУЦИЯ С НАВИГАЦИЕЙ ====================


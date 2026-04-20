#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import psycopg2
from psycopg2 import Error
from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"], supports_credentials=True, allow_headers=["Content-Type", "Authorization"])

# Конфигурация базы данных (те же настройки, что в боте)
DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres", 
    "password": "60606611125",
    "host": "localhost",
    "port": "5432"
}

def get_pg_connection():
    """Получить соединение с PostgreSQL"""
    try:
        conn = psycopg2.connect(
            dbname=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            client_encoding='utf8'
        )
        return conn
    except Error as e:
        logger.error(f"Ошибка подключения к PostgreSQL: {e}")
        return None

@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    """Получить отзывы с возможностью фильтрации"""
    try:
        # Параметры запроса
        service_type = request.args.get('service_type', None)
        limit = request.args.get('limit', 10, type=int)
        
        conn = get_pg_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Базовый запрос
        query = '''
            SELECT l.name, r.service_type, r.rating, r.text, r.created_date
            FROM reviews r
            JOIN label l ON r.user_id = l.telegram_id
            WHERE r.status = %s
        '''
        params = ["approved"]
        
        # Добавляем фильтр по типу услуги, если указан
        if service_type:
            query += ' AND r.service_type = %s'
            params.append(service_type)
            
        query += ' ORDER BY r.created_date DESC LIMIT %s'
        params.append(limit)
        
        cursor.execute(query, params)
        reviews = cursor.fetchall()
        
        # Преобразуем результат в JSON-формат
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
        logger.error(f"Ошибка при получении отзывов: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/reviews/random', methods=['GET'])
def get_random_review():
    """Получить случайный отзыв"""
    try:
        conn = get_pg_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
            
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
                'message': 'Пока нет отзывов'
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
        logger.error(f"Ошибка при получении случайного отзыва: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/reviews/stats', methods=['GET'])
def get_reviews_stats():
    """Получить статистику отзывов"""
    try:
        conn = get_pg_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Общее количество отзывов
        cursor.execute("SELECT COUNT(*) FROM reviews WHERE status = 'approved'")
        total_reviews = cursor.fetchone()[0]
        
        # Средний рейтинг
        cursor.execute("SELECT AVG(rating) FROM reviews WHERE status = 'approved'")
        avg_rating = cursor.fetchone()[0]
        
        # Количество по типам услуг
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
        logger.error(f"Ошибка при получении статистики: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/auth/check', methods=['GET'])
def check_auth_status():
    """Проверить статус авторизации по токену"""
    try:
        token = request.args.get('token')
        if not token:
            return jsonify({'success': False, 'error': 'Токен не указан'}), 400
            
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Проверяем код авторизации по токену
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
                # Код уже использован - авторизация успешна
                return jsonify({
                    'success': True,
                    'user': {
                        'telegram_id': user_id,
                        'username': username,
                        'name': name,
                        'isAdmin': False  # Можно добавить проверку админа
                    }
                })
            else:
                # Код еще не использован - ожидание
                return jsonify({'success': False, 'waiting': True})
        else:
            # Код не найден или истек
            return jsonify({'success': False, 'error': 'Неверный или истекший токен'})
            
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса авторизации: {e}")
        return jsonify({'success': False, 'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/auth/verify', methods=['POST'])
def verify_auth_code():
    """Проверить код авторизации"""
    try:
        data = request.get_json()
        if not data or 'code' not in data:
            return jsonify({'success': False, 'error': 'Код не указан'}), 400
            
        code = data['code'].strip()
        if not code:
            return jsonify({'success': False, 'error': 'Код не может быть пустым'}), 400
            
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Проверяем код
        cursor.execute('''
            SELECT ac.user_id, ac.expires_at, ac.used,
                   l.id, l.login, l.name, l.tg, l.telegram_id, l.admin, l.artist, 
                   l.balance, l.email, l.fio, l.phone, l.created_date
            FROM auth_codes ac
            JOIN label l ON ac.user_id = l.telegram_id
            WHERE ac.code = %s
        ''', (code,))
        
        result = cursor.fetchone()
        
        logger.info(f"Auth code verification: code={code}, result={result}")
        
        if not result:
            logger.warning(f"No user found for code: {code}")
            return jsonify({'success': False, 'error': 'Неверный код'})
            
        user_id, expires_at, used = result[:3]
        user_data = result[3:]
        
        # Проверяем, не использован ли код
        if used:
            return jsonify({'success': False, 'error': 'Код уже использован'})
            
        # Проверяем, не истек ли код
        if datetime.now() > expires_at:
            return jsonify({'success': False, 'error': 'Код истек'})
            
        # Отмечаем код как использованный
        cursor.execute('''
            UPDATE auth_codes 
            SET used = TRUE, used_at = CURRENT_TIMESTAMP
            WHERE code = %s
        ''', (code,))
        
        conn.commit()
        
        # Формируем данные пользователя
        logger.info(f"User data from DB: {user_data}")
        
        user_info = {
            'id': user_data[0],
            'login': user_data[1],
            'name': user_data[2],
            'username': user_data[3],
            'telegram_id': user_data[4],
            'isAdmin': bool(user_data[5]),
            'isArtist': bool(user_data[6]),
            'balance': float(user_data[7]) if user_data[7] else 0.0,
            'email': user_data[8],
            'fio': user_data[9],
            'phone': user_data[10],
            'created_date': user_data[11].isoformat() if user_data[11] else None,
            'registered': True
        }
        
        logger.info(f"Formed user info: {user_info}")
        
        return jsonify({'success': True, 'user': user_info})
        
    except Exception as e:
        logger.error(f"Error verifying auth code: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

# =================== PAYMENT MODULES ===================

# Проверяем доступность модуля для платежей
try:
    from yookassa import Configuration, Payment
    YOOKASSA_AVAILABLE = True
    # Настройки YooKassa (тестовые ключи)
    Configuration.account_id = "449150"
    Configuration.secret_key = "test_jdV9IqyNiy0O4oqwiFPX6lKHvG46zT3BjcVuoMJjUJc"
except ImportError:
    YOOKASSA_AVAILABLE = False
    logger.warning("yookassa module not available. YooKassa payments will be disabled.")

# Crypto Bot Configuration
CRYPTO_BOT_TOKEN = "449150:AAhpOhS1Mwm8mUfiVuOazq6Y7YHc6wkACxj"

# =================== BALANCE FUNCTIONS ===================

def change_user_balance(user_id, delta):
    """Изменить баланс пользователя"""
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
    """Создать платеж YooKassa"""
    if not YOOKASSA_AVAILABLE:
        return jsonify({'success': False, 'error': 'YooKassa не доступна'}), 503
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не переданы'}), 400
            
        amount = data.get('amount')
        user_id = data.get('user_id')  # ID пользователя для пополнения баланса
        description = data.get('description', 'Пополнение баланса')
        service_type = data.get('service_type', 'topup')
        
        if not amount or amount < 50:
            return jsonify({'success': False, 'error': 'Минимальная сумма 50 ₽'}), 400
        
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
            
        # Создаем платеж в YooKassa
        payment = Payment.create({
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": "http://193.104.57.60"},
            "capture": True,
            "description": description,
            "metadata": {
                "service": service_type,
                "amount": str(amount)
            }
        })
        
        payment_url = payment.confirmation.confirmation_url
        payment_id = payment.id
        
        logger.info(f"Created YooKassa payment {payment_id}, amount: {amount}")
        
        # Сохраняем заказ в базе данных
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Проверяем существование таблицы orders
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'orders'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            # Создаем таблицу orders
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
            logger.info("Таблица orders создана")
        
        # Сохраняем заказ
        cursor.execute(
            '''INSERT INTO orders (user_id, service_type, amount, status, payment_id, payment_system, created_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (user_id, service_type, amount, 'pending', payment_id, 'yookassa', datetime.now())
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
        return jsonify({'success': False, 'error': 'Ошибка создания платежа'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/payments/crypto/create', methods=['POST'])
def create_crypto_payment():
    """Создать платеж Crypto Bot"""
    try:
        import requests
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не переданы'}), 400
            
        amount = data.get('amount')
        user_id = data.get('user_id')  # ID пользователя для пополнения баланса
        description = data.get('description', 'Пополнение баланса')
        service_type = data.get('service_type', 'topup')
        
        if not amount or amount < 50:
            return jsonify({'success': False, 'error': 'Минимальная сумма 50 ₽'}), 400
        
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
        
        # Создаем инвойс в Crypto Bot
        crypto_api_url = "https://pay.crypt.bot/api/createInvoice"
        
        payload = {
            "asset": "USDT",
            "amount": amount / 100,  # конвертируем рубли в USDT примерно
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
                
                # Сохраняем заказ в базе данных
                conn = get_pg_connection()
                if not conn:
                    return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
                    
                cursor = conn.cursor()
                
                # Проверяем существование таблицы orders
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'orders'
                    )
                """)
                table_exists = cursor.fetchone()[0]
                
                if not table_exists:
                    # Создаем таблицу orders
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
                    logger.info("Таблица orders создана")
                
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
                return jsonify({'success': False, 'error': 'Ошибка Crypto Bot API'}), 500
        else:
            return jsonify({'success': False, 'error': 'Ошибка связи с Crypto Bot'}), 500
            
    except Exception as e:
        logger.error(f"Error creating Crypto Bot payment: {e}")
        return jsonify({'success': False, 'error': 'Ошибка создания платежа'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/payments/<payment_system>/status/<payment_id>', methods=['GET'])
def check_payment_status(payment_system, payment_id):
    """Проверить статус платежа"""
    try:
        if payment_system == 'yookassa':
            if not YOOKASSA_AVAILABLE:
                return jsonify({'success': False, 'error': 'YooKassa не доступна'}), 503
                
            # Проверяем статус в YooKassa
            payment = Payment.find_one(payment_id)
            if not payment:
                return jsonify({'success': False, 'error': 'Платеж не найден'}), 404
                
            status = payment.status
            
            if status == 'succeeded':
                # Обновляем статус в базе данных и пополняем баланс
                conn = get_pg_connection()
                if conn:
                    cursor = conn.cursor()
                    
                    # Получаем информацию о заказе
                    cursor.execute(
                        'SELECT user_id, amount, status FROM orders WHERE payment_id = %s',
                        (payment_id,)
                    )
                    order_info = cursor.fetchone()
                    
                    if order_info:
                        user_id, amount, current_status = order_info
                        
                        # Проверяем, что заказ еще не обработан
                        if current_status != 'completed':
                            # Обновляем статус заказа
                            cursor.execute(
                                'UPDATE orders SET status = %s WHERE payment_id = %s',
                                ('completed', payment_id)
                            )
                            
                            # Пополняем баланс пользователя
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
            
            # Проверяем статус в Crypto Bot
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
                        # Обновляем статус в базе данных и пополняем баланс
                        conn = get_pg_connection()
                        if conn:
                            cursor = conn.cursor()
                            
                            # Получаем информацию о заказе
                            cursor.execute(
                                'SELECT user_id, amount, status FROM orders WHERE payment_id = %s',
                                (payment_id,)
                            )
                            order_info = cursor.fetchone()
                            
                            if order_info:
                                user_id, amount, current_status = order_info
                                
                                # Проверяем, что заказ еще не обработан
                                if current_status != 'completed':
                                    # Обновляем статус заказа
                                    cursor.execute(
                                        'UPDATE orders SET status = %s WHERE payment_id = %s',
                                        ('completed', payment_id)
                                    )
                                    
                                    # Пополняем баланс пользователя
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
                    return jsonify({'success': False, 'error': 'Платеж не найден'}), 404
            else:
                return jsonify({'success': False, 'error': 'Ошибка Crypto Bot API'}), 500
        else:
            return jsonify({'success': False, 'error': 'Неизвестная платежная система'}), 400
            
    except Exception as e:
        logger.error(f"Error checking payment status: {e}")
        return jsonify({'success': False, 'error': 'Ошибка проверки статуса'}), 500

# =================== DISTRIBUTION API ===================

def get_admin_ids():
    """Получить ID админов из базы данных"""
    try:
        conn = get_pg_connection()
        if not conn:
            return [123456789]  # Fallback ID
            
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM label WHERE admin = 1 OR owner = 1")
        admin_ids = [row[0] for row in cursor.fetchall()]
        
        return admin_ids if admin_ids else [123456789]  # Fallback ID
        
    except Exception as e:
        logger.error(f"Ошибка получения ID админов: {e}")
        return [123456789]  # Fallback ID
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

def send_admin_notification(message):
    """Отправить уведомление админу в Telegram"""
    try:
        import requests
        
        # Получаем ID админов из базы данных
        admin_ids = get_admin_ids()
        logger.info(f"Найдено админов: {len(admin_ids)}, ID: {admin_ids}")
        
        # Токен бота (должен быть тот же, что в основном боте)
        bot_token = "6285811276:AAHpOhS1Mwm8mUfiVuOazq6Y7YHc6wkACxj"
        
        for admin_id in admin_ids:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': admin_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            logger.info(f"Отправляем уведомление админу {admin_id}")
            response = requests.post(url, data=data, timeout=10)
            logger.info(f"Ответ от Telegram API: {response.status_code}, {response.text}")
            
            if response.status_code == 200:
                logger.info(f"Уведомление отправлено админу {admin_id}")
            else:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {response.text}")
                
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления админу: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

@app.route('/api/user/balance', methods=['GET'])
def get_user_balance():
    """Получить баланс пользователя"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
            
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance FROM label WHERE telegram_id = %s', (user_id,))
        result = cursor.fetchone()
        
        if result:
            balance = float(result[0]) if result[0] else 0.0
            return jsonify({'success': True, 'balance': balance})
        else:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
            
    except Exception as e:
        logger.error(f"Ошибка при получении баланса: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/user/balance', methods=['POST'])
def update_user_balance():
    """Изменить баланс пользователя"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не переданы'}), 400
            
        user_id = data.get('user_id')
        delta = data.get('delta')
        
        if not user_id or delta is None:
            return jsonify({'success': False, 'error': 'ID пользователя и изменение баланса обязательны'}), 400
            
        if change_user_balance(user_id, delta):
            return jsonify({'success': True, 'message': 'Баланс обновлен'})
        else:
            return jsonify({'success': False, 'error': 'Ошибка обновления баланса'}), 500
            
    except Exception as e:
        logger.error(f"Ошибка при изменении баланса: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/api/admin/users/<int:user_id>/levels', methods=['PUT'])
def update_user_levels(user_id):
    """Обновить уровни пользователя (только для админов)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не переданы'}), 400
            
        levels = data.get('levels', [])
        if not isinstance(levels, list):
            return jsonify({'success': False, 'error': 'Уровни должны быть массивом'}), 400
            
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Обновляем уровни пользователя
        cursor.execute('''
            UPDATE label 
            SET levels = %s 
            WHERE telegram_id = %s
        ''', (levels, user_id))
        
        if cursor.rowcount > 0:
            conn.commit()
            return jsonify({'success': True, 'message': 'Уровни обновлены'})
        else:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
            
    except Exception as e:
        logger.error(f"Ошибка при обновлении уровней: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/telegram_auth', methods=['GET'])
def telegram_auth():
    """Аутентификация по Telegram ID"""
    try:
        telegram_id = request.args.get('tgid')
        if not telegram_id:
            return jsonify({'success': False, 'error': 'Telegram ID не указан'}), 400
            
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Получаем данные пользователя
        cursor.execute('''
            SELECT id, login, name, tg, telegram_id, admin, artist, owner,
                   balance, email, fio, phone, created_date, levels
            FROM label 
            WHERE telegram_id = %s
        ''', (telegram_id,))
        
        result = cursor.fetchone()
        
        if not result:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
            
        user_data = {
            'id': result[0],
            'username': result[1],
            'artistName': result[2],
            'channel': result[3],
            'levels': result[13] if result[13] else ['artist'],
            'isAdmin': bool(result[5]),
            'isOwner': bool(result[7]),
            'isSteezy': 'steezy' in (result[13] if result[13] else []),
            'isBibi': 'bibi' in (result[13] if result[13] else []),
            'isShvepz': 'shvepz' in (result[13] if result[13] else []),
            'isCreator': 'creator' in (result[13] if result[13] else []),
            'balance': float(result[8]) if result[8] else 0.0,
            'email': result[9],
            'fio': result[10],
            'phone': result[11],
            'createdDate': result[12].isoformat() if result[12] else None,
            'photoUrl': f'https://i.pravatar.cc/150?u={telegram_id}'
        }
        
        return jsonify({
            'success': True,
            'user': user_data
        })
        
    except Exception as e:
        logger.error(f"Ошибка при аутентификации Telegram: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/user_releases', methods=['GET'])
def get_user_releases():
    """Получить релизы пользователя"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
            
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Проверяем существование таблицы releases
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
                'message': 'Таблица релизов не найдена'
            })
        
        # Получаем релизы пользователя напрямую по переданному user_id
        cursor.execute("""
            SELECT id, release_type, artist_name, release_name, genre,
                   release_date, status, created_at
            FROM releases 
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))
        
        releases = cursor.fetchall()
        
        releases_list = []
        for release in releases:
            release_id, release_type, artist_name, release_name, genre, release_date, status, created_at = release
            releases_list.append({
                'id': release_id,
                'release_type': release_type,
                'artist_name': artist_name,
                'release_name': release_name,
                'genre': genre,
                'release_date': release_date.isoformat() if release_date else None,
                'status': status,
                'created_at': created_at.isoformat() if created_at else None
            })
        
        return jsonify({
            'success': True,
            'releases': releases_list,
            'count': len(releases_list)
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении релизов пользователя: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/distribution/create', methods=['POST'])
def create_distribution():
    """Создать релиз для дистрибуции"""
    try:
        # Получаем данные из формы
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400

        # Обязательные поля
        required_fields = {
            'releaseType': 'Тип релиза',
            'releaseName': 'Название релиза', 
            'artistName': 'Имя артиста',
            'releaseDate': 'Дата релиза',
            'genre': 'Жанр',
            'performerName': 'Исполнитель',
            'musicAuthor': 'Автор музыки'
        }

        release_data = {}
        for field, name in required_fields.items():
            value = request.form.get(field)
            if not value:
                return jsonify({'success': False, 'error': f'Поле "{name}" обязательно'}), 400
            release_data[field] = value

        # Дополнительные поля
        release_data['trackCount'] = int(request.form.get('trackCount', 1))
        release_data['featuringArtists'] = request.form.get('featuringArtists', '')
        release_data['explicitContent'] = request.form.get('explicitContent') == 'true'
        release_data['yandexSoon'] = request.form.get('yandexSoon') == 'true'
        release_data['createLinks'] = request.form.get('createLinks') == 'true'
        release_data['tiktokCommercial'] = request.form.get('tiktokCommercial') == 'true'
        release_data['tiktokFullVersion'] = request.form.get('tiktokFullVersion') == 'true'
        
        preview_start = request.form.get('previewStart')
        release_data['previewStart'] = int(preview_start) if preview_start else None

        # Проверяем файлы
        required_files = ['coverFile', 'audioFile', 'contractFile']
        file_data = {}
        
        for file_key in required_files:
            if file_key not in request.files:
                file_type = {'coverFile': 'обложку', 'audioFile': 'аудио файл', 'contractFile': 'договор'}[file_key]
                return jsonify({'success': False, 'error': f'Загрузите {file_type}'}), 400
            
            file = request.files[file_key]
            if file.filename == '':
                file_type = {'coverFile': 'обложку', 'audioFile': 'аудио файл', 'contractFile': 'договор'}[file_key]
                return jsonify({'success': False, 'error': f'Загрузите {file_type}'}), 400
                
            # Здесь в реальной системе файлы бы сохранялись на диск или в облако
            # Для демо сохраняем только имена файлов
            file_data[file_key] = file.filename

        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500

        cursor = conn.cursor()

        # Проверяем существование таблицы releases
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'releases'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            # Создаем таблицу releases (аналогично боту)
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
                    status TEXT DEFAULT 'принят',
                    is_album BOOLEAN DEFAULT FALSE,
                    upc_code TEXT,
                    platform_links JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("Таблица releases создана")

        # Проверяем статус артиста
        cursor.execute('SELECT artist FROM label WHERE telegram_id = %s', (user_id,))
        user_result = cursor.fetchone()
        is_artist = user_result and user_result[0] == 1

        # Сохраняем релиз
        cursor.execute("""
            INSERT INTO releases (
                user_id, release_type, artist_name, release_name, genre,
                cover_file_id, audio_file_id, release_date, performer_name,
                music_author, contract_file_id, explicit_content,
                preview_start, yandex_soon, create_links,
                tiktok_commercial, tiktok_full_version, status, is_album
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id,
            release_data['releaseType'],
            release_data['artistName'],
            release_data['releaseName'],
            release_data['genre'],
            file_data['coverFile'],  # В реальности тут был бы file_id
            file_data['audioFile'],  # В реальности тут был бы file_id
            release_data['releaseDate'],
            release_data['performerName'],
            release_data['musicAuthor'],
            file_data['contractFile'],  # В реальности тут был бы file_id
            release_data['explicitContent'],
            release_data['previewStart'],
            release_data['yandexSoon'],
            release_data['createLinks'],
            release_data['tiktokCommercial'],
            release_data['tiktokFullVersion'],
            'принят',
            release_data['releaseType'] in ['ALBUM', 'EP', 'Maxi Single']
        ))

        release_id = cursor.fetchone()[0]
        conn.commit()

        logger.info(f"Создан релиз ID {release_id} для пользователя {user_id}")

        # Отправляем уведомление админу
        try:
            # Получаем информацию о пользователе для уведомления
            cursor.execute('SELECT name, tg FROM label WHERE telegram_id = %s', (user_id,))
            user_info = cursor.fetchone()
            user_name = user_info[0] if user_info and user_info[0] else f"Пользователь {user_id}"
            user_username = user_info[1] if user_info and user_info[1] else "не указан"
            
            notification_message = f"""
🎵 <b>Новый релиз для дистрибуции!</b>

👤 <b>Исполнитель:</b> {user_name} (@{user_username})
🎼 <b>Название:</b> {release_data['releaseName']}
🎭 <b>Артист:</b> {release_data['artistName']}
📀 <b>Тип:</b> {release_data['releaseType']}
🎵 <b>Жанр:</b> {release_data['genre']}
📅 <b>Дата релиза:</b> {release_data['releaseDate']}

🆔 <b>ID релиза:</b> {release_id}
💰 <b>Стоимость:</b> {'Бесплатно' if is_artist else 'Платно'}

📋 <b>Дополнительные опции:</b>
{'✅ Яндекс.Музыка "скоро"' if release_data.get('yandexSoon') else ''}
{'✅ Создать ссылки' if release_data.get('createLinks') else ''}
{'✅ TikTok функции' if release_data.get('tiktokCommercial') or release_data.get('tiktokFullVersion') else ''}
{'✅ Явный контент' if release_data.get('explicitContent') else ''}

📁 <b>Файлы:</b>
• Обложка: {file_data.get('coverFile', 'не загружена')}
• Аудио: {file_data.get('audioFile', 'не загружен')}
• Договор: {file_data.get('contractFile', 'не загружен')}
            """
            
            send_admin_notification(notification_message)
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу: {e}")

        # Отправляем уведомление пользователю
        try:
            user_notification = f"""
🎵 <b>Ваш релиз принят!</b>

🎼 <b>Название:</b> {release_data['releaseName']}
🎭 <b>Артист:</b> {release_data['artistName']}
📀 <b>Тип:</b> {release_data['releaseType']}

🆔 <b>ID релиза:</b> {release_id}
📋 <b>Статус:</b> Принят на модерацию

💰 <b>Стоимость:</b> {'Бесплатно' if is_artist else 'Платно'}

⏳ <b>Ожидайте дальнейших инструкций в боте!</b>
            """
            
            # Отправляем уведомление пользователю
            import requests
            bot_token = "6285811276:AAHpOhS1Mwm8mUfiVuOazq6Y7YHc6wkACxj"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': user_id,
                'text': user_notification,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, data=data)
            if response.status_code == 200:
                logger.info(f"Уведомление отправлено пользователю {user_id}")
            else:
                logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {response.text}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю: {e}")

        return jsonify({
            'success': True,
            'message': 'Релиз успешно создан',
            'release_id': release_id,
            'is_free': is_artist
        })

    except Exception as e:
        logger.error(f"Error creating distribution: {e}")
        return jsonify({'success': False, 'error': 'Ошибка создания релиза'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/', methods=['GET'])
def index():
    """Главная страница API"""
    return jsonify({
        'message': 'TWAS Label API',
        'endpoints': {
            'GET /api/reviews': 'Получить отзывы (параметры: service_type, limit)',
            'GET /api/reviews/random': 'Получить случайный отзыв',
            'GET /api/reviews/stats': 'Получить статистику отзывов',
            'GET /api/auth/check': 'Проверить статус авторизации по токену',
            'POST /api/auth/verify': 'Проверить код авторизации (параметр: code)',
            'GET /api/user/balance': 'Получить баланс пользователя (параметр: user_id)',
            'POST /api/user/balance': 'Изменить баланс пользователя',
            'PUT /api/admin/users/{user_id}/levels': 'Обновить уровни пользователя',
            'GET /telegram_auth': 'Аутентификация по Telegram ID (параметр: tgid)',
            'GET /api/user_releases': 'Получить релизы пользователя (параметр: user_id)',
            'POST /api/payments/yookassa/create': 'Создать платеж YooKassa',
            'POST /api/payments/crypto/create': 'Создать платеж Crypto Bot',
            'GET /api/payments/{system}/status/{id}': 'Проверить статус платежа',
            'POST /api/distribution/create': 'Создать релиз для дистрибуции',
            'POST /api/releases/create': 'Создать релиз без файлов',
            'POST /api/albums/create': 'Создать альбом с треками',
            'GET /api/contracts/my': 'Получить контракты пользователя (параметр: user_id)',
            'GET /api/reports/my': 'Получить отчеты пользователя (параметр: user_id)',
            'GET /api/promo/history': 'Получить историю промокодов (параметр: user_id)'
        }
    })

@app.route('/api/orders', methods=['POST'])
def create_order():
    """Создать заказ дистрибуции"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не получены'}), 400
        
        # Получаем данные из запроса
        user_id = data.get('user_id')
        release_type = data.get('releaseType')
        release_name = data.get('releaseName')
        artist_name = data.get('artistName')
        producer = data.get('producer')
        genre = data.get('genre')
        track_count = data.get('trackCount')
        release_date = data.get('releaseDate')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
        
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
        
        cursor = conn.cursor()
        
        # Создаем заказ в таблице orders
        cursor.execute("""
            INSERT INTO orders (user_id, service_type, amount, status, created_date)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, f"Дистрибуция {release_type}", 100.00, 'pending', datetime.now()))
        
        order_id = cursor.fetchone()[0]
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'message': 'Заказ создан успешно'
        })
        
    except Exception as e:
        logger.error(f"Ошибка при создании заказа: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/releases/create', methods=['POST'])
def create_release():
    """Создать релиз без файлов"""
    conn = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не получены'}), 400
        
        user_id = data.get('user_id')
        release_type = data.get('releaseType', 'Single')
        release_name = data.get('releaseName', '')
        artist_name = data.get('artistName', '')
        producer = data.get('producer', '')
        genre = data.get('genre', '')
        release_date = data.get('releaseDate', '')
        # Дополнительные медиаполя, которые сайт может присылать
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
        
        # Логируем полученные данные для отладки
        logger.info(f"Получены данные: user_id={user_id}, release_type={release_type}, release_name={release_name}, artist_name={artist_name}, producer={producer}, genre={genre}, release_date={release_date}")
        
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
        
        # Проверяем обязательные поля
        if not release_name:
            return jsonify({'success': False, 'error': 'Название релиза не указано'}), 400
        if not artist_name:
            return jsonify({'success': False, 'error': 'Имя исполнителя не указано'}), 400
        if not release_date:
            return jsonify({'success': False, 'error': 'Дата релиза не указана'}), 400
        
        # Проверяем и исправляем формат даты
        try:
            from datetime import datetime
            # Если дата имеет формат "0003-03-31", заменяем на текущую дату
            if release_date.startswith('0003-'):
                release_date = datetime.now().strftime('%Y-%m-%d')
                logger.info(f"Исправлена дата релиза на: {release_date}")
            
            # Проверяем, что дата корректна
            datetime.strptime(release_date, '%Y-%m-%d')
        except ValueError as e:
            logger.error(f"Ошибка формата даты: {e}")
            return jsonify({'success': False, 'error': 'Неверный формат даты релиза'}), 400
        
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
        
        cursor = conn.cursor()
        
        # Проверяем существование таблицы releases
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'releases'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            # Создаем таблицу releases
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("Таблица releases создана с дополнительными полями для треков")
        
        logger.info(f"Создание релиза: user_id={user_id}, release_type={release_type}, release_name={release_name}, artist_name={artist_name}")
        
        cursor.execute("""
            INSERT INTO releases (user_id, release_type, artist_name, release_name,
                                producer, genre, cover_file_id, audio_file_id, release_date,
                                performer_name, music_author, contract_file_id, videoshot_url,
                                explicit_content, lyrics_file_id, preview_start, yandex_soon,
                                create_links, tiktok_commercial, tiktok_full_version, status,
                                is_album, is_track, upc_code, platform_links, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            False,
            None,
            datetime.now()
        ))
        
        release_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({
            'success': True,
            'release_id': release_id,
            'message': 'Релиз создан успешно'
        })
        
    except Exception as e:
        logger.error(f"Ошибка при создании релиза: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()


@app.route('/api/albums/create', methods=['POST'])
def create_album():
    """Создать альбом с треками"""
    conn = None
    try:
        from datetime import datetime
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не получены'}), 400
        
        user_id = data.get('user_id')
        release_type = data.get('releaseType')  # ALBUM или EP
        release_name = data.get('releaseName')
        artist_name = data.get('artistName')
        producer = data.get('producer')
        genre = data.get('genre')
        release_date = data.get('releaseDate')
        tracks = data.get('tracks', [])
        # Необязательные media-поля для альбома
        album_cover_id = data.get('coverFileId') or data.get('cover_file_id')
        album_audio_id = data.get('audioFileId') or data.get('audio_file_id')
        album_contract_id = data.get('contractFileId') or data.get('contract_file_id')
        performer_name = data.get('performerName') or artist_name
        music_author = data.get('musicAuthor') or artist_name
        
        logger.info(f"Создание альбома: user_id={user_id}, release_type={release_type}, release_name={release_name}, artist_name={artist_name}, tracks_count={len(tracks)}")
        
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
        
        if not release_name:
            return jsonify({'success': False, 'error': 'Название альбома не указано'}), 400
        
        if not artist_name:
            return jsonify({'success': False, 'error': 'Имя исполнителя не указано'}), 400
        
        if not release_date:
            return jsonify({'success': False, 'error': 'Дата релиза не указана'}), 400
        
        if not tracks:
            return jsonify({'success': False, 'error': 'Треки не указаны'}), 400
        
        # Проверяем и исправляем формат даты
        try:
            # Если дата имеет формат "0002-02-22", заменяем на текущую дату
            if release_date.startswith('0002-'):
                release_date = datetime.now().strftime('%Y-%m-%d')
                logger.info(f"Исправлена дата релиза на: {release_date}")
            
            # Проверяем, что дата корректна
            datetime.strptime(release_date, '%Y-%m-%d')
        except ValueError as e:
            logger.error(f"Ошибка формата даты: {e}")
            return jsonify({'success': False, 'error': 'Неверный формат даты релиза'}), 400
        
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
        
        cursor = conn.cursor()
        
        # Проверяем существование таблицы releases
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'releases'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            # Создаем таблицу releases
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("Таблица releases создана с дополнительными полями для треков")
        
        # Создаем запись альбома
        cursor.execute("""
            INSERT INTO releases (user_id, release_type, artist_name, release_name,
                                producer, genre, cover_file_id, audio_file_id, release_date,
                                performer_name, music_author, contract_file_id, videoshot_url,
                                explicit_content, lyrics_file_id, preview_start, yandex_soon,
                                create_links, tiktok_commercial, tiktok_full_version, status,
                                is_album, upc_code, platform_links, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id, release_type, artist_name, release_name, producer,
            genre, album_cover_id, album_audio_id, release_date,
            performer_name, music_author, album_contract_id, None,
            False, None, None, False,
            False, False, False, 'pending', True, None, None, datetime.now()
        ))
        
        album_id = cursor.fetchone()[0]
        
        # Создаем записи треков
        for i, track in enumerate(tracks, 1):
            t_audio = track.get('audioFileId') or track.get('audio_file_id')
            t_contract = track.get('contractFileId') or track.get('contract_file_id')
            t_cover = track.get('coverFileId') or track.get('cover_file_id')
            cursor.execute("""
                INSERT INTO releases (user_id, release_type, artist_name, release_name, 
                                    producer, genre, cover_file_id, audio_file_id, release_date, 
                                    performer_name, music_author, contract_file_id, videoshot_url, 
                                    explicit_content, lyrics_file_id, preview_start, yandex_soon, 
                                    create_links, tiktok_commercial, tiktok_full_version, status, 
                                    is_track, album_id, track_number, upc_code, platform_links, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                user_id, 'TRACK', artist_name, track.get('track_name'),
                track.get('producer'), track.get('genre'), t_cover, t_audio, release_date,
                performer_name, music_author, t_contract, None, False, None, None,
                False, False, False, False, 'pending', True, album_id, i, None, None, datetime.now()
            ))
        
        conn.commit()
        
        # Отправляем уведомление админам
        try:
            logger.info(f"Создание уведомления для альбома: {release_name}")
            notification_message = f"""
🎵 <b>Новый альбом создан!</b>

👤 <b>Пользователь:</b> {user_id}
🎼 <b>Название альбома:</b> {release_name}
🎤 <b>Исполнитель:</b> {artist_name}
🎹 <b>Продюсер:</b> {producer}
🎭 <b>Жанр:</b> {genre}
📅 <b>Дата релиза:</b> {release_date}
🎵 <b>Тип:</b> {release_type}
🎶 <b>Количество треков:</b> {len(tracks)}

<b>Треки:</b>
"""
            for i, track in enumerate(tracks, 1):
                notification_message += f"{i}. {track.get('track_name', 'Без названия')} (prod. {track.get('producer', 'Неизвестно')})\n"
            
            logger.info(f"Отправляем уведомление: {notification_message}")
            send_admin_notification(notification_message)
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        return jsonify({
            'success': True,
            'album_id': album_id,
            'tracks_count': len(tracks),
            'message': 'Альбом создан успешно'
        })
        
    except Exception as e:
        logger.error(f"Ошибка при создании альбома: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/contracts/my', methods=['GET'])
def get_my_contracts():
    """Получить контракты пользователя"""
    conn = None
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
        
        # Пока возвращаем пустой список, так как таблица contracts может не существовать
        return jsonify({
            'success': True,
            'contracts': [],
            'count': 0,
            'message': 'Функция контрактов в разработке'
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении контрактов: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.route('/api/reports/my', methods=['GET'])
def get_my_reports():
    """Получить отчеты пользователя"""
    conn = None
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
        
        # Пока возвращаем пустой список, так как таблица report_requests может не существовать
        return jsonify({
            'success': True,
            'reports': [],
            'count': 0,
            'message': 'Функция отчетов в разработке'
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении отчетов: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.route('/api/promo/history', methods=['GET'])
def get_promo_history():
    """Получить историю промокодов пользователя"""
    conn = None
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
        
        # Пока возвращаем пустой список, так как таблица promo_codes может не существовать
        return jsonify({
            'success': True,
            'history': [],
            'count': 0,
            'message': 'Функция промокодов в разработке'
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении истории промокодов: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()


if __name__ == '__main__':
    import ssl
    import os
    
    # Проверяем наличие SSL сертификатов
    cert_file = "ssl_certs/cert.pem"
    key_file = "ssl_certs/key.pem"
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        # Создаем SSL контекст
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.load_cert_chain(cert_file, key_file)
        
        print("🔐 Запуск API сервера с HTTPS...")
        app.run(host='0.0.0.0', port=5000, debug=True, ssl_context=context)
    else:
        print("⚠️  SSL сертификаты не найдены. Запуск в HTTP режиме...")
        print("   Для HTTPS запустите: python generate_ssl.py")
        app.run(host='0.0.0.0', port=5000, debug=True)

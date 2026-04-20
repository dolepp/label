# Добавляем простые эндпоинты для пополнения баланса
import uuid

@app.route('/api/payments/simple/create', methods=['POST'])
def create_simple_payment():
    """Создать простой платеж (для тестирования)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не переданы'}), 400
            
        amount = data.get('amount')
        user_id = data.get('user_id')
        description = data.get('description', 'Пополнение баланса')
        
        if not amount or amount < 1:
            return jsonify({'success': False, 'error': 'Минимальная сумма 1 ₽'}), 400
        
        if not user_id:
            return jsonify({'success': False, 'error': 'ID пользователя не указан'}), 400
            
        # Генерируем уникальный ID платежа
        payment_id = str(uuid.uuid4())
        
        # Создаем заказ в базе данных
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
                    payment_system VARCHAR(20) DEFAULT 'simple',
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("Таблица orders создана")
        
        # Сохраняем заказ
        cursor.execute(
            '''INSERT INTO orders (user_id, service_type, amount, status, payment_id, payment_system, created_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (user_id, 'topup', amount, 'pending', payment_id, 'simple', datetime.now())
        )
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'payment_id': payment_id,
            'amount': amount,
            'message': 'Платеж создан. Для завершения используйте /api/payments/simple/complete'
        })
        
    except Exception as e:
        logger.error(f"Error creating simple payment: {e}")
        return jsonify({'success': False, 'error': 'Ошибка создания платежа'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/payments/simple/complete', methods=['POST'])
def complete_simple_payment():
    """Завершить простой платеж (для тестирования)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Данные не переданы'}), 400
            
        payment_id = data.get('payment_id')
        
        if not payment_id:
            return jsonify({'success': False, 'error': 'ID платежа не указан'}), 400
            
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        # Получаем информацию о заказе
        cursor.execute(
            'SELECT user_id, amount, status FROM orders WHERE payment_id = %s',
            (payment_id,)
        )
        order_info = cursor.fetchone()
        
        if not order_info:
            return jsonify({'success': False, 'error': 'Платеж не найден'}), 404
            
        user_id, amount, current_status = order_info
        
        # Проверяем, что заказ еще не обработан
        if current_status == 'completed':
            return jsonify({'success': False, 'error': 'Платеж уже обработан'}), 400
            
        # Обновляем статус заказа
        cursor.execute(
            'UPDATE orders SET status = %s WHERE payment_id = %s',
            ('completed', payment_id)
        )
        
        # Пополняем баланс пользователя
        if change_user_balance(user_id, amount):
            conn.commit()
            logger.info(f"Simple payment {payment_id} completed: added {amount} to user {user_id}")
            
            return jsonify({
                'success': True,
                'message': 'Платеж успешно завершен',
                'amount': amount,
                'user_id': user_id
            })
        else:
            return jsonify({'success': False, 'error': 'Ошибка пополнения баланса'}), 500
            
    except Exception as e:
        logger.error(f"Error completing simple payment: {e}")
        return jsonify({'success': False, 'error': 'Ошибка завершения платежа'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()

@app.route('/api/payments/simple/status/<payment_id>', methods=['GET'])
def check_simple_payment_status(payment_id):
    """Проверить статус простого платежа"""
    try:
        conn = get_pg_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Ошибка подключения к базе данных'}), 500
            
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT status, amount, user_id FROM orders WHERE payment_id = %s',
            (payment_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            return jsonify({'success': False, 'error': 'Платеж не найден'}), 404
            
        status, amount, user_id = result
        
        return jsonify({
            'success': True,
            'status': status,
            'amount': float(amount),
            'user_id': user_id,
            'payment_id': payment_id
        })
        
    except Exception as e:
        logger.error(f"Error checking simple payment status: {e}")
        return jsonify({'success': False, 'error': 'Ошибка проверки статуса'}), 500
    finally:
        if 'conn' in locals() and conn:
            if 'cursor' in locals():
                cursor.close()
            conn.close()
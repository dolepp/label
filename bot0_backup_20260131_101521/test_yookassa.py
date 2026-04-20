#!/usr/bin/env python3
"""Тестовый скрипт для проверки YooKassa"""
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from yookassa import Configuration, Payment
    import logging
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)
    
    # Настройка YooKassa
    Configuration.account_id = "381764678"
    Configuration.secret_key = "live_8MVRYBieniDXJqm2K0KSNCOMFpUXZ0gjMebRfdl__B4"
    
    logger.info(f"YooKassa настроен: account_id={Configuration.account_id}")
    logger.info(f"Secret key начинается с: {Configuration.secret_key[:20]}...")
    
    # Пропускаем проверку API через requests, так как она может работать по-другому
    # Прямо создаем платеж
    
    # Создание тестового платежа
    try:
        logger.info("Создание тестового платежа...")
        payment_data = {
            "amount": {"value": "1.00", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": "https://t.me/twaslabel_bot"},
            "capture": True,
            "description": "Test payment - проверка YooKassa",
            "metadata": {"test": "true"}
        }
        
        logger.info(f"Данные платежа: amount={payment_data['amount']}, description={payment_data['description']}")
        
        payment = Payment.create(payment_data)
        payment_url = payment.confirmation.confirmation_url
        payment_id = payment.id
        
        logger.info(f"✅ Платеж создан успешно!")
        logger.info(f"   Payment ID: {payment_id}")
        logger.info(f"   Payment URL: {payment_url}")
        logger.info(f"   Amount: {payment.amount.value} {payment.amount.currency}")
        logger.info(f"   Status: {payment.status}")
        
        # Отменяем тестовый платеж
        try:
            Payment.cancel(payment_id)
            logger.info(f"✅ Тестовый платеж {payment_id} отменён")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отменить тестовый платеж (это нормально): {e}")
        
        print("\n" + "="*70)
        print("✅ ТЕСТ YOOKASSA УСПЕШЕН!")
        print("="*70)
        print(f"Payment ID: {payment_id}")
        print(f"Payment URL (откройте в браузере для проверки):")
        print(f"{payment_url}")
        print("="*70)
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания платежа: {type(e).__name__}: {e}")
        if hasattr(e, 'args') and e.args:
            import json
            try:
                error_data = e.args[0] if isinstance(e.args[0], dict) else json.loads(str(e.args[0]))
                if isinstance(error_data, dict):
                    logger.error(f"   Код ошибки: {error_data.get('code', 'N/A')}")
                    logger.error(f"   Описание: {error_data.get('description', 'N/A')}")
            except:
                pass
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
except ImportError as e:
    print(f"❌ Ошибка импорта модулей: {e}")
    print("Убедитесь, что модуль yookassa установлен: pip install yookassa")
    sys.exit(1)
except Exception as e:
    print(f"❌ Неожиданная ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


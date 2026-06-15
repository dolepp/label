import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


import label  # noqa

if hasattr(label, 'start_bot_with_retry'):
    label.start_bot_with_retry()
else:
    # Настраиваем таймауты перед запуском
    try:
        import telebot.apihelper
        telebot.apihelper.READ_TIMEOUT = 30
        telebot.apihelper.CONNECT_TIMEOUT = 10
    except Exception:
        pass
    
    label.bot.polling(
        none_stop=True, 
        interval=0,  # Без задержки — быстрее отклик
        timeout=20,
        long_polling_timeout=25,
        skip_pending=True
    )

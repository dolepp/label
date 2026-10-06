"""Handle website Telegram linking before ordinary /start onboarding."""
import logging
import re
from db.repositories.account_connections import link_telegram, linked_web_account
from core.config import WEB_APP_URL
from telebot import types

logger = logging.getLogger(__name__)


def register_account_connection_handlers(bot):
    @bot.message_handler(func=lambda message: bool(re.fullmatch(
        r'/start(?:@\w+)?\s+link_[A-Za-z0-9_-]{43}', (message.text or '').strip())))
    def connect_account(message):
        if message.chat.type != 'private':
            bot.reply_to(message, 'Привяжите Telegram в личном чате с ботом.')
            return
        token = message.text.strip().split()[1][5:]
        try:
            link_telegram(token, message.from_user.id, message.from_user.username)
            bot.reply_to(message, '✅ Telegram привязан к профилю TWAS Label. Здесь будут уведомления о релизах и заявках. Вернитесь в профиль сайта и нажмите «Проверить привязку».')
        except ValueError as exc:
            bot.reply_to(message, str(exc))
        except Exception:
            logger.exception('Could not link Telegram account')
            bot.reply_to(message, 'Не удалось привязать Telegram. Попробуйте позже.')

    @bot.message_handler(commands=["start"], func=lambda message: bool(re.fullmatch(r'/start(?:@\w+)?', (getattr(message, 'text', '') or '').strip())) and getattr(message.chat, 'type', None) == 'private' and bool(linked_web_account(message.from_user.id)))
    def linked_start(message):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('Открыть профиль', url=WEB_APP_URL))
        bot.reply_to(message, 'Ваш Telegram связан с профилем сайта. Здесь приходят уведомления. Для входа на сайт отправьте /код.', reply_markup=markup)

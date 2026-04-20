# Обработчики регистрируются на bot при импорте (декораторы @bot.message_handler и т.д.)
from handlers import common, start, profile, releases, distribution, finance, support, admin, reviews, services

__all__ = ["common", "start", "profile", "releases", "distribution", "finance", "support", "admin", "reviews", "services"]

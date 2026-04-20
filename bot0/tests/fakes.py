"""Small fakes used by handler registration tests."""
from __future__ import annotations

from types import SimpleNamespace


class FakeBot:
    def __init__(self):
        self.message_handlers = []
        self.callback_query_handlers = []
        self.next_step_handlers = []
        self.sent_messages = []
        self.edited_messages = []
        self.callback_answers = []
        self.user_data = {}

    def message_handler(self, **filters):
        def decorator(func):
            self.message_handlers.append({"function": func, "filters": filters})
            return func

        return decorator

    def callback_query_handler(self, **filters):
        def decorator(func):
            self.callback_query_handlers.append({"function": func, "filters": filters})
            return func

        return decorator

    def register_next_step_handler(self, message, callback, *args, **kwargs):
        self.next_step_handlers.append((message, callback, args, kwargs))

    def reply_to(self, message, text, reply_markup=None, **kwargs):
        sent = make_message(text=text, user_id=message.from_user.id, chat_id=message.chat.id)
        self.sent_messages.append({"chat_id": message.chat.id, "text": text, "reply_markup": reply_markup, "kwargs": kwargs})
        return sent

    def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        sent = make_message(text=text, user_id=chat_id, chat_id=chat_id)
        self.sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup, "kwargs": kwargs})
        return sent

    def send_document(self, chat_id, document, caption=None, reply_markup=None, **kwargs):
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "document": document,
                "caption": caption,
                "reply_markup": reply_markup,
                "kwargs": kwargs,
            }
        )
        return make_message(text=caption or "", user_id=chat_id, chat_id=chat_id)

    def edit_message_text(self, text, chat_id, message_id, reply_markup=None, **kwargs):
        self.edited_messages.append(
            {"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup, "kwargs": kwargs}
        )

    def get_chat_member(self, channel_username, user_id):
        return SimpleNamespace(status="administrator")

    def answer_callback_query(self, callback_id, text=None, **kwargs):
        self.callback_answers.append({"id": callback_id, "text": text, "kwargs": kwargs})

    def delete_message(self, chat_id, message_id):
        return None


def make_message(text: str, user_id: int = 1398275867, chat_id: int | None = None):
    chat_id = user_id if chat_id is None else chat_id
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=user_id, username="test_user", first_name="Test"),
        chat=SimpleNamespace(id=chat_id),
        message_id=1,
    )


def make_call(data: str, user_id: int = 1398275867, chat_id: int | None = None):
    chat_id = user_id if chat_id is None else chat_id
    return SimpleNamespace(
        id="callback-id",
        data=data,
        from_user=SimpleNamespace(id=user_id, username="test_user", first_name="Test"),
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=1),
    )


def count_matching_message_handlers(bot: FakeBot, text: str) -> int:
    message = make_message(text)
    count = 0
    for handler in bot.message_handlers:
        func_filter = handler.get("filters", {}).get("func")
        if func_filter and func_filter(message):
            count += 1
    return count


def count_matching_callback_handlers(bot: FakeBot, data: str) -> int:
    call = make_call(data)
    count = 0
    for handler in bot.callback_query_handlers:
        func_filter = handler.get("filters", {}).get("func")
        if func_filter and func_filter(call):
            count += 1
    return count


def count_command_handlers(bot: FakeBot, command: str) -> int:
    count = 0
    for handler in bot.message_handlers:
        commands = handler.get("filters", {}).get("commands") or []
        if command in commands:
            count += 1
    return count

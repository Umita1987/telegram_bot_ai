from aiogram import Dispatcher

from .approval_handlers import register_approval_handlers
from .callback_handlers import register_callback_query_handlers
from .payment_callback import register_payment_callback_handlers
from .slot_selection_handler import register_slot_selection_handler
from .start import register_start_handlers
from .user_handlers import register_user_handlers
from .admin_handlers import register_admin_handlers
from .payment_handlers import register_payment_handlers  # Тут уже есть обработчик successful_payment
from .stats_handlers import register_stats_handlers

import logging

logger = logging.getLogger("handlers")

def register_all_handlers(dp: Dispatcher):
    register_start_handlers(dp)
    register_user_handlers(dp)
    register_admin_handlers(dp)
    register_payment_handlers(dp)  # Тут есть обработчик successful_payment!
    register_callback_query_handlers(dp)
    register_approval_handlers(dp)
    register_payment_callback_handlers(dp)
    register_slot_selection_handler(dp)
    register_stats_handlers(dp)


    # Проверяем, зарегистрирован ли обработчик successful_payment
    if any(handler.callback.__name__ == "handle_successful_payment" for handler in dp.message.handlers):
        logger.info("✅ Обработчик successful_payment успешно зарегистрирован!")
    else:
        logger.error("❌ Ошибка: Обработчик successful_payment НЕ зарегистрирован!")
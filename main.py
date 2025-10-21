import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from config import TELEGRAM_TOKEN, SENTRY_DSN
from handlers import register_all_handlers
from services.cleanup import schedule_cleanup
from services.metrics import start_prometheus_server
from services.redis_client import init_redis, close_redis
from services.scheduler import scheduler
from services.telethon_client import start_client, stop_client  # 📌 Добавляем Telethon

# Загрузка .env
from dotenv import load_dotenv
load_dotenv()

# ✅ Инициализация Sentry
import sentry_sdk
sentry_sdk.init(
    dsn=SENTRY_DSN,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
)

# 🔧 Прометеус
start_prometheus_server()

# 📋 Логгер
from logs import get_logger

logger = get_logger("main.py")
logger.info("🚀 Prometheus сервер метрик запущен на порту 8000")
logger.info("🛡️ Sentry инициализирован")
# 🤖 Бот
bot = Bot(token=TELEGRAM_TOKEN)

async def main():
    """Главный запуск"""
    try:
        logger.info("Инициализация Redis...")
        redis = await init_redis()

        if redis is None:
            logger.error("❌ Не удалось подключиться к Redis. Завершение работы.")
            return

        storage = RedisStorage(redis)
        dp = Dispatcher(storage=storage)
        register_all_handlers(dp)

        logger.info("🚀 Запуск Telethon-клиента...")
        await start_client()

        asyncio.create_task(scheduler())
        asyncio.create_task(schedule_cleanup())

        logger.info("🚀 Бот успешно запущен!")
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"❌ Произошла ошибка: {e}")
        sentry_sdk.capture_exception(e)  # ⬅️ Отправка ошибки в Sentry

    finally:
        logger.info("🛑 Остановка Telethon-клиента...")
        await stop_client()

        await close_redis()
        logger.info("🔴 Программа завершена.")


if __name__ == "__main__":
    asyncio.run(main())

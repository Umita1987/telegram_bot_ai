import os
from redis.asyncio import Redis
from logs import get_logger
logger = get_logger("redis_client")


redis: Redis | None = None  # Глобальная переменная для подключения


async def init_redis() -> Redis:
    """
    Инициализирует подключение к Redis, используя настройки из переменных окружения.
    """
    global redis
    if redis is None:
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))

        redis = Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            encoding="utf-8",
            decode_responses=True
        )
        try:
            await redis.ping()
            logger.info(f"Успешное подключение к Redis! Объект Redis: {redis}")
        except Exception as e:
            redis = None
            logger.error(f"Ошибка подключения к Redis: {e}")
            raise
    return redis


async def close_redis():
    """
    Закрывает подключение к Redis.
    """
    global redis
    if redis:
        try:
            await redis.close()
            redis = None
            logger.info("Подключение к Redis закрыто.")
        except Exception as e:
            logger.error(f"Ошибка при закрытии соединения с Redis: {e}")
from telethon import TelegramClient
from config import API_ID, API_HASH, PHONE_NUMBER
from logs import get_logger

logger = get_logger("telethon_client")

client = TelegramClient("session_name", API_ID, API_HASH)

async def start_client():
    """Запускает клиента Telethon (авторизация)"""
    await client.start(PHONE_NUMBER)
    logger.info("✅ Telethon-клиент успешно запущен!")


async def stop_client():
    """Останавливает клиента Telethon"""
    try:
        await client.disconnect()
        logger.info("🚪 Telethon-клиент остановлен.")
    except Exception as e:
        logger.error(f"❌ Ошибка остановки Telethon клиента: {e}")

def get_client():
    """Получить экземпляр клиента"""
    return client
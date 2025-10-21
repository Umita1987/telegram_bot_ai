from config import TEST_CHANNEL_ID
from services.telethon_client import client

from logs import get_logger
logger = get_logger("stats_service")


def format_reactions(reactions) -> str:
    """
    Преобразует объект реакций в строку вида "❤ x2, 👍 x3".
    Если реакций нет, возвращает "Нет реакций".
    """
    try:
        # Если реакций нет или список пуст – возвращаем placeholder
        if not reactions or not hasattr(reactions, 'results') or not reactions.results:
            return "Нет реакций"

        formatted = []
        for rc in reactions.results:
            if hasattr(rc, 'reaction') and hasattr(rc, 'count'):
                emoticon = getattr(rc.reaction, "emoticon", "❓")
                count = rc.count
                formatted.append(f"{emoticon} x{count}")
            else:
                formatted.append("❓")

        return ", ".join(formatted)

    except Exception as e:
        logger.error(f"Ошибка при форматировании реакций: {e}")
        return "Нет реакций"


async def get_post_stats(post_ids):
    """
    Получает статистику сообщений по их ID из канала.

    :param post_ids: Список ID сообщений.
    :return: Список словарей со статистикой по постам с ключами:
             "id", "views" и "reactions".
    """
    try:
        # Запрашиваем сообщения по их ID из указанного канала
        messages = await client.get_messages(TEST_CHANNEL_ID, ids=post_ids)
        stats = []
        for message in messages:
            if message is None:
                continue
            stats.append({
                "id": message.id,
                "views": message.views if message.views is not None else "❓",
                "reactions": format_reactions(message.reactions) if message.reactions is not None else "❓"
            })
        return stats

    except Exception as e:
        logger.error(f"❌ Ошибка при получении статистики: {e}")
        return []

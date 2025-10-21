# services/cleanup.py
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import delete
from services.database import async_session
from models.models import Post
from logs import get_logger
from services.publisher import MOSCOW_TZ

logger = get_logger("cleanup")


async def cleanup_old_drafts():
    """
    Удаляет старые черновики (посты со статусами "draft" или "accepted"),
    созданные более 24 часов назад.
    """
    threshold =datetime.now(MOSCOW_TZ) - timedelta(hours=24)
    async with async_session() as session:
        result = await session.execute(
            delete(Post).where(
                Post.status.in_(["draft", "accepted"]),
                Post.created_at < threshold
            )
        )
        await session.commit()
        logger.info(f"Cleanup: удалено {result.rowcount} старых черновиков.")

async def schedule_cleanup():
    """
    Периодически запускает очистку старых черновиков (например, раз в час).
    """
    while True:
        await cleanup_old_drafts()
        # Ожидаем 1 час до следующего запуска
        await asyncio.sleep(1800)

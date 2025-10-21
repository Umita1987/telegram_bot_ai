import html  # Для экранирования HTML
from datetime import timezone, timedelta
from typing import Union
from aiogram import Router, types
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.future import select

from services.database import async_session
from models.models import Post

from logs import get_logger

logger = get_logger("stats_handlers")
router = Router()

def split_message_by_lines(text: str, max_length: int = 4000) -> list:
    """Разбивает текст на части по строкам так, чтобы каждая часть не превышала max_length символов."""
    lines = text.splitlines(keepends=True)
    messages = []
    current = ""
    for line in lines:
        if len(current) + len(line) > max_length:
            messages.append(current)
            current = line
        else:
            current += line
    if current:
        messages.append(current)
    return messages

@router.callback_query(lambda c: c.data == "view_post_stats")
@router.message(lambda m: m.text == "📊 Статистика постов")
async def view_post_stats(event: Union[types.CallbackQuery, types.Message]):
    """
    Обработчик для получения статистики постов.
    Выводит статистику для каждого поста пользователя, включая просмотры, реакции и клики по Bitly-ссылке.
    """
    send = event.message.answer if isinstance(event, types.CallbackQuery) else event.answer

    async with async_session() as session:
        try:
            # Получаем все опубликованные посты пользователя
            result = await session.execute(
                select(Post)
                .where(Post.user_id == event.from_user.id, Post.status == "published")
                .order_by(Post.published_at.desc())
            )
            posts = result.scalars().all()

            if not posts:
                await send("❌ У вас нет опубликованных постов.", parse_mode="HTML")
                return

            response_text = "📊 <b>Статистика ваших постов:</b>\n\n"

            for post in posts:
                if not post.telegram_message_id:
                    logger.warning(f"⚠️ Пропускаем пост {post.id}, так как отсутствует telegram_message_id")
                    continue

                try:
                    from services.telegram_stats import get_post_stats
                    stats = await get_post_stats([post.telegram_message_id])
                    views = stats[0].get("views", "❓") if stats and "views" in stats[0] else "❓"
                    reactions = stats[0].get("reactions", "❓") if stats and "reactions" in stats[0] else "❓"
                except TelegramAPIError as e:
                    logger.warning(f"⚠️ Не удалось получить статистику для поста {post.id}: {e}")
                    views = "❓"
                    reactions = "❓"

                clicks = "❓"
                if post.short_url:
                    try:
                        from services.bitly_service import get_link_clicks
                        click_count = await get_link_clicks(post.short_url)
                        if click_count is not None:
                            clicks = click_count
                        else:
                            clicks = "❓"
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить данные о кликах для поста {post.id}: {e}")
                        clicks = "❓"

                safe_id = html.escape(str(post.id))
                safe_date = html.escape(post.published_at.astimezone(timezone(timedelta(hours=3))).strftime(
                    '%d.%m.%Y %H:%M')) if post.published_at else "❓"

                safe_link = html.escape(post.link) if post.link else "❓"
                link_html = f"<a href=\"{safe_link}\">Перейти</a>" if safe_link != "❓" else "❓"
                safe_views = html.escape(str(views))
                safe_reactions = html.escape(str(reactions))
                safe_clicks = html.escape(str(clicks))

                response_text += (
                    f"📌 <b>ID поста:</b> {safe_id}\n"
                    f"📅 <b>Дата публикации:</b> {safe_date}\n"
                    f"🔗 <b>Ссылка:</b> {link_html}\n"
                    f"🖱 <b>Клики:</b> {safe_clicks}\n"
                    f"👀 <b>Просмотры:</b> {safe_views}\n"
                    f"💬 <b>Реакции:</b> {safe_reactions}\n"
                    "-----------------------------------\n"
                )

            logger.info(f"📊 Итоговый текст статистики:\n{response_text}")

            messages = split_message_by_lines(response_text)
            for msg in messages:
                await send(msg, parse_mode="HTML")

        except Exception as e:
            logger.error(f"❌ Ошибка при получении статистики постов: {e}", exc_info=True)
            await send("❌ Ошибка при получении статистики постов.", parse_mode="HTML")

def register_stats_handlers(dp):
    dp.include_router(router)

# publisher.py
import re
import traceback
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select, update
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from config import TELEGRAM_TOKEN, TEST_CHANNEL_ID, CHANNEL_USERNAME
from models.models import Post
from services.database import async_session
from services.bitly_service import shorten_url
from logs import get_logger

logger = get_logger("publisher")
bot = Bot(token=TELEGRAM_TOKEN)
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def add_unique_query_param(url: str, post_id: int) -> str:
    logger.debug(f"Добавляем уникальный параметр post_id={post_id} к URL: {url}")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query['post_id'] = str(post_id)
    new_query = urlencode(query, doseq=True)
    new_parsed = parsed._replace(query=new_query)
    result = urlunparse(new_parsed)
    logger.debug(f"Результат: {result}")
    return result


def remove_url(text: str, url: str) -> str:
    logger.debug(f"Удаляем URL из текста: {url[:50]}...")
    pattern = re.compile(re.escape(url), re.IGNORECASE)
    return pattern.sub("", text)


def escape_markdown_v2(text: str) -> str:
    special_chars = r"_*[]()~`>#+=|{}.!-\\"
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text


def escape_markdown_v2_except_links(text: str) -> str:
    """
    Экранирует MarkdownV2, кроме ссылок вида [текст](url).
    Внутри якоря экранируются специальные символы, URL экранируется частично (скобки, пробелы).
    """
    logger.debug("Экранируем MarkdownV2 (кроме ссылок)")
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    result = ''
    last_end = 0

    def escape_text(s):
        return re.sub(r'([_\*\[\]\(\)~`>#+\-=|{}.!\\])', r'\\\1', s)

    for match in link_pattern.finditer(text):
        start, end = match.span()
        anchor, url = match.groups()

        # Экранируем текст до ссылки
        result += escape_text(text[last_end:start])

        # Экранируем ссылку — скобки и пробелы
        escaped_url = url.replace("(", "\\(").replace(")", "\\)").replace(" ", "%20")
        escaped_anchor = escape_text(anchor)
        result += f"[{escaped_anchor}]({escaped_url})"

        last_end = end

    # Экранируем оставшийся текст
    result += escape_text(text[last_end:])
    return result


async def publish_to_channel(post_id: int) -> str:
    logger.info(f"📤 Инициируется публикация поста с ID: {post_id}")

    try:
        async with async_session() as session:
            async with session.begin():
                logger.debug(f"Загружаем пост {post_id} из БД...")
                result = await session.execute(
                    select(Post).where(Post.id == post_id).with_for_update()
                )
                post = result.scalars().first()

                if not post:
                    logger.error(f"❌ Ошибка: пост ID {post_id} не найден в БД.")
                    return "❌ Ошибка: пост не найден."

                logger.info(f"✅ Пост {post_id} загружен из БД, статус: {post.status}")

                if post.status in ("published", "publishing"):
                    logger.warning(f"⚠️ Пост {post_id} уже обрабатывается (статус: {post.status})")
                    return "⚠️ Пост уже обрабатывается или опубликован."

                logger.info(f"Меняем статус поста {post_id} на 'publishing'")
                post.status = "publishing"
                await session.flush()

                current_post_id = post.id
                content_local = post.content
                description_local = post.description
                link_local = post.link
                image_url_local = post.image_url
                short_url_local = post.short_url

        logger.info(f"🔧 Формируем контент для публикации...")
        formatted_content = f"{content_local}\n\n{description_local}"

        if link_local:
            logger.info(f"🔗 Обрабатываем ссылку: {link_local[:50]}...")
            unique_long_url = add_unique_query_param(link_local, current_post_id)

            try:
                logger.info("🔗 Сокращаем ссылку через Bitly...")
                short_url_local = shorten_url(unique_long_url) or unique_long_url
                logger.info(f"✅ Bitly: {short_url_local[:50]}...")
            except Exception as e:
                logger.error(f"⚠️ Ошибка Bitly: {e}. Используем оригинальную ссылку.")
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                short_url_local = unique_long_url

            formatted_content = remove_url(formatted_content, link_local)
            formatted_content += f"\n🔗 [Перейти к товару]({short_url_local})"

        logger.info("⚙️ Экранируем Markdown...")
        formatted_content = escape_markdown_v2_except_links(formatted_content)
        logger.info(f"📝 Отправляемый текст (первые 200 символов):\n{formatted_content[:200]}...")

        try:
            if image_url_local:
                logger.info(f"📷 Публикуем с изображением: {image_url_local[:100]}...")
                caption = formatted_content[:1024]
                logger.debug(f"Caption длина: {len(caption)} символов")

                msg = await bot.send_photo(
                    chat_id=TEST_CHANNEL_ID,
                    photo=image_url_local,
                    caption=caption,
                    parse_mode="MarkdownV2"
                )
                logger.info(f"✅ Фото отправлено, message_id: {msg.message_id}")
            else:
                logger.info("📝 Публикуем текстовое сообщение без изображения...")
                msg = await bot.send_message(
                    chat_id=TEST_CHANNEL_ID,
                    text=formatted_content,
                    parse_mode="MarkdownV2"
                )
                logger.info(f"✅ Сообщение отправлено, message_id: {msg.message_id}")

            # 🎉 Добавляем реакции после публикации
            try:
                logger.info(f"🎭 Добавляем реакции к сообщению {msg.message_id}...")
                from services.reaction_sender import send_reactions
                await send_reactions(channel_username=CHANNEL_USERNAME, message_id=msg.message_id)
                logger.info(f"✅ Реакции успешно добавлены")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось добавить реакции: {e}")
                logger.warning(f"Traceback:\n{traceback.format_exc()}")

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке поста ID {current_post_id}: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")

            logger.info(f"Возвращаем статус поста {current_post_id} в 'scheduled'")
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(Post).where(Post.id == current_post_id).values(status="scheduled")
                    )
            return "❌ Ошибка публикации поста."

        logger.info(f"💾 Обновляем пост {current_post_id} в БД со статусом 'published'...")
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(Post).where(Post.id == current_post_id).values(
                        telegram_message_id=msg.message_id,
                        published_at=datetime.now(MOSCOW_TZ),
                        status="published",
                        short_url=short_url_local
                    )
                )

        logger.info(f"✅ Пост {current_post_id} успешно опубликован! Message ID: {msg.message_id}")
        return "✅ Пост успешно опубликован."

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в publish_to_channel для поста {post_id}: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return f"❌ Критическая ошибка: {e}"
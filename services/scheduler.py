from datetime import datetime
import asyncio
from sqlalchemy.future import select
from aiogram import Bot

from config import TELEGRAM_TOKEN, TEST_CHANNEL_ID
from logs import get_logger
from models.models import Post, Payment
from services.database import async_session
from services.metrics import (
    POSTS_PUBLISHED,
    POSTS_FAILED,
    PAYMENT_REFUNDS,
    PUBLISH_LATENCY,
    CHECK_REFUNDS_LATENCY,
)
from services.payments import get_payment_status
from services.publisher import publish_to_channel
from services.random_post_publisher import publish_random_product
from services.slot_manager import SLOTS, MOSCOW_TZ, TOLERANCE

logger = get_logger("scheduler")
bot = Bot(token=TELEGRAM_TOKEN)


async def check_for_refunds_loop():
    while True:
        try:
            with CHECK_REFUNDS_LATENCY.time():
                logger.info("🚩 Проверка возвратов запущена.")
                async with async_session() as session:
                    async with session.begin():
                        payments_query = await session.execute(
                            select(Payment).where(Payment.status.in_(["succeeded", "refunded"]))
                        )
                        payments = payments_query.scalars().all()

                        for payment in payments:
                            current_status = await get_payment_status(payment.payment_id)

                            if current_status == "refunded" and payment.status != "refunded":
                                payment.status = "refunded"
                                PAYMENT_REFUNDS.inc()

                                post_result = await session.execute(
                                    select(Post).where(Post.id == payment.post_id)
                                )
                                post = post_result.scalars().first()

                                if post:
                                    previous_status = post.status
                                    post.status = "canceled"

                                    if previous_status == "scheduled":
                                        logger.info(f"✅ Отменена публикация поста {post.id}")
                                    elif previous_status == "published":
                                        try:
                                            await bot.delete_message(
                                                chat_id=TEST_CHANNEL_ID,
                                                message_id=post.telegram_message_id
                                            )
                                            logger.info(f"✅ Пост {post.id} удалён из канала.")
                                        except Exception as e:
                                            logger.error(f"❌ Ошибка удаления поста: {e}")

                                    if post.user_id:
                                        try:
                                            await bot.send_message(
                                                post.user_id,
                                                f"⚠️ Ваш пост {post.id} был отменён из-за возврата средств.\n"
                                                f"Если это ошибка — обратитесь в поддержку."
                                            )
                                            logger.info(f"📩 Уведомление отправлено пользователю {post.user_id}")
                                        except Exception as e:
                                            logger.error(f"❌ Ошибка уведомления: {e}")

                                logger.info(f"⚠️ Возврат платежа {payment.payment_id}, пост {payment.post_id} отменён.")
                    await session.commit()
        except Exception as e:
            logger.error(f"🚨 Ошибка в check_for_refunds_loop: {e}", exc_info=True)

        await asyncio.sleep(60)


async def scheduled_post_loop():
    while True:
        sleep_duration = 60
        try:
            async with async_session() as session:
                now = datetime.now(MOSCOW_TZ).replace(second=0, microsecond=0)
                start_time = now - TOLERANCE
                end_time = now + TOLERANCE
                logger.info(f"🔍 Проверка постов на публикацию ({now.strftime('%Y-%m-%d %H:%M')} MSK)")

                post_query = await session.execute(
                    select(Post).where(Post.published_at.between(start_time, end_time), Post.status == "scheduled")
                )
                posts = post_query.scalars().all()

                if posts:
                    for post in posts:
                        logger.info(f"📌 Публикуем пост ID {post.id}")
                        with PUBLISH_LATENCY.time():
                            publish_result = await publish_to_channel(post.id)

                        await session.refresh(post)  # Обновляем объект, чтобы получить telegram_message_id

                        if "✅" in publish_result:
                            POSTS_PUBLISHED.inc()
                            logger.info(f"✅ Пост {post.id} опубликован.")
                            if post.user_id:
                                try:
                                    await bot.send_message(
                                        post.user_id,
                                        f"✅ Ваш пост {post.id} опубликован {now.strftime('%d.%m %H:%M')} MSK!\n"
                                        f"🔗 [Смотреть](https://t.me/wildberriesStuff1/{post.telegram_message_id})",
                                        parse_mode="Markdown"
                                    )
                                except Exception as e:
                                    logger.error(f"❌ Ошибка уведомления пользователя: {e}")
                        else:
                            POSTS_FAILED.inc()
                            logger.error(f"❌ Ошибка публикации поста {post.id}")
                else:
                    slot_matched = False
                    for hour, minute in SLOTS:
                        slot_time = now.replace(hour=hour, minute=minute)
                        if abs((slot_time - now).total_seconds()) <= TOLERANCE.total_seconds():
                            slot_matched = True
                            logger.info("🟢 Слот пуст — публикуем случайный товар.")
                            await publish_random_product("products.txt")
                            break

                    if not slot_matched:
                        logger.info("⚪️ Не время слота — постов нет.")

                next_post_query = await session.execute(
                    select(Post).where(Post.status == "scheduled", Post.published_at > now).order_by(Post.published_at)
                )
                next_post = next_post_query.scalars().first()

                if next_post:
                    delta = (next_post.published_at - now).total_seconds()
                    sleep_duration = min(max(delta - 30, 5), 60)
                    logger.info(
                        f"📅 Следующий пост в {next_post.published_at.astimezone(MOSCOW_TZ).strftime('%d.%m %H:%M')} MSK."
                        f" Ожидание: {sleep_duration} сек."
                    )
                else:
                    logger.info("⏳ Следующих постов нет.")

        except Exception as e:
            logger.error(f"🚨 Ошибка в scheduled_post_loop: {e}", exc_info=True)

        await asyncio.sleep(sleep_duration)


async def scheduler():
    await asyncio.gather(
        check_for_refunds_loop(),
        scheduled_post_loop()
    )

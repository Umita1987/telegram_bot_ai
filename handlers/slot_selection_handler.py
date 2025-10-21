from zoneinfo import ZoneInfo

from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from sqlalchemy.future import select
from services.database import async_session
from models.models import Post
from datetime import datetime, timezone, timedelta
from handlers.callback_handlers import back_to_main_menu
from logs import get_logger

logger = get_logger("slot_selection_handlers")
router = Router()

# Московский часовой пояс
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

@router.callback_query(lambda c: c.data.startswith("slot_"))
async def slot_selection_handler(callback_query: types.CallbackQuery, state: FSMContext):
    logger.info(f"📩 Получен callback_query: {callback_query.data}")

    try:
        _, post_id_str, slot_time_str = callback_query.data.split("_")
        post_id = int(post_id_str)

        # Время из callback всегда трактуем как Московское (без пояса)
        slot_time_naive = datetime.fromisoformat(slot_time_str)
        slot_time_msk = slot_time_naive.replace(tzinfo=MOSCOW_TZ)

        # Сохраняем в базу в формате UTC
        slot_time_utc = slot_time_msk.astimezone(timezone.utc)

    except Exception as e:
        logger.error(f"❌ Ошибка разбора callback.data: {e}", exc_info=True)
        await callback_query.answer("❌ Ошибка: неверный формат данных.", show_alert=True)
        return

    try:
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(select(Post).where(Post.id == post_id))
                post = result.scalars().first()

                if not post:
                    logger.error(f"❌ Ошибка: пост ID {post_id} не найден.")
                    await callback_query.answer("❌ Ошибка: пост не найден.", show_alert=True)
                    return

                post.published_at = slot_time_utc  # в базе всегда UTC
                post.status = "scheduled"
                session.add(post)

                await session.flush()
                current_post_id = post.id

            logger.info(f"✅ Пост {current_post_id} запланирован на {slot_time_msk.strftime('%d.%m %H:%M')} MSK.")

    except Exception as e:
        logger.error(f"❌ Ошибка работы с БД: {e}", exc_info=True)
        await callback_query.answer("❌ Ошибка работы с базой данных.", show_alert=True)
        return

    try:
        await callback_query.message.edit_reply_markup(reply_markup=None)
        logger.info(f"✅ Убрали кнопки у сообщения ID {callback_query.message.message_id}")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при удалении кнопок: {e}")

    await callback_query.message.answer(
        f"✅ Ваш пост запланирован на {slot_time_msk.strftime('%d.%m %H:%M')} MSK!"
    )

    logger.info(f"🔄 Возвращаем пользователя {callback_query.from_user.id} в главное меню...")
    await back_to_main_menu(callback_query)

def register_slot_selection_handler(dp):
    dp.include_router(router)

from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from handlers.keyboards import generate_publish_keyboard, generate_payment_keyboard
from services.database import async_session
from services.slot_manager import find_nearest_slots
from handlers.callback_handlers import generate_ad_text
from models.models import Post, Payment
from logs import get_logger

logger = get_logger("approval_handlers")
router = Router()


@router.callback_query(lambda c: c.data.startswith("accept_post:"))
async def accept_post(callback: types.CallbackQuery):
    """Обработчик принятия поста (callback data: "accept_post:<post_id>")"""
    try:
        _, post_id_str = callback.data.split(":")
        post_id = int(post_id_str)
    except ValueError:
        logger.error("❌ Ошибка: Неверный формат ID поста.", exc_info=True)
        await callback.message.answer("❌ Ошибка: неверные данные.")
        return

    async with async_session() as session:
        async with session.begin():
            post_result = await session.execute(select(Post).where(Post.id == post_id))
            post = post_result.scalars().first()

            if not post:
                await callback.message.answer("❌ Пост не найден.")
                return

            # Проверяем, был ли успешный платеж для этого поста
            payment_result = await session.execute(
                select(Payment).where(Payment.post_id == post.id, Payment.status == "succeeded")
            )
            payment = payment_result.scalars().first()

            # Убираем inline-кнопки, чтобы предотвратить повторное нажатие
            await callback.message.edit_reply_markup(reply_markup=None)

            if payment:
                post.status = "paid"
                post_id_confirmed = post.id
                await session.commit()

                logger.info(f"✅ Пост {post_id_confirmed} уже оплачен.")

                slots = await find_nearest_slots(session)
                keyboard = generate_publish_keyboard(post_id_confirmed, slots)
                await callback.message.answer(
                    "✅ Оплата подтверждена! Теперь вы можете опубликовать пост.",
                    reply_markup=keyboard
                )
                return

            # Если платежа нет – переводим в статус "accepted" и предлагаем оплату
            post.status = "accepted"
            post_id_confirmed = post.id
            await session.commit()
            logger.info(f"✅ Пользователь одобрил пост ID {post_id_confirmed}.")

            keyboard = generate_payment_keyboard(post_id_confirmed)
            await callback.message.answer(
                "✅ Пост принят. Теперь вы можете его оплатить.",
                reply_markup=keyboard
            )

@router.callback_query(lambda c: c.data.startswith("publish_post:"))
async def publish_post(callback: types.CallbackQuery):
    """Обработчик публикации поста (callback data: "publish_post:<post_id>")."""
    try:
        _, post_id_str = callback.data.split(":")
        post_id = int(post_id_str)
    except ValueError:
        logger.error("❌ Ошибка: Неверный формат ID поста.", exc_info=True)
        await callback.message.answer("❌ Ошибка: неверные данные.")
        return

    # Убираем inline-кнопки, чтобы предотвратить повторное нажатие
    await callback.message.edit_reply_markup(reply_markup=None)

    user_id = callback.from_user.id

    async with async_session() as session:
        async with session.begin():
            # Проверяем успешный платеж для указанного post_id
            payment_result = await session.execute(
                select(Payment).where(Payment.post_id == post_id, Payment.status == "succeeded")
            )
            payment = payment_result.scalars().first()

            if not payment:
                logger.warning(f"⚠️ Для поста {post_id} успешный платеж не найден.")
                await callback.message.answer("❌ Оплаченный пост не найден.")
                return

            # Получаем пост со статусом "paid"
            post_result = await session.execute(
                select(Post).where(Post.id == post_id, Post.status == "paid")
            )
            post = post_result.scalars().first()

            if not post:
                logger.error("❌ Пост не найден.")
                await callback.message.answer("❌ Ошибка: пост не найден.")
                return

            logger.info(f"🔍 Выбран пост ID {post.id} для публикации.")

            # Получаем ближайшие слоты для публикации
            nearest_slots = await find_nearest_slots(session)
            keyboard = generate_publish_keyboard(post.id, nearest_slots)

            await callback.message.answer(
                "✅ Оплата завершена! Выберите время публикации.",
                reply_markup=keyboard
            )


@router.callback_query(lambda c: c.data == "regenerate_text")
async def regenerate_text(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик перегенерации текста поста."""
    try:
        user_id = callback.from_user.id

        async with async_session() as session:
            async with session.begin():
                post_result = await session.execute(
                    select(Post).where(Post.user_id == user_id, Post.status == "draft").order_by(Post.id.desc())
                )
                post = post_result.scalars().first()

                if not post:
                    await callback.message.answer("❌ Черновик поста не найден.")
                    return

        # ✅ Вместо удаления клавиатуры просто отправляем новое сообщение
        await generate_ad_text(callback, state)
        logger.info(f"🔄 Текст поста {post.id} был обновлён.")

    except SQLAlchemyError as e:
        logger.error(f"❌ Ошибка работы с БД: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка работы с базой данных.")
    except Exception as e:
        logger.error(f"❌ Ошибка перегенерации текста: {e}", exc_info=True)
        await callback.message.answer(f"❌ Ошибка перегенерации текста: {e}")



def register_approval_handlers(dp):
    """Регистрирует обработчики для публикации постов."""
    dp.include_router(router)
    logger.info("✅ Обработчики публикации постов зарегистрированы.")

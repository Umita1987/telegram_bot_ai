from aiogram import Router, types
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

from services.database import async_session
from models.models import Payment, Post
from services.payments import check_and_update_payment
from services.slot_manager import find_nearest_slots
from handlers.keyboards import generate_publish_keyboard
from logs import get_logger

logger = get_logger("payment_callback")
router = Router()


@router.callback_query(lambda c: c.data.startswith("confirm_payment_"))
async def confirm_payment(callback_query: types.CallbackQuery) -> None:
    """
    Обработчик подтверждения платежа через callback.
    """
    _, payment_id = callback_query.data.split("_")

    async with async_session() as session:
        try:
            # Получаем платеж с учетом последнего по времени (если их несколько)
            result = await session.execute(
                select(Payment)
                .where(Payment.payment_id == payment_id)
                .order_by(Payment.created_at.desc())  # Берем самый последний платеж
            )
            payment = result.scalars().first()

            if not payment:
                logger.warning(f"⚠️ Платеж {payment_id} не найден в БД.")
                await callback_query.answer("❌ Ошибка: платеж не найден.", show_alert=True)
                return

            # Логируем данные платежа перед проверкой
            logger.info(f"🔍 Найден платеж: {payment_id}, post_id={payment.post_id}, status={payment.status}")

            # Проверяем и обновляем статус платежа
            if payment.status == "succeeded":
                await callback_query.answer("✅ Этот платеж уже подтвержден.", show_alert=True)
                return

            if not await check_and_update_payment(payment, session):
                await callback_query.answer("⚠️ Оплата не подтверждена, попробуйте позже.", show_alert=True)
                return

            # Получаем связанный пост
            post_result = await session.execute(
                select(Post).where(Post.id == payment.post_id)
            )
            post = post_result.scalars().first()

            if not post:
                logger.error(f"❌ Ошибка: пост {payment.post_id} не найден.")
                await callback_query.answer("❌ Ошибка: пост не найден.", show_alert=True)
                return

            # Логируем обновленный статус платежа
            logger.info(f"✅ Платеж {payment_id} подтвержден, обновляем пост {post.id}.")

            # Обновляем статус поста
            post.status = "paid"
            await session.commit()

            # Получаем ближайшие слоты и отправляем пользователю клавиатуру
            nearest_slots = await find_nearest_slots(session)
            keyboard = generate_publish_keyboard(post.id, nearest_slots)

            try:
                await callback_query.message.answer(
                    "✅ Оплата успешно подтверждена! Выберите время публикации.", reply_markup=keyboard
                )
                await callback_query.answer()
            except Exception as e:
                logger.error(f"❌ Ошибка отправки сообщения пользователю {payment.user_id}: {e}")

        except SQLAlchemyError as e:
            logger.error(f"❌ Ошибка работы с БД: {e}", exc_info=True)
            await callback_query.answer("❌ Ошибка работы с базой данных.", show_alert=True)
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке подтверждения платежа: {e}", exc_info=True)
            await callback_query.answer("❌ Произошла ошибка. Попробуйте ещё раз.", show_alert=True)


def register_payment_callback_handlers(dp):
    dp.include_router(router)

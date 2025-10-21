import json
import logging
from aiogram import Router, types
from aiogram.types import LabeledPrice, PreCheckoutQuery
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from aiogram.exceptions import TelegramAPIError

from services.database import async_session
from models.models import Payment, Post
from config import PAYMENT_PROVIDER_TOKEN
from services.slot_manager import find_nearest_slots

logger = logging.getLogger("payment_handlers")
router = Router()


@router.callback_query(lambda c: c.data.startswith("pay_post:"))
async def handle_payment(callback: types.CallbackQuery):
    """
    Обработчик кнопки "Оплатить", где callback_data имеет формат "pay_post:<post_id>".
    После нажатия удаляется inline‑клавиатура из сообщения.
    Сохраняем ID сообщения-инвойса в базе (новое поле invoice_message_id в модели Payment).
    """
    # Удаляем inline‑клавиатуру, чтобы предотвратить повторное нажатие
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"Не удалось удалить клавиатуру: {e}")

    try:
        _, post_id_str = callback.data.split(":")
        post_id = int(post_id_str)
    except ValueError:
        await callback.message.answer("❌ Неверные данные оплаты.")
        return

    user_id = callback.from_user.id
    bot = callback.bot

    async with async_session() as session:
        try:
            # Ищем пост с конкретным ID и статусом "accepted" для текущего пользователя
            result = await session.execute(
                select(Post).where(
                    Post.id == post_id,
                    Post.user_id == user_id,
                    Post.status == "accepted"
                )
            )
            post = result.scalars().first()

            if not post:
                await callback.message.answer("❌ Пост для оплаты не найден.")
                return

            # Создаём запись платежа в БД (Payment), в которой есть поле invoice_message_id (String).
            payment_record = Payment(
                user_id=user_id,
                post_id=post.id,
                amount=100.0,
                status="pending",
                payment_id=None,
                invoice_message_id=None  # Здесь будет храниться ID сообщения-инвойса
            )
            session.add(payment_record)
            await session.commit()

            # Формируем JSON-данные для поля provider_data
            # В реальном проекте можно динамически подставлять email/phone/цены и т.д.
            provider_data_dict = {
                "receipt": {
                    "customer": {
                        "email": "example@example.com",
                        "phone": "79211234567"
                    },
                    "items": [
                        {
                            "description": f"Публикация поста ID {post.id}",
                            "quantity": "1.0",
                            "amount": {
                                "value": "100.00",
                                "currency": "RUB"
                            },
                            "vat_code": "1",               # Ставка НДС, пример
                            "payment_mode": "full_payment",
                            "payment_subject": "commodity"
                        }
                    ],
                    "tax_system_code": 1
                }
            }

            # Отправляем счёт пользователю, передавая provider_data
            try:
                invoice_msg = await bot.send_invoice(
                    chat_id=user_id,
                    title="Оплата публикации поста",
                    description=f"Оплата за публикацию поста ID {post.id}",
                    provider_token=PAYMENT_PROVIDER_TOKEN,
                    currency="RUB",
                    prices=[LabeledPrice(label="Публикация поста", amount=10000)],
                    start_parameter="publish",
                    payload=str(post.id),
                    provider_data=json.dumps(provider_data_dict)  # <-- ключевой момент
                )

                # Сохраняем ID сообщения-инвойса (конвертируем в str) в payment_record
                payment_record.invoice_message_id = str(invoice_msg.message_id)
                await session.commit()

            except TelegramAPIError as e:
                logger.error(f"❌ Ошибка отправки счета: {e}")
                await callback.message.answer("❌ Ошибка при отправке счета, попробуйте позже.")

        except SQLAlchemyError as e:
            logger.error(f"❌ Ошибка работы с БД: {e}", exc_info=True)
            await callback.message.answer("❌ Ошибка работы с базой данных.")


@router.pre_checkout_query()
async def process_pre_checkout_query(query: PreCheckoutQuery):
    """
    Обрабатываем pre_checkout_query и сохраняем payment_id (Telegram Payment ID) перед успешной оплатой.
    """
    logger.info(f"📌 Получен pre_checkout_query: {query}")

    async with async_session() as session:
        try:
            payment_result = await session.execute(
                select(Payment).where(
                    Payment.user_id == query.from_user.id,
                    Payment.post_id == int(query.invoice_payload)
                )
            )
            payment = payment_result.scalars().first()

            if payment:
                payment.payment_id = query.id  # Telegram Payment ID
                await session.commit()
                logger.info(f"✅ Сохранен payment_id {query.id} для платежа post_id={query.invoice_payload}")
            else:
                logger.warning(
                    f"⚠️ Платеж не найден в БД (user_id={query.from_user.id}, post_id={query.invoice_payload})"
                )
        except SQLAlchemyError as e:
            logger.error(f"❌ Ошибка работы с БД при pre_checkout_query: {e}", exc_info=True)

    await query.bot.answer_pre_checkout_query(query.id, ok=True)


@router.message(lambda m: m.successful_payment is not None)
async def handle_successful_payment(message: types.Message):
    """
    Обработчик успешного платежа от Telegram.
    1) Используем invoice_payload, чтобы определить post_id.
    2) Обновляем Payment (status='succeeded', payment_id).
    3) Обновляем Post (status='paid').
    4) Удаляем сообщение-инвойс, если invoice_message_id есть в базе.
    5) Предлагаем выбрать время публикации.
    """
    user_id = message.from_user.id
    invoice_payload = message.successful_payment.invoice_payload

    try:
        post_id = int(invoice_payload)
    except ValueError:
        logger.error("❌ Ошибка конвертации invoice_payload в post_id", exc_info=True)
        await message.answer("❌ Ошибка обработки платежа.")
        return

    payment_charge_id = message.successful_payment.provider_payment_charge_id
    logger.info(f"✅ Получено successful_payment: {payment_charge_id} для поста {post_id}")

    async with async_session() as session:
        async with session.begin():
            # Ищем запись Payment в статусе "pending"
            payment_result = await session.execute(
                select(Payment).where(
                    Payment.user_id == user_id,
                    Payment.post_id == post_id,
                    Payment.status == "pending"
                )
            )
            payment = payment_result.scalars().first()
            if not payment:
                logger.warning(f"❌ Платеж не найден (user_id={user_id}, post_id={post_id}).")
                await message.answer("❌ Ошибка: платеж не найден.")
                return

            payment.status = "succeeded"
            payment.payment_id = payment_charge_id

            # Обновляем статус поста
            post_result = await session.execute(
                select(Post).where(Post.id == post_id)
            )
            post = post_result.scalars().first()
            if post:
                post.status = "paid"
                logger.info(f"✅ Статус поста {post.id} обновлен на 'paid'.")
            else:
                logger.warning(f"⚠️ Не найден пост для платежа {payment.id}")
                return
        await session.commit()

    # Удаляем сообщение-инвойс, если invoice_message_id было сохранено
    invoice_msg_id = payment.invoice_message_id
    if invoice_msg_id:
        try:
            await message.bot.delete_message(chat_id=user_id, message_id=int(invoice_msg_id))
            logger.info(f"✅ Удалено сообщение-инвойс (ID={invoice_msg_id}).")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить сообщение-инвойс: {e}")

    # Предлагаем выбрать время публикации
    async with async_session() as session:
        try:
            from handlers.keyboards import generate_publish_keyboard
            nearest_slots = await find_nearest_slots(session)
            keyboard = generate_publish_keyboard(post_id, nearest_slots)
            await message.answer("✅ Оплата успешно подтверждена! Выберите время публикации.", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке клавиатуры слотов: {e}")


def register_payment_handlers(dp):
    dp.include_router(router)
    dp.message.register(handle_successful_payment, lambda m: m.successful_payment is not None)

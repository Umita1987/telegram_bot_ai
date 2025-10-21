import aiohttp
import base64
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from models.models import Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_URL

logger = logging.getLogger("payments")

HEADERS = {
    "Authorization": "Basic " + base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode(),
    "Content-Type": "application/json"
}

async def get_payment_status(payment_id: str) -> str:
    """Проверяет статус платежа через /payments/{payment_id}, включая возвраты."""
    if not payment_id:
        raise ValueError("❌ Ошибка: payment_id не может быть пустым.")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{YOOKASSA_URL}/{payment_id}", headers=HEADERS) as payment_resp:
                if payment_resp.status == 200:
                    payment_result = await payment_resp.json()
                    refunded = float(payment_result.get("refunded_amount", {}).get("value", "0"))
                    paid = float(payment_result.get("amount", {}).get("value", "0"))

                    # 🟡 Проверка на полный возврат
                    if refunded >= paid and paid > 0:
                        return "refunded"

                    return payment_result.get("status", "unknown")

                elif payment_resp.status == 404:
                    logger.warning(f"⚠️ Платеж {payment_id} не найден в YooKassa.")
                    return "not_found"
                else:
                    logger.error(f"❌ Ошибка API YooKassa: {payment_resp.status} - {await payment_resp.text()}")
                    return "error"

        except Exception as e:
            logger.error(f"❌ Ошибка при получении статуса платежа {payment_id}: {e}")
            return "error"



async def check_and_update_payment(session: AsyncSession, payment: Payment) -> Optional[bool]:
    """Проверяет статус платежа и обновляет запись в БД."""
    if not payment.payment_id:
        logger.warning(f"⚠️ У платежа {payment.id} нет payment_id, ждем следующую проверку.")
        return None

    try:
        status = await get_payment_status(payment.payment_id)
        logger.info(f"🔔 YooKassa статус платежа {payment.payment_id}: {status}")
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке платежа {payment.payment_id}: {e}")
        return None

    if status == "succeeded":
        payment.status = "succeeded"
        await session.commit()
        logger.info(f"✅ Платеж {payment.payment_id} успешно завершен!")
        return True

    elif status == "canceled":
        payment.status = "canceled"
        await session.commit()
        logger.warning(f"⚠️ Платеж {payment.payment_id} был отменен.")
        return False

    elif status == "refunded":
        payment.status = "refunded"
        await session.commit()
        logger.warning(f"⚠️ Платеж {payment.payment_id} был возвращён.")
        return False

    return None

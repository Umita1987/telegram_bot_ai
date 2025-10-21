from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.future import select
from models.models import Post

from logs import get_logger
logger = get_logger("slot_manager")

# Часовой пояс Москвы (UTC+2)
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# Доступные слоты публикации в Московском времени (UTC+2)
SLOTS = [(7,10), (9,20), (11,54), (18,00),(23,35)]  # Московское время

TOLERANCE = timedelta(seconds=10)  # Допуск при сравнении времени слота

async def find_nearest_slots(session, num_slots=6):
    """
    Ищет ближайшие свободные слоты в московском времени (UTC+2).
    - Сначала проверяются слоты на сегодня.
    - Если слотов недостаточно, добавляются слоты на следующий день.
    """
    now = datetime.now(MOSCOW_TZ).replace(second=0, microsecond=0)
    logger.info(f"🔍 Поиск ближайших слотов. Сейчас {now.strftime('%Y-%m-%d %H:%M')} MSK")

    available_slots = []
    days_ahead = 0  # Начинаем с сегодняшнего дня

    while len(available_slots) < num_slots:
        target_day = now + timedelta(days=days_ahead)
        for hour, minute in SLOTS:
            # Формируем время слота в московском времени
            slot_time = datetime.combine(target_day.date(), datetime.min.time(), tzinfo=MOSCOW_TZ).replace(
                hour=hour, minute=minute
            )
            # Проверяем только будущие слоты
            if slot_time > now:
                # Проверяем, занят ли слот с учетом допуска TOLERANCE
                result = await session.execute(
                    select(Post.id).where(
                        Post.published_at.between(slot_time - TOLERANCE, slot_time + TOLERANCE)
                    )
                )
                if result.scalar() is None:  # Если нет записи, слот свободен
                    available_slots.append(slot_time)
            if len(available_slots) == num_slots:
                break  # Достаточно слотов
        days_ahead += 1  # Если слотов не хватает, проверяем следующий день

    logger.info(f"📅 Найдены ближайшие {len(available_slots)} свободных слотов: {available_slots}")
    return available_slots

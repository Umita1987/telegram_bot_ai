import re
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from handlers.keyboards import generate_generate_text_keyboard
from services.parser import parse_product
from services.parser_ozon import parse_ozon_with_zenrows_bs4
from config import ZENROWS_API_KEY

from logs import get_logger

logger = get_logger("user_handlers")

router = Router()

# Регулярные выражения для проверки ссылок
WILDBERRIES_URL_PATTERN = re.compile(r"https?://(www\.)?wildberries\.\w{2,3}/catalog/\d+")
OZON_URL_PATTERN = re.compile(r"https?://(www\.)?ozon\.ru/product/[^/]+-(\d+)/")


@router.message()
async def handle_user_message(message: Message, state: FSMContext):
    """
    Основной обработчик текстовых сообщений.
    - Проверяет корректность ссылок Wildberries и Ozon.
    - Отправляет сообщение о парсинге.
    - Запускает процесс получения данных о товаре.
    """
    # Игнорируем сообщения без текста
    if not message.text:
        return

    # Если сообщение содержит кнопку «Статистика постов» — перенаправляем в соответствующий обработчик
    if message.text.strip() == "📊 Статистика постов":
        from handlers.stats_handlers import view_post_stats
        await view_post_stats(message)
        return

    # Игнорируем команды
    if message.text.strip().startswith("/"):
        return

    user_text = message.text.strip()

    # Если пользователь редактирует текст поста, передаем управление обработчику редактирования
    current_state = await state.get_state()
    if current_state == "EditPostState:waiting_for_text":
        from handlers.callback_handlers import save_edited_text
        await save_edited_text(message, state)
        return

    # Определяем тип ссылки и парсим соответствующим парсером
    product_data = None

    if WILDBERRIES_URL_PATTERN.match(user_text):
        # Парсинг Wildberries
        await message.reply("🔄 Парсинг данных о товаре с Wildberries... Пожалуйста, подождите.")

        try:
            product_data = parse_product(user_text)
            if product_data:
                # Преобразуем формат данных WB в общий формат
                product_data = {
                    "title": product_data.get("name", ""),
                    "brand": "",  # WB парсер не возвращает бренд отдельно
                    "price": product_data.get("price", ""),
                    "description": product_data.get("description", ""),
                    "characteristics": {},  # WB парсер не возвращает характеристики отдельно
                    "image_url": product_data.get("image_url", ""),
                    "all_images": [product_data.get("image_url", "")] if product_data.get("image_url") else [],
                    "url": product_data.get("url", user_text),
                    "source": "wildberries"
                }
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга Wildberries: {e}")
            await message.reply(f"❌ Ошибка парсинга Wildberries: {e}")
            return

    elif OZON_URL_PATTERN.match(user_text):
        # Парсинг Ozon
        await message.reply("🔄 Парсинг данных о товаре с Ozon... Пожалуйста, подождите.")

        try:
            product_data = parse_ozon_with_zenrows_bs4(user_text, ZENROWS_API_KEY)
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга Ozon: {e}")
            await message.reply(f"❌ Ошибка парсинга Ozon: {e}")
            return

    else:
        await message.reply(
            "❗ Пожалуйста, отправьте корректную ссылку на товар:\n"
            "• Wildberries: https://www.wildberries.ru/catalog/...\n"
            "• Ozon: https://www.ozon.ru/product/..."
        )
        return

    if not product_data:
        await message.reply("❌ Не удалось получить данные о товаре. Попробуйте позже.")
        return

    # Логируем полученные данные
    logger.info(f"✅ Получены данные товара: {product_data['title'][:50]}... из {product_data['source']}")

    # Сохраняем данные в FSMContext в едином формате
    await state.update_data(product_data=product_data)

    # Генерируем клавиатуру для дальнейших действий
    keyboard = generate_generate_text_keyboard()

    # Отправляем пользователю предложение сгенерировать рекламный текст
    source_name = "Wildberries" if product_data['source'] == "wildberries" else "Ozon"
    await message.reply(
        f"✅ Данные о товаре с {source_name} успешно получены. Хотите сгенерировать рекламный текст?",
        reply_markup=keyboard
    )


def register_user_handlers(dp):
    dp.include_router(router)
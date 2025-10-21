# random_post_publisher.py

import random
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

from config import CHANNEL_USERNAME, ZENROWS_API_KEY
from services.parser import parse_product, parse_promo_products
from services.parser_ozon import parse_ozon_with_zenrows_bs4, parse_ozon_category_products, is_valid_product_image
from services.publisher import publish_to_channel
from models.models import Post
from services.database import async_session
from services.content_generator import generate_product_description_sync
from logs import get_logger

from services.reaction_sender import send_reactions
from sqlalchemy import select

logger = get_logger("random_post_publisher")
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# URLs для парсинга товаров
WILDBERRIES_PROMO_URLS = [
    "https://www.wildberries.ru/catalog/zhenshchinam/odezhda/dzhempery-i-kardigany",
    "https://www.wildberries.ru/catalog/zhenshchinam/odezhda/bluzki-i-rubashki",
    "https://www.wildberries.ru/catalog/zhenshchinam/odezhda/platya",
    "https://www.wildberries.ru/catalog/zhenshchinam/odezhda/yubki"
]

OZON_CATEGORY_URLS = [
    "https://www.ozon.ru/highlight/gruppa-populyarnye-brendy-zh-2976006/",
    "https://www.ozon.ru/highlight/premium-zhenskiy-2816469/",
    "https://www.ozon.ru/category/platya-zhenskie-7502/"
]


def clean_ozon_price(price_str: str) -> str:
    """Очищает и форматирует цену товара с Ozon"""
    if not price_str:
        return "Не указана"
    # Заменяем "₽c" на "₽ c" (добавляем пробел)
    price = price_str.replace("₽c", "₽ c")
    return price


async def parse_wildberries_products():
    """Парсинг товаров с Wildberries"""
    promo_url = random.choice(WILDBERRIES_PROMO_URLS)
    logger.info(f"🔥 Получаем товары с Wildberries: {promo_url}")

    try:
        products = parse_promo_products(promo_url, limit=50)
        logger.info(f"📊 WB результат: получено {len(products)} URLs товаров")

        if not products:
            logger.error("❌ WB вернул пустой список товаров!")
            return False

        random.shuffle(products)
        logger.info(f"🎲 Перемешано {len(products)} товаров, начинаем парсинг...")

        for i, product_url in enumerate(products, 1):
            try:
                logger.info(f"📦 [{i}/{len(products)}] Пробуем WB товар: {product_url}")
                product_data = parse_product(product_url)
                logger.info(f"📦 Парсинг WB товара завершён: {product_data}")

                if not product_data or not product_data.get("description") or not product_data.get("image_url"):
                    logger.warning(f"❌ Товар {product_url} неполный или недоступен, пропускаем.")
                    continue

                unified_product_data = {
                    "title": product_data.get("name", ""),
                    "brand": "",
                    "price": product_data.get("price", ""),
                    "description": product_data.get("description", ""),
                    "characteristics": {},
                    "image_url": product_data.get("image_url", ""),
                    "url": product_data.get("url", product_url),
                    "source": "wildberries"
                }

                success = await process_and_publish_product(unified_product_data)
                if success:
                    logger.info(f"✅ WB товар успешно обработан и опубликован")
                    return True

            except Exception as e:
                logger.error(f"❌ Ошибка обработки товара WB {product_url}: {e}")
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                continue

        logger.warning("❌ WB: все товары обработаны, но ни один не подошёл")
        return False

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в parse_wildberries_products: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return False


async def parse_ozon_products():
    """Парсинг товаров с Ozon"""
    category_url = random.choice(OZON_CATEGORY_URLS)
    logger.info(f"🔥 Получаем товары с Ozon: {category_url}")

    try:
        products = parse_ozon_category_products(category_url, limit=20)
        logger.info(f"📊 Ozon результат: получено {len(products)} URLs товаров")
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга категории Ozon: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        from services.parser_ozon import get_fallback_ozon_urls
        products = get_fallback_ozon_urls()
        logger.info(f"⚠️ Используем fallback URLs для Ozon: {len(products)} товаров")

    if not products:
        logger.error("❌ Ozon: список товаров пуст!")
        return False

    random.shuffle(products)
    logger.info(f"🎲 Перемешано {len(products)} Ozon товаров, начинаем парсинг...")

    for i, product_url in enumerate(products, 1):
        try:
            logger.info(f"📦 [{i}/{len(products)}] Пробуем Ozon товар: {product_url}")
            product_data = parse_ozon_with_zenrows_bs4(product_url, ZENROWS_API_KEY)
            logger.info(f"📦 Парсинг Ozon товара: {product_data.get('title', 'N/A') if product_data else 'None'}")

            if not product_data:
                logger.warning(f"❌ Товар Ozon {product_url} не спаршен, пропускаем.")
                continue

            # Дополнительная проверка обязательных полей
            title = product_data.get("title", "").strip()
            price = product_data.get("price", "").strip()
            description = product_data.get("description", "").strip()
            characteristics = product_data.get("characteristics", {})

            if not title or title == "Название отсутствует" or len(title) < 3:
                logger.warning(f"❌ Ozon товар: некорректное название '{title}', пропускаем.")
                continue

            if not price:
                logger.warning(f"❌ Ozon товар: отсутствует цена, пропускаем.")
                continue

            # Если нет описания и характеристик, используем только название для генерации
            if not description and not characteristics:
                logger.info(
                    "⚠️ Ozon товар: отсутствует описание и характеристики, будем использовать только название для генерации"
                )

            image_url = product_data.get("image_url", "")

            if not is_valid_product_image(image_url):
                logger.warning("❌ Товар Ozon имеет некачественное изображение, пробуем альтернативы.")
                logger.debug(f"   Проблемный URL изображения: {image_url}")

                all_images = product_data.get("all_images", [])
                valid_image_found = False

                for img in all_images:
                    if is_valid_product_image(img):
                        product_data["image_url"] = img
                        logger.info(f"✅ Найдено альтернативное изображение: {img[:100]}...")
                        valid_image_found = True
                        break

                if not valid_image_found:
                    logger.warning("❌ Не найдено подходящее изображение для товара, пропускаем.")
                    continue

            image_url = product_data.get("image_url", "")
            if image_url and any(
                    sz in image_url for sz in ['wc50', 'wc100', 'wc200', 'wc250', 'wc300', 'wc400', 'wc500']):
                logger.info("⚙️ Улучшаем качество изображения...")
                for size in ['wc50', 'wc100', 'wc200', 'wc250', 'wc300', 'wc400', 'wc500']:
                    image_url = image_url.replace(size, 'wc1000')
                product_data["image_url"] = image_url
                logger.info(f"✅ Качество улучшено: {image_url[:100]}...")

            # ВАЖНО: помечаем источник перед обработкой
            product_data["source"] = "ozon"

            success = await process_and_publish_product(product_data)
            if success:
                logger.info(f"✅ Ozon товар успешно обработан и опубликован")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка обработки товара Ozon {product_url}: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            continue

    logger.warning("❌ Ozon: все товары обработаны, но ни один не подошёл")
    return False


async def publish_random_product(products_file: str = None):
    """Публикует случайный товар с Wildberries или Ozon с fallback логикой"""

    source = random.choice(["wildberries", "ozon"])
    logger.info(f"🎲 Выбран источник: {source}")

    success = False

    if source == "ozon":
        # Сначала пробуем Ozon
        logger.info("🔍 Пытаемся получить товар с Ozon...")
        success = await parse_ozon_products()

        if not success:
            # Если Ozon не удался, переключаемся на Wildberries
            logger.warning("⚠️ Не удалось получить товар с Ozon, переключаемся на Wildberries...")
            success = await parse_wildberries_products()

            if not success:
                logger.error("❌ Не удалось получить товар ни с Ozon, ни с Wildberries")
    else:
        # Сначала пробуем Wildberries
        logger.info("🔍 Пытаемся получить товар с Wildberries...")
        success = await parse_wildberries_products()

        if not success:
            # Если Wildberries не удался, переключаемся на Ozon
            logger.warning("⚠️ Не удалось получить товар с Wildberries, переключаемся на Ozon...")
            success = await parse_ozon_products()

            if not success:
                logger.error("❌ Не удалось получить товар ни с Wildberries, ни с Ozon")

    if not success:
        logger.warning("❌ Нет доступных товаров для публикации из обоих источников.")
    else:
        logger.info("✅ Публикация товара успешно завершена!")


async def process_and_publish_product(product_data: dict, publish: bool = True) -> bool:
    """
    Общая обработка товара. При publish=False выполняет валидации и сбор текста,
    но НЕ пишет в БД, НЕ публикует и НЕ ставит реакции — удобно для локальных прогонов.
    """
    try:
        logger.info(f"🔧 Начинаем обработку товара: {product_data.get('title', 'N/A')[:50]}...")

        # Проверяем основные поля для Ozon товаров
        if product_data.get("source") == "ozon":
            title = product_data.get("title", "").strip()
            price = product_data.get("price", "").strip()
            image_url = product_data.get("image_url", "")

            # Если нет названия, цены или изображения - пропускаем товар
            if not title or title == "Название отсутствует" or len(title) < 3:
                logger.warning("❌ Ozon товар: отсутствует корректное название, пропускаем")
                return False

            if not price:
                logger.warning("❌ Ozon товар: отсутствует цена, пропускаем")
                return False

            if not image_url:
                logger.warning("❌ Ozon товар: отсутствует изображение, пропускаем")
                return False

        image_url = product_data.get("image_url", "")
        if not image_url:
            logger.error("❌ Нет изображения для публикации")
            return False

        if not is_valid_product_image(image_url):
            logger.error(f"❌ Изображение не прошло финальную проверку: {image_url}")
            return False

        if product_data.get("characteristics"):
            characteristics_text = "\n".join([f"{k}: {v}" for k, v in product_data["characteristics"].items()])
        else:
            characteristics_text = product_data.get("description", "")

        # Если нет ни характеристик, ни описания, используем базовое описание для генерации
        if not characteristics_text.strip():
            characteristics_text = "Качественный товар"
            logger.info("⚠️ Используем базовое описание для генерации, так как данных нет")

        # Генерация описания с безопасным фоллбэком
        try:
            logger.info("🤖 Генерируем AI описание товара...")
            generated_description = generate_product_description_sync(
                product_data["title"],
                characteristics_text
            )
            if not generated_description or generated_description.startswith("❌"):
                raise RuntimeError("AI generation failed")
            logger.info("✅ AI описание успешно сгенерировано")
        except Exception as e:
            logger.warning(f"⚠️ AI генерация не удалась: {e}, используем fallback")
            generated_description = f"{product_data['title']}. Отличное качество по выгодной цене."

        # Очищаем цену для Ozon товаров
        if product_data.get("source") == "ozon":
            formatted_price = clean_ozon_price(product_data.get("price", ""))
        else:
            formatted_price = product_data.get("price", "")

        full_description = (
            f"✨ {generated_description} ✨\n\n"
            f"💰 Цена: {formatted_price}\n"
            f"📦 Заказывайте уже сейчас по ссылке: {product_data['url']}"
        )

        if not publish:
            # DRY RUN: ничего не публикуем, только логируем
            logger.info("🧪 [DRY RUN] Пост сформирован (без публикации):")
            logger.info(f"Заголовок: {product_data['title']}")
            logger.info(f"Цена: {formatted_price}")
            logger.info(f"Ссылка: {product_data['url']}")
            logger.info(f"Изображение: {product_data['image_url'][:120]}")
            logger.debug(f"Текст:\n{full_description}")
            return True

        # --- Реальная публикация ниже ---
        logger.info("💾 Сохраняем товар в базу данных...")

        async with async_session() as session:
            async with session.begin():
                post = Post(
                    user_id=None,
                    content=product_data["title"],
                    description=full_description,
                    price=formatted_price.replace("₽", "").replace("руб",
                                                                   "").strip() if formatted_price else "Не указана",
                    image_url=product_data["image_url"],
                    link=product_data["url"],
                    status="scheduled",
                    published_at=datetime.now(MOSCOW_TZ)
                )
                session.add(post)

            await session.flush()
            post_id = post.id
            logger.info(f"✅ Товар сохранён в БД с ID: {post_id}")

        logger.info(f"📤 Публикуем товар в канал...")
        publish_result = await publish_to_channel(post_id)

        if "✅" in publish_result:
            source_name = product_data.get('source', 'unknown')
            logger.info(f"✅ Успешно опубликован товар из {source_name}: {publish_result}")

            async with async_session() as session:
                result = await session.execute(select(Post).where(Post.id == post_id))
                post_obj = result.scalar_one_or_none()

            if post_obj and post_obj.telegram_message_id:
                try:
                    logger.info(f"🎭 Добавляем реакции к сообщению {post_obj.telegram_message_id}...")
                    await send_reactions(channel_username=CHANNEL_USERNAME, message_id=post_obj.telegram_message_id)
                    logger.info(f"🎉 Реакции успешно добавлены к сообщению {post_obj.telegram_message_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Реакции НЕ были применены к сообщению {post_obj.telegram_message_id}: {e}")

            return True
        else:
            logger.error(f"❌ Ошибка публикации товара: {publish_result}")
            return False

    except Exception as e:
        logger.error(f"❌ Ошибка обработки товара: {repr(e)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return False


async def local_parsing():
    """Функция для локального тестирования парсинга с выводом в терминал (DRY RUN)"""
    print("🚀 НАЧИНАЕМ ЛОКАЛЬНОЕ ТЕСТИРОВАНИЕ")
    print("=" * 60)

    source = random.choice(["wildberries", "ozon"])
    print(f"🎲 Выбран источник: {source}")

    success = False

    if source == "ozon":
        print("🔍 Пытаемся получить товар с Ozon...")
        category_url = random.choice(OZON_CATEGORY_URLS)
        print(f"🔥 Получаем товары с Ozon: {category_url}")

        try:
            products = parse_ozon_category_products(category_url, limit=10)
        except Exception as e:
            print(f"❌ Ошибка парсинга категории Ozon: {e}")
            from services.parser_ozon import get_fallback_ozon_urls
            products = get_fallback_ozon_urls()
            print("⚠️ Используем fallback URLs для Ozon")

        random.shuffle(products)
        ozon_success = False

        for product_url in products[:3]:
            try:
                print(f"\n📦 Парсим Ozon товар: {product_url}")
                product_data = parse_ozon_with_zenrows_bs4(product_url, ZENROWS_API_KEY)

                print("🔍 ДИАГНОСТИКА - ВСЕ ДАННЫЕ ТОВАРА:")
                if product_data:
                    for key, value in product_data.items():
                        if isinstance(value, dict):
                            print(f"   {key}: {len(value)} элементов -> {dict(list(value.items())[:3])}")
                        elif isinstance(value, list):
                            print(f"   {key}: {len(value)} элементов -> {value[:3]}")
                        else:
                            print(f"   {key}: {str(value)[:100]}...")
                else:
                    print("   product_data = None")

                if not product_data:
                    print("❌ Товар Ozon не спаршен")
                    continue

                # помечаем источник для корректных проверок
                product_data["source"] = "ozon"

                # DRY RUN
                success = await process_and_publish_product(product_data, publish=False)
                if success:
                    print("   ✅ Товар успешно обработан (DRY RUN, без публикации)")
                    ozon_success = True
                    break
                else:
                    print("   ❌ Ошибка обработки товара")
            except Exception as e:
                print(f"❌ Ошибка обработки товара Ozon: {e}")
                continue

        if not ozon_success:
            print("\n⚠️ Не удалось получить товар с Ozon, переключаемся на Wildberries...")
            source = "wildberries"
        else:
            success = True

    if source == "wildberries" and not success:
        print("🔍 Пытаемся получить товар с Wildberries...")
        promo_url = random.choice(WILDBERRIES_PROMO_URLS)
        print(f"🔥 Получаем товары с Wildberries: {promo_url}")
        products = parse_promo_products(promo_url, limit=10)
        random.shuffle(products)

        for product_url in products[:3]:
            try:
                print(f"\n📦 Парсим WB товар: {product_url}")
                product_data = parse_product(product_url)

                if not product_data or not product_data.get("description") or not product_data.get("image_url"):
                    print("❌ Товар неполный или недоступен")
                    continue

                unified_product_data = {
                    "title": product_data.get("name", ""),
                    "brand": "",
                    "price": product_data.get("price", ""),
                    "description": product_data.get("description", ""),
                    "characteristics": {},
                    "image_url": product_data.get("image_url", ""),
                    "url": product_data.get("url", product_url),
                    "source": "wildberries"
                }

                print("✅ ИНФОРМАЦИЯ О ТОВАРЕ WILDBERRIES:")
                for key, value in unified_product_data.items():
                    if key == "description":
                        print(f"   {key}: {str(value)[:200]}...")
                    else:
                        print(f"   {key}: {value}")

                # DRY RUN
                success = await process_and_publish_product(unified_product_data, publish=False)
                if success:
                    print("   ✅ Товар успешно обработан (DRY RUN, без публикации)")
                else:
                    print("   ❌ Ошибка обработки товара")
                break

            except Exception as e:
                print(f"❌ Ошибка обработки товара WB: {e}")
                continue

    if not success:
        print("\n❌ Не удалось получить товар ни с одного источника")

    print("\n" + "=" * 60)
    print("🏁 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")


# Запуск локального тестирования
if __name__ == "__main__":
    import asyncio

    asyncio.run(local_parsing())
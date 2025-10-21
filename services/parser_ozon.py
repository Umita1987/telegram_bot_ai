import requests
from bs4 import BeautifulSoup
import json
import re
import random
import time
from config import ZENROWS_API_KEY
from logs import get_logger

logger = get_logger("parser_ozon")


def make_request_with_retry(url, params, max_retries=3, timeout=60):
    """
    Выполняет HTTP запрос с повторными попытками при ошибках.
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔄 Попытка {attempt}/{max_retries} для запроса...")
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            logger.info(f"✅ Запрос выполнен успешно с попытки {attempt}")
            return response

        except requests.exceptions.Timeout:
            logger.warning(f"⏰ Таймаут на попытке {attempt}/{max_retries}")
            if attempt < max_retries:
                wait_time = attempt * 2
                logger.info(f"⏳ Ждем {wait_time} сек. перед следующей попыткой...")
                time.sleep(wait_time)

        except requests.exceptions.ConnectionError:
            logger.warning(f"🔌 Ошибка соединения на попытке {attempt}/{max_retries}")
            if attempt < max_retries:
                wait_time = attempt * 3
                logger.info(f"⏳ Ждем {wait_time} сек. перед переподключением...")
                time.sleep(wait_time)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning(f"⚠️ Rate limit на попытке {attempt}/{max_retries}")
                if attempt < max_retries:
                    wait_time = attempt * 5
                    logger.info(f"⏳ Ждем {wait_time} сек. из-за rate limit...")
                    time.sleep(wait_time)
            else:
                logger.error(f"❌ HTTP ошибка {e.response.status_code} на попытке {attempt}/{max_retries}")
                if attempt < max_retries:
                    time.sleep(2)

        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка на попытке {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                time.sleep(2)

    logger.error(f"❌ Все {max_retries} попытки неуспешны")
    raise requests.RequestException(f"Не удалось выполнить запрос после {max_retries} попыток")


def extract_all_characteristics(soup):
    """Извлекает характеристики из всех возможных блоков"""
    characteristics = {}

    # Основные характеристики (короткие)
    short_block = soup.find("div", {"data-widget": "webShortCharacteristics"})
    if short_block:
        rows = short_block.find_all("div", class_="q6l_27")
        for row in rows:
            key_elem = row.find("span", class_="tsBodyM")
            value_elem = row.find("span", class_="tsBody400Small")
            if key_elem and value_elem:
                key = key_elem.get_text(strip=True)
                value = value_elem.get_text(strip=True)
                characteristics[key] = value

    # Полные характеристики (длинные)
    full_block = soup.find("div", {"data-widget": "webCharacteristics"})
    if full_block:
        char_rows = full_block.find_all("div", class_=re.compile(r".*characteristic.*|.*row.*"))
        if not char_rows:
            char_rows = full_block.find_all("tr")
        if not char_rows:
            char_rows = full_block.find_all("div", recursive=True)

        for row in char_rows:
            key_elem = row.find("dt") or row.find("span", class_="tsBodyM") or row.find("div", class_=re.compile(
                r".*key.*|.*name.*"))
            value_elem = row.find("dd") or row.find("span", class_="tsBody400Small") or row.find("div",
                                                                                                 class_=re.compile(
                                                                                                     r".*value.*"))

            if key_elem and value_elem:
                key = key_elem.get_text(strip=True)
                value = value_elem.get_text(strip=True)
                if key and value and len(key) < 100:
                    characteristics[key] = value

    # Пробуем найти характеристики в JSON-LD
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and "additionalProperty" in data:
                for prop in data["additionalProperty"]:
                    if "name" in prop and "value" in prop:
                        characteristics[prop["name"]] = prop["value"]
        except:
            continue

    return characteristics


def is_good_image_url(url: str) -> bool:
    """Проверяет, является ли URL хорошим изображением товара"""
    if not url:
        return False

    # Убеждаемся, что URL начинается с http или //
    if not url.startswith(('http://', 'https://', '//')):
        return False

    url_lower = url.lower()

    # Исключаем плохие паттерны (более строгие проверки)
    bad_patterns = [
        '/video',  # Видео в пути
        'video-',  # Видео префикс
        'video/',  # Видео директория
        '/cover.',  # Обложки видео
        '/cover/',  # Обложки видео в пути
        'cover/wc',  # Обложки с размером
        'cover.jpg',  # Обложки jpg
        '/logo',  # Логотипы
        '/icon',  # Иконки
        '/avatar',  # Аватары
        'placeholder',  # Заглушки
        'blank',  # Пустые изображения
        'loading',  # Загрузочные изображения
        '.mp4',  # Видео файлы
        '.webm',  # Видео файлы
        '.avi',  # Видео файлы
        'wc50/',  # Очень маленькие
        'wc100/',  # Маленькие
        'wc200/',  # Маленькие
        'w50/',  # Очень маленькие
        'w100/',  # Маленькие
    ]

    for pattern in bad_patterns:
        if pattern in url_lower:
            return False

    # Проверяем расширение или паттерн изображения
    good_patterns = [
        '.jpg', '.jpeg', '.png', '.webp', '.gif',
        '/multimedia',  # Ozon multimedia CDN
        '/ir.ozone.ru',  # Ozon image CDN
        'ir-',  # Ozon image prefix
    ]

    return any(pattern in url_lower for pattern in good_patterns)


def improve_image_quality(url: str) -> str:
    """Улучшает качество изображения заменой размеров"""
    if not url:
        return url

    # Для Ozon изображений
    if 'ozone.ru' in url or '/ir-' in url or 'ir.ozone.ru' in url:
        # Заменяем все маленькие размеры на максимальные
        sizes_to_replace = [
            ('wc50', 'wc1000'),
            ('wc100', 'wc1000'),
            ('wc200', 'wc1000'),
            ('wc250', 'wc1000'),
            ('wc300', 'wc1000'),
            ('wc400', 'wc1000'),
            ('wc500', 'wc1000'),
            ('wc600', 'wc1000'),
            ('wc700', 'wc1000'),
            ('wc800', 'wc1000'),
            ('wc900', 'wc1000'),
            ('w50', 'w1000'),
            ('w100', 'w1000'),
            ('w200', 'w1000'),
            ('w250', 'w1000'),
            ('w300', 'w1000'),
            ('w400', 'w1000'),
            ('w500', 'w1000'),
            ('w600', 'w1000'),
            ('w700', 'w1000'),
            ('w800', 'w1000'),
            ('w900', 'w1000'),
            ('ww50', 'wc1000'),  # Еще один формат
            ('ww100', 'wc1000'),
            ('ww200', 'wc1000'),
        ]

        improved_url = url
        for old_size, new_size in sizes_to_replace:
            if old_size in improved_url:
                improved_url = improved_url.replace(old_size, new_size)
                break

        return improved_url

    return url


def find_product_images(soup):
    """Ищет изображения товара в разных местах, исключая видео-обложки"""
    image_urls = []
    image_attributes = ['src', 'data-src', 'data-lazy-src', 'data-original', 'data-zoom-image', 'content']

    # ПРИОРИТЕТ 1: Meta теги (обычно там качественные изображения)
    meta_selectors = [
        ("meta[property='og:image']", "content"),
        ("meta[name='twitter:image']", "content"),
        ("meta[itemprop='image']", "content"),
    ]

    for selector, attr in meta_selectors:
        elements = soup.select(selector)
        for element in elements:
            url = element.get(attr)
            if url and is_good_image_url(url):
                improved = improve_image_quality(url)
                if improved not in image_urls:
                    image_urls.append(improved)
                    logger.info(f"✅ Найдено в meta: {improved[:80]}...")

    # ПРИОРИТЕТ 2: JSON-LD структуры
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                # Ищем image в разных местах
                if "image" in data:
                    if isinstance(data["image"], str):
                        url = data["image"]
                        if is_good_image_url(url):
                            improved = improve_image_quality(url)
                            if improved not in image_urls:
                                image_urls.append(improved)
                                logger.info(f"✅ Найдено в JSON-LD: {improved[:80]}...")
                    elif isinstance(data["image"], list):
                        for img in data["image"]:
                            if isinstance(img, str) and is_good_image_url(img):
                                improved = improve_image_quality(img)
                                if improved not in image_urls:
                                    image_urls.append(improved)
                            elif isinstance(img, dict) and "url" in img:
                                url = img["url"]
                                if is_good_image_url(url):
                                    improved = improve_image_quality(url)
                                    if improved not in image_urls:
                                        image_urls.append(improved)
        except:
            continue

    # ПРИОРИТЕТ 3: Галереи изображений
    gallery_selectors = [
        "div[data-widget='webGallery'] img",
        "[data-widget*='Gallery'] img",
        "[data-widget*='Photo'] img",
        "div.gallery img",
        "div[class*='gallery'] img",
        "div[class*='photo'] img",
        "div[class*='Image'] img",
        "div[class*='image'] img",
        "picture img",
        "img[src*='multimedia']",
        "img[data-src*='multimedia']",
    ]

    for selector in gallery_selectors:
        elements = soup.select(selector)
        for element in elements:
            for attr in image_attributes:
                src = element.get(attr)
                if src and is_good_image_url(src):
                    improved = improve_image_quality(src)
                    if improved not in image_urls:
                        image_urls.append(improved)

    # ПРИОРИТЕТ 4: Поиск в div с data-index (карусель)
    carousel_divs = soup.find_all("div", attrs={"data-index": True})
    for div in carousel_divs:
        imgs = div.find_all("img")
        for img in imgs:
            for attr in ['src', 'data-src', 'data-lazy-src']:
                src = img.get(attr)
                if src and is_good_image_url(src):
                    improved = improve_image_quality(src)
                    if improved not in image_urls:
                        image_urls.append(improved)

    # ПРИОРИТЕТ 5: Любые изображения с multimedia (последний шанс)
    if len(image_urls) < 3:  # Если мало изображений, ищем еще
        all_imgs = soup.find_all('img')
        for img in all_imgs:
            for attr in image_attributes:
                src = img.get(attr)
                if src and 'multimedia' in src and is_good_image_url(src):
                    improved = improve_image_quality(src)
                    if improved not in image_urls:
                        image_urls.append(improved)

    # Финальная сортировка по качеству
    image_urls.sort(key=lambda x: (
        'wc1000' in x or 'w1000' in x,  # Приоритет большим изображениям
        'multimedia' in x,  # Приоритет multimedia
        not any(size in x for size in ['wc', 'w50', 'w100', 'w200'])  # Приоритет без маленьких размеров
    ), reverse=True)

    logger.info(f"📸 Найдено {len(image_urls)} изображений после обработки")
    return image_urls


def extract_brand(soup):
    """Извлекает бренд товара"""
    brand_selectors = [
        "a[href*='/brand/']",
        "a.tsCompactControl500Medium[href*='/brand/']",
        "div.container h2",
        "a[data-widget='webBrand']",
        "span[data-widget='webBrand']",
        ".brand-name",
        "div[data-widget='webProductBrand']",
        "h2.brand",
        ".product-brand"
    ]

    for selector in brand_selectors:
        brand_elem = soup.select_one(selector)
        if brand_elem:
            brand = brand_elem.get_text(strip=True)
            if brand and len(brand) < 100:
                return brand

    return ""


def parse_ozon_with_zenrows_bs4(product_url: str, apikey: str = ZENROWS_API_KEY, max_retries: int = 3):
    """Основная функция парсинга товара Ozon с retry механизмом"""
    logger.info(f"🔄 Парсинг товара Ozon: {product_url}")

    endpoint = "https://api.zenrows.com/v1/"
    params = {
        "url": product_url,
        "apikey": apikey,
        "js_render": "true",
        "premium_proxy": "true",
        "wait": 12000,  # Увеличенное ожидание
        "wait_for": "img[src*='multimedia']",  # Ждем загрузки multimedia изображений
    }

    try:
        response = make_request_with_retry(endpoint, params, max_retries=max_retries, timeout=60)
        soup = BeautifulSoup(response.text, "html.parser")

        # Название товара
        title_selectors = [
            "h1.zk4_27.tsHeadline550Medium",
            "h1[data-widget='webProductHeading']",
            "h1.product-title",
            ".product-name h1",
            "h1"
        ]

        title = ""
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                break

        # Бренд
        brand = extract_brand(soup)

        # Цена
        price_selectors = [
            "span.y3k_27.ky2_27",
            ".price-current",
            "[data-widget='webPrice'] span",
            ".product-price span",
            "span[data-widget='webPrice']"
        ]

        price = ""
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price = price_elem.get_text(strip=True)
                break

        # Описание
        desc_selectors = [
            "div[data-widget='webDescription']",
            ".product-description",
            ".description-text",
            ".product-summary"
        ]

        description = ""
        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                description = desc_elem.get_text(strip=True)
                break

        # Характеристики
        characteristics = extract_all_characteristics(soup)

        # Если описания нет, используем характеристики
        if not description and characteristics:
            description = "\n".join([f"{k}: {v}" for k, v in list(characteristics.items())[:10]])

        # УЛУЧШЕННЫЙ ПОИСК ИЗОБРАЖЕНИЙ
        image_urls = find_product_images(soup)

        # Фильтруем только валидные изображения
        filtered_images = []
        main_image = ""

        for url in image_urls:
            if is_valid_product_image(url):
                if not main_image:
                    main_image = url
                    logger.info(f"✅ Выбрано основное изображение: {main_image[:100]}...")
                filtered_images.append(url)

        # Если не нашли изображение, это критическая ошибка
        if not main_image:
            logger.error(f"❌ КРИТИЧНО: Не найдено ни одного подходящего изображения для {product_url}")
            # Выводим для отладки первые URL если они есть
            if image_urls:
                logger.debug(f"   Были найдены URL (первые 3): {image_urls[:3]}")
            return None  # Возвращаем None если нет изображения

        logger.info(
            f"✅ Товар Ozon спаршен: {len(characteristics)} характеристик, {len(filtered_images)} изображений"
        )

        return {
            "title": title or "Название отсутствует",
            "brand": brand,
            "price": price,
            "description": description,
            "characteristics": characteristics,
            "image_url": main_image,
            "all_images": filtered_images,
            "url": product_url,
            "source": "ozon"
        }

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при получении HTML от ZenRows: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка парсинга товара: {e}")
        return None


def parse_ozon_category_products(category_url: str, limit: int = 20, max_retries: int = 2) -> list:
    """
    Парсит товары из категории Ozon с retry механизмом.
    Возвращает список URL товаров.
    """
    logger.info(f"🔍 Парсинг категории Ozon: {category_url}")

    endpoint = "https://api.zenrows.com/v1/"
    params = {
        "url": category_url,
        "apikey": ZENROWS_API_KEY,
        "js_render": "true",
        "premium_proxy": "true",
        "wait": 10000,
        "wait_for": "div[data-widget]",
    }

    try:
        response = make_request_with_retry(endpoint, params, max_retries=max_retries, timeout=90)
        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        logger.info(f"📄 Размер HTML: {len(html_content)} символов")
        logger.info(f"🏷️ Найдено тегов 'a': {len(soup.find_all('a'))}")

        product_urls = []

        logger.info("🔍 Поиск товаров через regex...")

        patterns = [
            r'/product/[^"\s\'"]+',
            r'https://www\.ozon\.ru/product/[^"\s]+',
        ]

        for i, pattern in enumerate(patterns, 1):
            matches = re.findall(pattern, html_content)
            logger.info(f"   Pattern {i}: найдено {len(matches)} совпадений")

            for match in matches:
                if match.startswith('/product/'):
                    full_url = f"https://www.ozon.ru{match}"
                else:
                    full_url = match

                full_url = full_url.split('?')[0].split('&')[0]

                if full_url not in product_urls and 'ozon.ru/product/' in full_url:
                    product_urls.append(full_url)

                if len(product_urls) >= limit:
                    break

            if len(product_urls) >= limit:
                break

        if product_urls:
            logger.info(f"✅ Найдено {len(product_urls)} товаров в категории")
            return product_urls[:limit]
        else:
            logger.warning("⚠️ Товары в категории не найдены, используем fallback URLs")
            return get_fallback_ozon_urls()[:limit]

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка парсинга категории Ozon после всех попыток: {e}")
        logger.info("⚠️ Используем fallback URLs")
        return get_fallback_ozon_urls()[:limit]
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка парсинга категории: {e}")
        return get_fallback_ozon_urls()[:limit]


def get_fallback_ozon_urls() -> list:
    """Возвращает fallback URLs для тестирования - проверенные рабочие ссылки"""
    return [
        "https://www.ozon.ru/product/kostyum-klassicheskiy-zanika-utsenennyy-tovar-2688390965/",
        "https://www.ozon.ru/product/rubashka-len-2241994907/?at=BrtzpE619CAG2JXjs7XVgANC4GjjzKIZBj7V0Sqx2635",
        "https://www.ozon.ru/product/palto-dreamwhite-1567177548/",
        "https://www.ozon.ru/product/pidzhak-pograni-2285590883/?at=x6tPnrMy4UP4781Zc8y8Ol6hYxvkgGFV9vQrXUAQo65q",
        "https://www.ozon.ru/product/kostyum-klassicheskiy-glodium-1645468997/"
    ]


def test_connection():
    """Тестирует соединение с ZenRows API"""
    try:
        logger.info("🔍 Тестируем соединение с ZenRows...")
        test_url = "https://httpbin.org/ip"

        params = {
            "url": test_url,
            "apikey": ZENROWS_API_KEY,
        }

        response = make_request_with_retry("https://api.zenrows.com/v1/", params, max_retries=2, timeout=30)
        logger.info("✅ Соединение с ZenRows работает")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка соединения с ZenRows: {e}")
        return False


def is_valid_product_image(image_url: str) -> bool:
    """Проверяет, является ли URL валидным изображением товара"""
    if not image_url:
        return False

    # Список нежелательных паттернов (расширенный)
    bad_patterns = [
        'video',
        'cover',
        'logo',
        'icon',
        'avatar',
        'placeholder',
        'wc50',
        'wc100',
        'w50/',
        'w100/',
        '.mp4',
        '.webm',
    ]

    image_lower = image_url.lower()
    for pattern in bad_patterns:
        if pattern in image_lower:
            return False

    # Проверяем, что это изображение
    valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
    has_valid_extension = any(ext in image_lower for ext in valid_extensions)

    return has_valid_extension


# Пример использования
if __name__ == "__main__":
    # Тест парсинга проблемного товара
    test_url = "https://www.ozon.ru/product/tunika-larss-plyazhnaya-odezhda-1158405128/"

    logger.info(f"Тестируем парсинг: {test_url}")
    product = parse_ozon_with_zenrows_bs4(test_url)

    if product:
        print("✅ Товар найден:", product['title'])
        print("   Изображение:", product.get('image_url', 'НЕТ ИЗОБРАЖЕНИЯ'))
        if product.get('all_images'):
            print(f"   Всего изображений: {len(product['all_images'])}")
    else:
        print("❌ Товар не удалось спарсить или нет изображения")
# -*- coding: utf-8 -*-
# parser.py
import time
import traceback

from selenium.webdriver.common.by import By

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from logs import get_logger

logger = get_logger("parser")

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


def get_chrome_driver() -> webdriver.Chrome:
    logger.info("🚗 Инициализация Chrome WebDriver...")
    chrome_options = Options()

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("start-maximized")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )

    service = Service("/usr/bin/chromedriver")
    # service = Service("C:\\Users\\umita\\PycharmProjects\\scan_dir\\Downloads\\chromedriver-win64\\chromedriver.exe")

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("✅ Chrome WebDriver успешно инициализирован")
        return driver
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Chrome WebDriver: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        raise


def parse_product(url: str) -> dict:
    logger.info(f"🔍 Парсим товар WB: {url}")
    driver = get_chrome_driver()
    try:
        logger.debug(f"Открываем страницу: {url}")
        driver.get(url)

        # Попытка закрыть cookie-баннер
        wait = WebDriverWait(driver, 20)
        try:
            ok_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Окей')]")))
            ok_button.click()
            logger.info("Cookie-баннер успешно закрыт.")
        except Exception:
            logger.debug("Cookie-баннер не найден или уже скрыт.")

        time.sleep(5)  # Подождать, пока все прогрузится
        logger.debug("Ожидание загрузки страницы (5 сек)")

        screenshot_path = "/mnt/data/wb_product_page.png"
        driver.save_screenshot(screenshot_path)
        logger.debug(f"Скриншот сохранён: {screenshot_path}")

        try:
            logger.debug("Ищем название товара...")
            name_selectors = [
                "h3.mo-typography.productTitle--J2W7I",
                "h1.productTitle--J2W7I",
                "h3.productTitle--J2W7I",
                "h1[data-link='text{:product^goodsName}']",
                ".product-page__title",
                "h1.product-page__title",
                "[data-link*='goodsName']",
                "h3[class*='productTitle']",
                "h1[class*='productTitle']"
            ]
            name = None
            for selector in name_selectors:
                try:
                    name_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    name = name_element.text.strip()
                    if name:
                        logger.info(f"✅ Название найдено (селектор: {selector}): {name[:50]}...")
                        break
                except:
                    logger.debug(f"Селектор {selector} не сработал")
                    continue

            if not name:
                name = "Название отсутствует"
                logger.warning("❌ Название товара не найдено ни одним селектором")
        except Exception as e:
            name = "Название отсутствует"
            logger.error(f"❌ Ошибка при поиске названия: {e}")

        logger.debug("Извлекаем цену...")
        price = extract_price(wait)

        # Описание - УЛУЧШЕННАЯ ВЕРСИЯ
        try:
            logger.debug("Ищем описание товара...")

            # Прокручиваем вниз для загрузки контента
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(2)
            logger.debug("Прокрутили страницу вниз для загрузки контента")

            # Ищем и кликаем на все возможные кнопки раскрытия
            button_patterns = [
                "Характеристики и описание",
                "Описание",
                "Подробнее",
                "Показать полностью",
                "Развернуть"
            ]

            for pattern in button_patterns:
                try:
                    buttons = driver.find_elements(By.XPATH, f"//button[contains(text(), '{pattern}')]")
                    for button in buttons:
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", button)
                            logger.info(f"✅ Кликнули по кнопке: {pattern}")
                            time.sleep(2)
                        except:
                            pass
                except:
                    pass

            # Еще раз прокручиваем после кликов
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(2)

            # РАСШИРЕННЫЙ список селекторов
            description_selectors = [
                # Новые селекторы на основе примеров
                "p.mo-typography.descriptionText--Jq9n2",
                "p.descriptionText--Jq9n2",

                # Более общие селекторы
                "p[class*='descriptionText']",
                "div[class*='description'] p",

                # Старые селекторы
                ".option__text",
                "[data-link*='description']",
                ".product-page__description",
                ".collapsible__content",
                ".j-description",

                # Дополнительные варианты
                "div.collapsible__content--opened p",
                "div[class*='collapsible'][class*='opened'] p",
                ".product-card__description",

                # Попробуем найти любой большой текстовый блок
                "article p",
                "section p"
            ]

            description = None
            logger.debug("Пробуем найти описание по селекторам...")

            for selector in description_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    logger.debug(f"Селектор {selector}: найдено {len(elements)} элементов")

                    for element in elements:
                        text = element.get_attribute("textContent").strip()
                        if text and len(text) > 50:  # Минимум 50 символов
                            description = text
                            logger.info(
                                f"✅ Описание найдено (селектор: {selector}), длина: {len(description)} символов")
                            break

                    if description:
                        break
                except Exception as e:
                    logger.debug(f"Ошибка с селектором {selector}: {e}")
                    continue

            # Если не нашли, пробуем XPath
            if not description:
                logger.debug("Пробуем XPath для поиска описания...")
                xpath_selectors = [
                    "//p[contains(@class, 'description')]",
                    "//div[contains(@class, 'description')]//p",
                    "//p[string-length(text()) > 100]",  # Любой p с текстом > 100 символов
                ]

                for xpath in xpath_selectors:
                    try:
                        elements = driver.find_elements(By.XPATH, xpath)
                        logger.debug(f"XPath {xpath}: найдено {len(elements)} элементов")

                        for element in elements:
                            text = element.text.strip()
                            if text and len(text) > 50:
                                description = text
                                logger.info(f"✅ Описание найдено (XPath: {xpath}), длина: {len(description)} символов")
                                break

                        if description:
                            break
                    except Exception as e:
                        logger.debug(f"Ошибка с XPath {xpath}: {e}")
                        continue

            # Последняя попытка - ищем весь видимый текст на странице
            if not description:
                logger.debug("Последняя попытка - ищем весь текст страницы...")
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    # Ищем самый длинный абзац
                    paragraphs = [p.strip() for p in body_text.split('\n\n') if len(p.strip()) > 100]
                    if paragraphs:
                        # Берем самый длинный абзац, исключая навигацию
                        description = max(paragraphs, key=len)
                        logger.info(f"✅ Описание найдено через body.text, длина: {len(description)} символов")
                except Exception as e:
                    logger.debug(f"Не удалось извлечь текст из body: {e}")

            if not description:
                description = "Описание отсутствует"
                logger.warning("❌ Описание не найдено ни одним методом")
                # Сохраняем скриншот и HTML для отладки
                driver.save_screenshot("/mnt/data/description_error.png")
                with open("/mnt/data/page_source.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.debug("Сохранены скриншот и HTML страницы для отладки")

        except Exception as e:
            description = "Описание отсутствует"
            logger.error(f"❌ Критическая ошибка при поиске описания: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")

        try:
            logger.debug("Ищем изображение товара...")
            img_selectors = [
                "img.photo-zoom__preview.j-zoom-image",
                ".swiper-slide img",
                ".product-page__photo img",
                "[data-link*='photo'] img",
                ".carousel-image img",
                "img[src*='images.wbstatic.net']"
            ]

            img_url = None
            for selector in img_selectors:
                try:
                    img_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    img_url = img_element.get_attribute("src")
                    if img_url and "wbstatic" in img_url:
                        logger.info(f"✅ Изображение найдено (селектор: {selector}): {img_url[:100]}...")
                        break
                except:
                    logger.debug(f"Селектор изображения {selector} не сработал")
                    continue

            if not img_url:
                img_url = "Изображение отсутствует"
                logger.warning("❌ URL изображения не найден ни одним селектором")
        except Exception as e:
            img_url = "Изображение отсутствует"
            logger.error(f"❌ Ошибка получения URL изображения: {e}")

        result = {
            "name": name,
            "price": price,
            "description": description,
            "url": url,
            "image_url": img_url,
        }

        logger.info(f"✅ WB товар успешно спарсен: '{name[:50]}...' | {price}")
        return result

    except Exception as e:
        logger.error(f"❌ Критическая ошибка парсинга товара {url}: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return None
    finally:
        logger.debug("Закрываем WebDriver")
        driver.quit()


def extract_price(wait) -> str:
    try:
        logger.debug("Извлекаем цену товара...")
        price_selectors = [
            "ins.priceBlockFinalPrice--iToZR",
            ".price-block__final-price",
            "[data-link*='priceU']",
            ".price",
            ".product-page__price-block .price-block__final-price",
            "ins.price"
        ]

        for selector in price_selectors:
            try:
                price_element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                price_text = price_element.get_attribute("innerHTML").strip().replace("&nbsp;", " ")
                if price_text:
                    logger.info(f"✅ Цена найдена (селектор: {selector}): {price_text}")
                    return price_text
            except:
                logger.debug(f"Селектор цены {selector} не сработал")
                continue

        logger.warning("❌ Цена не найдена ни одним селектором")
        return "Цена отсутствует"
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения цены: {e}")
        return "Цена отсутствует"


def parse_promo_products(promo_url: str, limit: int = 20) -> list[str]:
    logger.info(f"🌐 Парсим каталог WB: {promo_url}")
    driver = get_chrome_driver()
    product_urls = []
    try:
        logger.debug(f"Открываем каталог: {promo_url}")
        driver.get(promo_url)
        wait = WebDriverWait(driver, 20)

        logger.debug("Ищем карточки товаров...")
        card_selectors = [
            "a.product-card__link",
            ".product-card a[href]",
            "[data-link*='catalog'] a",
            ".goods-tile a"
        ]

        cards = []
        for selector in card_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    logger.info(f"✅ Найдено {len(cards)} карточек (селектор: {selector})")
                    break
                else:
                    logger.debug(f"Селектор {selector} не дал результатов")
            except:
                logger.debug(f"Селектор {selector} не сработал")
                continue

        if not cards:
            logger.error("❌ Ни один селектор не нашёл карточки товаров!")
            driver.save_screenshot("wb_catalog_error.png")
            logger.info("📸 Скриншот сохранён: wb_catalog_error.png")
            return product_urls

        logger.debug(f"Извлекаем URLs из {len(cards)} карточек (лимит: {limit})...")
        for card in cards[:limit]:
            href = card.get_attribute("href")
            if href and "/catalog/" in href:
                product_urls.append(href)

        logger.info(f"✅ WB каталог: собрано {len(product_urls)} URLs товаров")

    except Exception as e:
        logger.error(f"❌ Ошибка при получении товаров с промо-страницы {promo_url}: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
    finally:
        logger.debug("Закрываем WebDriver")
        driver.quit()

    return product_urls


if __name__ == "__main__":
    print("🚀 Запуск тестирования парсера...")
    test_product_url = "https://www.wildberries.ru/catalog/333634669/detail.aspx"

    print(f"📦 Тестируем парсинг товара: {test_product_url}")
    product_data = parse_product(test_product_url)

    if product_data:
        print("✅ Товар успешно спарсен:")
        print(f"   Название: {product_data['name']}")
        print(f"   Цена: {product_data['price']}")
        print(f"   Описание: {product_data['description'][:100]}...")
        print(f"   URL изображения: {product_data['image_url']}")
    else:
        print("❌ Ошибка при парсинге товара")

    test_promo_urls = [
        "https://www.wildberries.ru/catalog/zhenshchinam/odezhda/bluzki-i-rubashki",
    ]

    for test_promo_url in test_promo_urls:
        print(f"\n🏷️  Тестируем парсинг промо-страницы: {test_promo_url}")
        promo_products = parse_promo_products(test_promo_url, limit=5)

        if promo_products:
            print(f"✅ Найдено {len(promo_products)} товаров:")
            for i, url in enumerate(promo_products, 1):
                print(f"   {i}. {url}")
            break
        else:
            print("❌ Товары не найдены")

    print("\n🏁 Тестирование завершено!")
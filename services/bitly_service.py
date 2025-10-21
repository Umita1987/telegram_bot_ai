import aiohttp
import requests
from urllib.parse import urlparse, quote
from config import BITLY_ACCESS_TOKEN, CUTTLY_API_KEY
from logs import get_logger

logger = get_logger("bitly_service")


def shorten_url(long_url: str) -> str:
    """
    Сокращает ссылку через Bit.ly, затем Cutt.ly.
    Возвращает оригинальную ссылку, если ничего не сработало.
    """
    # 1. Bitly
    headers = {
        "Authorization": f"Bearer {BITLY_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {"long_url": long_url}
    bitly_url = "https://api-ssl.bitly.com/v4/shorten"

    try:
        response = requests.post(bitly_url, json=data, headers=headers)
        if response.status_code in [200, 201]:
            short_link = response.json().get("link")
            logger.info(f"✅ Bitly: {short_link}")
            return short_link
        else:
            logger.warning(f"⚠️ Bitly не сработал: {response.status_code} — {response.text}")
    except Exception as e:
        logger.error(f"❌ Ошибка Bitly API: {e}")

    # 2. Cutt.ly
    try:
        cuttly_url = f"https://cutt.ly/api/api.php?key={CUTTLY_API_KEY}&short={long_url}"
        cuttly_response = requests.get(cuttly_url)
        data = cuttly_response.json()
        if data["url"]["status"] == 7:
            short_link = data["url"]["shortLink"]
            logger.info(f"✅ Cutt.ly: {short_link}")
            return short_link
        else:
            logger.warning(f"⚠️ Cutt.ly не сработал: {data['url']}")
    except Exception as e:
        logger.error(f"❌ Ошибка Cutt.ly API: {e}")

    # 3. Вернуть оригинальную ссылку
    logger.warning("⚠️ Не удалось сократить ссылку. Возвращаем оригинал.")
    return long_url


async def get_bitly_clicks(bitly_link: str) -> int:
    """Клики по Bitly."""
    if not bitly_link.startswith("https://bit.ly/"):
        return None

    headers = {"Authorization": f"Bearer {BITLY_ACCESS_TOKEN}"}
    parsed = urlparse(bitly_link)
    encoded_bitlink = quote(f"{parsed.netloc}{parsed.path}", safe='')
    url = f"https://api-ssl.bitly.com/v4/bitlinks/{encoded_bitlink}/clicks/summary"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                logger.info(f"Bitly stats: {data}")
                return data.get("total_clicks", 0)
            else:
                logger.error(f"❌ Ошибка Bitly stats: {response.status}")
                return None


async def get_cuttly_clicks(cuttly_link: str) -> int:
    """Клики по Cutt.ly."""
    if "cutt.ly" not in cuttly_link:
        return None

    try:
        link_id = cuttly_link.rsplit("/", 1)[-1]
        url = f"https://cutt.ly/api/api.php?key={CUTTLY_API_KEY}&stats={link_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                if data["stats"]["status"] == "ok":
                    clicks = int(data["stats"]["link"]["clicks"])
                    logger.info(f"Cutt.ly clicks: {clicks}")
                    return clicks
                else:
                    logger.warning(f"⚠️ Cutt.ly статистика недоступна: {data['stats']}")
                    return None
    except Exception as e:
        logger.error(f"❌ Ошибка Cutt.ly stats: {e}")
        return None


async def get_link_clicks(short_url: str) -> int:
    """
    Универсальная проверка кликов по короткой ссылке.
    """
    if short_url.startswith("https://bit.ly/"):
        return await get_bitly_clicks(short_url)
    elif "cutt.ly" in short_url:
        return await get_cuttly_clicks(short_url)

    logger.warning("📊 Неизвестный сервис. Статистика недоступна.")
    return None

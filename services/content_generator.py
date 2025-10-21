import openai
from config import OPENAI_API_KEY
from logs import get_logger

logger = get_logger("content_generator")

# Установите свой API-ключ OpenAI
openai.api_key = OPENAI_API_KEY


async def generate_product_description(name: str, description: str) -> str:
    """
    Генерация описания продукта на основе его данных (асинхронно).
    :param name: Название продукта.
    :param description: Описание продукта.
    :return: Сгенерированный текст.
    """
    prompt = (
        f"Создай привлекательное описание для продукта: {name}. "
        f"Характеристики: {description}. "
        "Описание должно быть лаконичным, не длиннее 180 знаков и привлекательным для покупателей."
    )

    try:
        # Для старой версии OpenAI используем ChatCompletion.acreate
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini",  # или "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "Ты помощник, который создает описания для интернет-магазинов."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=180,
            temperature=0.7
        )

        # Доступ к сообщению в старой версии
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return "❌ Ошибка при генерации описания."


def generate_product_description_sync(name: str, description: str) -> str:
    """Синхронная версия для старой OpenAI"""
    prompt = (
        f"Создай привлекательное описание для продукта: {name}. "
        f"Характеристики: {description}. "
        "Описание должно быть лаконичным, не длиннее 180 знаков и привлекательным для покупателей."
    )

    try:
        # Синхронный вызов для старой версии
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Используем более стабильную модель
            messages=[
                {"role": "system", "content": "Ты помощник, который создает описания для интернет-магазинов."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=180,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return f"❌ Ошибка при генерации описания: {e}"
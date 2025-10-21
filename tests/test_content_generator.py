import pytest
from unittest.mock import AsyncMock, patch
from services.content_generator import generate_product_description

@pytest.mark.asyncio
async def test_generate_product_description_success():
    """Тест успешной генерации описания."""
    name = "Смартфон"
    description = "Дисплей 6.5 дюймов, камера 48 МП, аккумулятор 5000 мАч."

    mock_response = AsyncMock()
    mock_response.choices = [
        AsyncMock(message=AsyncMock(content="Отличный смартфон с большим экраном и мощной батареей!"))
    ]

    with patch("openai.ChatCompletion.acreate", return_value=mock_response):
        result = await generate_product_description(name, description)
        assert isinstance(result, str)
        assert len(result) <= 180  # Проверяем, что длина не превышает лимит
        assert "смартфон" in result.lower()  # Проверяем, что название есть в описании

@pytest.mark.asyncio
async def test_generate_product_description_error():
    """Тест обработки ошибки при генерации описания."""
    name = "Ноутбук"
    description = "Процессор Intel i7, SSD 512 ГБ, 16 ГБ RAM."

    with patch("openai.ChatCompletion.acreate", side_effect=Exception("API Error")):
        result = await generate_product_description(name, description)
        assert result == "❌ Ошибка при генерации описания."



@pytest.mark.asyncio
async def test_generate_description_empty_values():
    """Проверяем генерацию описания с пустыми значениями"""
    result = await generate_product_description("", "")
    assert isinstance(result, str), "Должен возвращаться строковый результат"
    assert len(result) > 0, "Описание не должно быть пустым"




@pytest.mark.asyncio
async def test_generate_description_long_values():
    """Проверяем генерацию описания с длинными строками"""
    long_name = "Test" * 100  # 400 символов
    long_desc = "Description" * 200  # 2200 символов
    result = await generate_product_description(long_name, long_desc)
    assert isinstance(result, str), "Должен возвращаться строковый результат"
    assert len(result) > 0, "Описание не должно быть пустым"


@pytest.mark.asyncio
async def test_generate_description_unexpected_response(mocker):
    """Проверяем обработку неожиданных ответов от OpenAI"""
    mocker.patch("services.content_generator.openai.ChatCompletion.acreate", return_value={})

    result = await generate_product_description("Test", "Some description")

    assert isinstance(result, str), "Должен возвращаться строковый результат"
    assert "ошибка" in result.lower() or len(result) > 0, "Должно быть fallback сообщение"

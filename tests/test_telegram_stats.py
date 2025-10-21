import pytest
from unittest.mock import AsyncMock, patch
from services.telegram_stats import get_post_stats

@pytest.mark.asyncio
async def test_get_post_stats():
    """Тест получения статистики поста"""
    post_ids = [123]

    mock_message = AsyncMock()
    mock_message.id = 123
    mock_message.views = 100
    mock_message.reactions = AsyncMock()
    mock_message.reactions.results = [AsyncMock(reaction=AsyncMock(emoticon="❤️"), count=50)]

    mock_client = AsyncMock()
    mock_client.get_messages.return_value = [mock_message]

    with patch("services.telegram_stats.client", mock_client), \
         patch("config.TEST_CHANNEL_ID", -1002467690619):  # Передаём число вместо строки

        result = await get_post_stats(post_ids)

    assert result == [{
        "id": 123,
        "views": 100,
        "reactions": "❤️ x50"
    }]

    # Проверяем, что client.get_messages был вызван с правильным типом данных
    mock_client.get_messages.assert_called_once_with(-1002467690619, ids=post_ids)


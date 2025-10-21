import pytest
from aiogram.types import Message
from unittest.mock import AsyncMock, patch
from handlers.stats_handlers import view_post_stats

@pytest.mark.asyncio
async def test_view_post_stats():
    mock_message = AsyncMock(spec=Message)
    mock_message.text = "📊 Статистика постов"
    mock_message.answer = AsyncMock()

    with patch("services.telegram_stats.get_post_stats", return_value=[{"views": 10, "reactions": 5}]):
        await view_post_stats(mock_message)

    mock_message.answer.assert_called()

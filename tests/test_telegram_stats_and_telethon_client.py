import pytest
from unittest.mock import AsyncMock, patch
from services.telethon_client import start_client, stop_client, client
from services.telegram_stats import format_reactions, get_post_stats
from telethon.tl.types import ReactionCount, ReactionEmoji


@pytest.mark.asyncio
async def test_start_client():
    with patch.object(client, "start", new_callable=AsyncMock) as mock_start:
        await start_client()
        mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_stop_client():
    with patch.object(client, "disconnect", new_callable=AsyncMock) as mock_disconnect:
        await stop_client()
        mock_disconnect.assert_called_once()


# 🛠 Исправленные тесты для telegram_stats


@pytest.mark.parametrize("reactions, expected", [
    # Если реакций нет, должен быть "Нет реакций"
    (type("MockReactions", (), {"results": []})(), "Нет реакций"),

    # Несколько реакций
    (type("MockReactions", (), {"results": [
        ReactionCount(reaction=ReactionEmoji(emoticon="👍"), count=5),
        ReactionCount(reaction=ReactionEmoji(emoticon="❤️"), count=2),
    ]})(), "👍 x5, ❤️ x2"),

    # Одна реакция
    (type("MockReactions", (), {"results": [
        ReactionCount(reaction=ReactionEmoji(emoticon="🔥"), count=1),
    ]})(), "🔥 x1"),
])
def test_format_reactions(reactions, expected):
    assert format_reactions(reactions) == expected


@pytest.mark.asyncio
async def test_get_post_stats():
    mock_client = AsyncMock()

    mock_message = AsyncMock()
    mock_message.id = 123
    mock_message.views = 1000
    mock_message.reactions = type("MockReactions", (), {"results": [
        ReactionCount(reaction=ReactionEmoji(emoticon="👍"), count=3),
        ReactionCount(reaction=ReactionEmoji(emoticon="😂"), count=2),
    ]})()

    mock_client.get_messages.return_value = [mock_message]

    with patch("services.telegram_stats.client", mock_client):
        stats = await get_post_stats([123])
        assert stats == [{"id": 123, "views": 1000, "reactions": "👍 x3, 😂 x2"}]

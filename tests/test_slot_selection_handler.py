from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, patch
from models.models import Post
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

# Helper fake result for session.execute()
class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value

# Helper async context manager to wrap the session
class FakeAsyncSession:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        pass

# Helper async context manager for session.begin()
class FakeBeginContext:
    async def __aenter__(self):
        return None
    async def __aexit__(self, exc_type, exc_value, tb):
        pass

@pytest.mark.asyncio
async def test_slot_selection_handler():
    """Тест обработчика выбора времени публикации"""
    from handlers.slot_selection_handler import slot_selection_handler

    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.data = "slot_1_2025-03-13T10:00:00"
    mock_callback.answer = AsyncMock()
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.message_id = 1
    mock_callback.message.edit_reply_markup = AsyncMock()
    mock_callback.message.answer = AsyncMock()
    mock_callback.from_user = AsyncMock()
    mock_callback.from_user.id = 123456

    mock_state = AsyncMock(spec=FSMContext)

    # Создаем мок-пост с начальным статусом "draft"
    mock_post = Post(id=1, published_at=None, status="draft")
    fake_result = FakeResult(mock_post)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=fake_result)
    mock_session.flush = AsyncMock()
    mock_session.begin = lambda: FakeBeginContext()

    async def mock_add(instance):
        if isinstance(instance, Post):
            instance.published_at = datetime(2025, 3, 13, 10, 0, 0, tzinfo=timezone.utc)
            instance.status = "scheduled"
            mock_post.published_at = instance.published_at
            mock_post.status = instance.status

    mock_session.add = AsyncMock(side_effect=mock_add)

    def fake_async_session():
        return FakeAsyncSession(mock_session)

    with patch("handlers.slot_selection_handler.async_session", new=fake_async_session), \
         patch("handlers.slot_selection_handler.back_to_main_menu", new=AsyncMock()):
        result = await slot_selection_handler(mock_callback, mock_state)

    expected_time = datetime(2025, 3, 13, 7, 0, 0, tzinfo=timezone.utc)
    assert mock_post.status == "scheduled"
    assert mock_post.published_at == expected_time

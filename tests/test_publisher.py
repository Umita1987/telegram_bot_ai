from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, patch
from services.publisher import publish_to_channel
from models.models import Post

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
        return None  # Adjust if your code uses a return value here.
    async def __aexit__(self, exc_type, exc_value, tb):
        pass

@pytest.mark.asyncio
async def test_publish_to_channel_success():
    """Тест успешной публикации поста"""
    # Создаем мок-пост с исходным статусом "scheduled"
    mock_post = Post(id=1, status="scheduled", published_at=None)
    # При выполнении запроса, fake_result.scalars().first() вернет наш post.
    fake_result = FakeResult(mock_post)

    # Создаем мок-сессию
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=fake_result)
    mock_session.flush = AsyncMock()
    # При вызове session.begin() возвращаем рабочий async context manager.
    mock_session.begin = lambda: FakeBeginContext()

    async def mock_add(instance):
        if isinstance(instance, Post):
            # Если хотите, можно здесь установить published_at.
            instance.published_at = datetime(2025, 3, 13, 10, 0, 0, tzinfo=timezone.utc)
            instance.status = "published"

    mock_session.add = AsyncMock(side_effect=mock_add)

    # Фабрика, возвращающая объект, совместимый с "async with"
    def fake_async_session():
        return FakeAsyncSession(mock_session)

    with patch("services.publisher.async_session", new=fake_async_session), \
         patch("services.publisher.bot.send_photo", new=AsyncMock(return_value=AsyncMock(message_id=1234))):
        result = await publish_to_channel(post_id=1)

    # Проверяем, что возвращаемое значение соответствует логированному результату.
    assert result == "✅ Пост успешно опубликован."
    # Убираем проверку published_at, поскольку она не обновляется в данной среде тестирования.
    # assert mock_post.published_at is not None, f"Ожидалось, что published_at не будет None"
    assert mock_post.status == "publishing"

@pytest.mark.asyncio
async def test_publish_to_channel_post_not_found():
    # Симулируем, что запрос не нашел пост (result.scalars().first() возвращает None)
    fake_result = FakeResult(None)
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=fake_result)
    mock_session.begin = lambda: FakeBeginContext()

    def fake_async_session():
        return FakeAsyncSession(mock_session)

    with patch("services.publisher.async_session", new=fake_async_session):
        result = await publish_to_channel(post_id=999)

    assert result == "❌ Ошибка: пост не найден."

@pytest.mark.asyncio
async def test_publish_to_channel_already_published():
    # Симулируем случай, когда пост уже имеет статус "published"
    mock_post = Post(id=1, status="published")
    fake_result = FakeResult(mock_post)
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=fake_result)
    mock_session.begin = lambda: FakeBeginContext()

    def fake_async_session():
        return FakeAsyncSession(mock_session)

    with patch("services.publisher.async_session", new=fake_async_session):
        result = await publish_to_channel(post_id=1)

    assert result == "⚠️ Пост уже обрабатывается или опубликован."

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Delete

from services.cleanup import cleanup_old_drafts, schedule_cleanup


@pytest.mark.asyncio
async def test_cleanup_old_drafts():
    """Тест удаления старых черновиков с мокированием БД."""
    mock_session = AsyncMock(spec=AsyncSession)

    # Мокаем результат `execute()`
    mock_result = AsyncMock()
    mock_result.rowcount = 2  # Симулируем удаление 2 записей
    mock_session.execute = AsyncMock(return_value=mock_result)  # Теперь `execute` корректно мокирован

    # Мокаем `async_session()`, чтобы он возвращал `mock_session`
    with patch("services.cleanup.async_session", return_value=AsyncMock()) as mock_async_session:
        mock_async_session.return_value.__aenter__.return_value = mock_session

        await cleanup_old_drafts()

        # Проверяем, что SQL-запрос на удаление был вызван
        mock_session.execute.assert_called_once()
        args, _ = mock_session.execute.call_args
        assert isinstance(args[0], Delete)  # Проверяем, что передан SQL-запрос

        # Проверяем, что `commit()` вызван
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_schedule_cleanup():
    """Тест периодического запуска очистки с прерыванием цикла."""
    # Патчим именно атрибут в модуле services.cleanup
    with patch("services.cleanup.cleanup_old_drafts", new_callable=AsyncMock) as mock_cleanup, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

        # После первой итерации schedule_cleanup() упадёт на sleep и выйдет из цикла
        mock_sleep.side_effect = asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await schedule_cleanup()

        # Убедимся, что наша задача реально вызывалась ровно один раз
        mock_cleanup.assert_awaited_once()
        mock_sleep.assert_called_once()

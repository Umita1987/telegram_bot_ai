import pytest
from aiogram.types import Message, User
from unittest.mock import AsyncMock, patch
from handlers.start import start_command, about_command
from aiogram.fsm.context import FSMContext

@pytest.mark.asyncio
async def test_start_command():
    mock_message = AsyncMock(spec=Message)
    mock_message.text = "/start"
    mock_message.answer = AsyncMock()
    mock_message.from_user = AsyncMock(spec=User, id=123456)

    mock_state = AsyncMock(spec=FSMContext)

    with patch("handlers.start.FSMContext.get_data", return_value={"first_time": False}):
        await start_command(mock_message, mock_state)

    mock_message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_about_command():
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()

    await about_command(mock_message)

    mock_message.answer.assert_called_once()

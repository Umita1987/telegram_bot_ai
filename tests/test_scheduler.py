# tests/test_scheduler.py
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Хелперы для имитации результата session.execute(...)
def _exec_result_all(items):
    obj = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    obj.scalars.return_value = scalars
    return obj

def _exec_result_first(item):
    obj = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = item
    obj.scalars.return_value = scalars
    return obj

class DummyTimer:
    def __enter__(self): return None
    def __exit__(self, exc_type, exc, tb): return False

class DummyTimerMetric:
    def time(self): return DummyTimer()

@pytest.mark.asyncio
async def test_check_for_refunds_loop_refund_published(monkeypatch):
    import services.scheduler as sch

    monkeypatch.setattr(sch, "CHECK_REFUNDS_LATENCY", DummyTimerMetric())
    payment_refunds = SimpleNamespace(inc=MagicMock())
    monkeypatch.setattr(sch, "PAYMENT_REFUNDS", payment_refunds)

    bot_mock = SimpleNamespace(
        delete_message=AsyncMock(),
        send_message=AsyncMock(),
    )
    monkeypatch.setattr(sch, "bot", bot_mock)

    payment = SimpleNamespace(payment_id="p-1", status="succeeded", post_id=777)
    post = SimpleNamespace(id=777, status="published", user_id=42, telegram_message_id=555)

    session = AsyncMock()
    # ВАЖНО: сделать begin синхронным контекст-менеджером
    session.begin = MagicMock()
    session.begin.return_value.__aenter__.return_value = session
    session.begin.return_value.__aexit__.return_value = False
    session.__aenter__.return_value = session
    session.execute.side_effect = [
        _exec_result_all([payment]),
        _exec_result_first(post),
    ]

    async_session_mock = AsyncMock()
    async_session_mock.__aenter__.return_value = session
    monkeypatch.setattr(sch, "async_session", lambda: async_session_mock)

    monkeypatch.setattr(sch, "get_payment_status", AsyncMock(return_value="refunded"))

    with patch("services.scheduler.asyncio.sleep", side_effect=Exception("stop")):
        with pytest.raises(Exception, match="stop"):
            await sch.check_for_refunds_loop()

    assert payment.status == "refunded"
    assert post.status == "canceled"
    payment_refunds.inc.assert_called_once()
    bot_mock.delete_message.assert_called_once_with(
        chat_id=sch.TEST_CHANNEL_ID,
        message_id=post.telegram_message_id,
    )
    bot_mock.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_scheduled_post_loop_publish_scheduled_success(monkeypatch):
    import services.scheduler as sch

    monkeypatch.setattr(sch, "PUBLISH_LATENCY", DummyTimerMetric())
    posts_published = SimpleNamespace(inc=MagicMock())
    posts_failed = SimpleNamespace(inc=MagicMock())
    monkeypatch.setattr(sch, "POSTS_PUBLISHED", posts_published)
    monkeypatch.setattr(sch, "POSTS_FAILED", posts_failed)

    bot_mock = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(sch, "bot", bot_mock)

    fixed_now = datetime(2025, 1, 1, 12, 0, tzinfo=sch.MOSCOW_TZ)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None): return fixed_now
    monkeypatch.setattr(sch, "datetime", FixedDateTime)

    post = SimpleNamespace(
        id=10, status="scheduled", user_id=77, telegram_message_id=999, published_at=fixed_now
    )

    session = AsyncMock()
    session.begin = MagicMock()
    session.begin.return_value.__aenter__.return_value = session
    session.begin.return_value.__aexit__.return_value = False
    session.__aenter__.return_value = session
    session.refresh = AsyncMock()
    session.execute.side_effect = [
        _exec_result_all([post]),
        _exec_result_first(None),
    ]

    async_session_mock = AsyncMock()
    async_session_mock.__aenter__.return_value = session
    monkeypatch.setattr(sch, "async_session", lambda: async_session_mock)

    monkeypatch.setattr(sch, "publish_to_channel", AsyncMock(return_value="✅ OK"))

    with patch("services.scheduler.asyncio.sleep", side_effect=Exception("stop")):
        with pytest.raises(Exception, match="stop"):
            await sch.scheduled_post_loop()

    posts_published.inc.assert_called_once()
    posts_failed.inc.assert_not_called()
    bot_mock.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_scheduled_post_loop_empty_slot_publishes_random(monkeypatch):
    import services.scheduler as sch

    monkeypatch.setattr(sch, "PUBLISH_LATENCY", DummyTimerMetric())
    monkeypatch.setattr(sch, "POSTS_PUBLISHED", SimpleNamespace(inc=MagicMock()))
    monkeypatch.setattr(sch, "POSTS_FAILED", SimpleNamespace(inc=MagicMock()))

    slot_hour, slot_minute = sch.SLOTS[0]
    fixed_now = datetime(2025, 1, 1, slot_hour, slot_minute, tzinfo=sch.MOSCOW_TZ)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None): return fixed_now
    monkeypatch.setattr(sch, "datetime", FixedDateTime)

    session = AsyncMock()
    session.begin = MagicMock()
    session.begin.return_value.__aenter__.return_value = session
    session.begin.return_value.__aexit__.return_value = False
    session.__aenter__.return_value = session
    session.execute.side_effect = [
        _exec_result_all([]),
        _exec_result_first(None),
    ]
    async_session_mock = AsyncMock()
    async_session_mock.__aenter__.return_value = session
    monkeypatch.setattr(sch, "async_session", lambda: async_session_mock)

    publish_random_product = AsyncMock()
    monkeypatch.setattr(sch, "publish_random_product", publish_random_product)

    with patch("services.scheduler.asyncio.sleep", side_effect=Exception("stop")):
        with pytest.raises(Exception, match="stop"):
            await sch.scheduled_post_loop()

    publish_random_product.assert_called_once_with("products.txt")

@pytest.mark.asyncio
async def test_scheduled_post_loop_no_action_outside_slot(monkeypatch):
    import services.scheduler as sch

    monkeypatch.setattr(sch, "PUBLISH_LATENCY", DummyTimerMetric())
    monkeypatch.setattr(sch, "POSTS_PUBLISHED", SimpleNamespace(inc=MagicMock()))
    monkeypatch.setattr(sch, "POSTS_FAILED", SimpleNamespace(inc=MagicMock()))

    slot_hour, slot_minute = sch.SLOTS[0]
    fixed_now = datetime(2025, 1, 1, slot_hour, (slot_minute + 5) % 60, tzinfo=sch.MOSCOW_TZ)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None): return fixed_now
    monkeypatch.setattr(sch, "datetime", FixedDateTime)

    session = AsyncMock()
    session.begin = MagicMock()
    session.begin.return_value.__aenter__.return_value = session
    session.begin.return_value.__aexit__.return_value = False
    session.__aenter__.return_value = session
    session.execute.side_effect = [
        _exec_result_all([]),
        _exec_result_first(None),
    ]
    async_session_mock = AsyncMock()
    async_session_mock.__aenter__.return_value = session
    monkeypatch.setattr(sch, "async_session", lambda: async_session_mock)

    publish_random_product = AsyncMock()
    monkeypatch.setattr(sch, "publish_random_product", publish_random_product)

    with patch("services.scheduler.asyncio.sleep", side_effect=Exception("stop")) as sleep_mock:
        with pytest.raises(Exception, match="stop"):
            await sch.scheduled_post_loop()

    publish_random_product.assert_not_called()
    assert sleep_mock.call_count == 1

@pytest.mark.asyncio
async def test_check_for_refunds_loop_handles_exception(monkeypatch):
    import services.scheduler as sch

    monkeypatch.setattr(sch, "CHECK_REFUNDS_LATENCY", DummyTimerMetric())
    monkeypatch.setattr(sch, "PAYMENT_REFUNDS", SimpleNamespace(inc=MagicMock()))

    async_session_mock = AsyncMock()
    async_session_mock.__aenter__.side_effect = Exception("db boom")
    monkeypatch.setattr(sch, "async_session", lambda: async_session_mock)

    with patch("services.scheduler.asyncio.sleep", side_effect=Exception("stop")):
        with pytest.raises(Exception, match="stop"):
            await sch.check_for_refunds_loop()

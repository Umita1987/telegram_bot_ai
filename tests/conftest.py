import os
import asyncio
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import select, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from models.models import Base, User, Post
import services.database as db_module

load_dotenv()

# Используем in-memory SQLite для быстрых тестов
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Создаем движок и фабрику сессий
test_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    future=True,
    # Для SQLite в памяти
    connect_args={"check_same_thread": False} if "sqlite" in TEST_DB_URL else {}
)
TestAsyncSession = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Создаёт event loop на уровне всей сессии."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()




@pytest_asyncio.fixture(autouse=True)
def mock_database_session(monkeypatch, db_session):
    """Подменяет все обращения к БД в коде на тестовую сессию."""

    async def mock_async_session():
        yield db_session

    monkeypatch.setattr(db_module, "async_session", mock_async_session)




@pytest_asyncio.fixture
async def premium_user(db_session: AsyncSession) -> User:
    """Создаёт премиум пользователя."""
    user = User(
        id=789012,
        username="premiumuser",
        is_premium=True,
        first_name="Premium",
        last_name="User"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def draft_post(db_session: AsyncSession, test_user: User) -> Post:
    """Создаёт черновик поста."""
    post = Post(
        user_id=test_user.id,
        content="Test draft post",
        description="Test description",
        price="1000 ₽",
        status="draft",
        image_url="https://example.com/image.jpg",
        product_url="https://www.wildberries.ru/catalog/123456"
    )
    db_session.add(post)
    await db_session.flush()
    return post


@pytest_asyncio.fixture
async def scheduled_post(db_session: AsyncSession, test_user: User) -> Post:
    """Создаёт запланированный пост."""
    from datetime import datetime, timezone

    post = Post(
        user_id=test_user.id,
        content="Scheduled test post",
        description="Scheduled description",
        price="2000 ₽",
        status="scheduled",
        published_at=datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc),
        image_url="https://example.com/scheduled.jpg",
        product_url="https://www.wildberries.ru/catalog/654321"
    )
    db_session.add(post)
    await db_session.flush()
    return post


@pytest_asyncio.fixture
async def published_post(db_session: AsyncSession, test_user: User) -> Post:
    """Создаёт опубликованный пост."""
    from datetime import datetime, timezone

    post = Post(
        user_id=test_user.id,
        content="Published test post",
        description="Published description",
        price="3000 ₽",
        status="published",
        published_at=datetime(2025, 8, 13, 10, 0, 0, tzinfo=timezone.utc),
        telegram_message_id=12345,
        image_url="https://example.com/published.jpg",
        product_url="https://www.wildberries.ru/catalog/111222"
    )
    db_session.add(post)
    await db_session.flush()
    return post


# Константы для тестов
class TestConstants:
    VALID_WB_URL = "https://www.wildberries.ru/catalog/123456/detail.aspx"
    INVALID_URL = "https://invalidsite.com/product/123"
    TEST_USER_ID = 123456
    PREMIUM_USER_ID = 789012
    TEST_CHANNEL_ID = -1002467690619

    SAMPLE_PRODUCT_DATA = {
        "name": "Тестовый товар",
        "price": "1 999 ₽",
        "description": "Отличный товар для тестирования",
        "image_url": "https://example.com/test-product.jpg",
        "url": VALID_WB_URL
    }


@pytest.fixture
def test_constants():
    """Предоставляет константы для тестов."""
    return TestConstants

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="session")
async def setup_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(setup_test_db):
    engine = setup_test_db
    async with engine.connect() as conn:
        trans = await conn.begin()  # внешняя транзакция
        Session = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession)
        async with Session() as session:
            # стартуем SAVEPOINT
            await session.begin_nested()

            # авто-реcоздание SAVEPOINT после каждого завершения вложенной транзакции
            @event.listens_for(session.sync_session, "after_transaction_end")
            def _restart_savepoint(sess, transaction):
                if transaction.nested and not sess.in_nested_transaction():
                    sess.begin_nested()

            yield session

            # teardown
            await session.close()
        # откатываем всё целиком
        await trans.rollback()


@pytest.fixture
async def test_user(db_session):
    # сначала пробуем найти уже существующего пользователя с тем же PK
    existing = await db_session.get(User, 123456)
    if existing:
        return existing

    user = User(id=123456, username="testuser", is_premium=False)
    db_session.add(user)
    await db_session.flush()  # без commit — останемся в текущей транзакции/сейвпоинте
    return user
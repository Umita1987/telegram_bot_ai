from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
from models.models import Base  # Импортируем базовый класс из models.py
from logs import get_logger
logger = get_logger("database")

# Создаем асинхронный движок
engine: AsyncEngine = create_async_engine(
    DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),  # Переход на драйвер asyncpg
    echo=True  # Вывод SQL-запросов в консоль (опционально)
)

# Создаем асинхронный Session
async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    """
    Генератор для асинхронной сессии базы данных.
    """
    async with async_session() as session:
        yield session

async def init_db():
    """
    Автоматически создает таблицы в базе данных при запуске.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def shutdown():
    """
    Закрывает соединение с базой перед завершением работы.
    """
    await engine.dispose()

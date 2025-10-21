from prometheus_client import start_http_server, Counter, Histogram, Gauge, Info
import time
from functools import wraps
from logs import get_logger

logger = get_logger("metrics")

# ========== ИНФОРМАЦИЯ О СИСТЕМЕ ==========
BOT_INFO = Info('telegram_bot_info', 'Information about the telegram bot')

# ========== СУЩЕСТВУЮЩИЕ МЕТРИКИ ==========
POSTS_PUBLISHED = Counter("posts_published_total", "Общее число опубликованных постов")
POSTS_FAILED = Counter("posts_failed_total", "Неудачные публикации постов")
PAYMENT_REFUNDS = Counter("payment_refunds_total", "Количество возвращённых платежей")

PUBLISH_LATENCY = Histogram("publish_latency_seconds", "Время публикации поста (в секундах)")
CHECK_REFUNDS_LATENCY = Histogram("check_refunds_latency_seconds", "Время проверки возвратов (в секундах)")

# Метрики для отслеживания источников товаров
PRODUCTS_PARSED_BY_SOURCE = Counter(
    'products_parsed_by_source_total',
    'Total number of products parsed by source',
    ['source']  # wildberries, ozon
)

PRODUCTS_PUBLISHED_BY_SOURCE = Counter(
    'products_published_by_source_total',
    'Total number of products published by source',
    ['source']
)

PARSING_ERRORS_BY_SOURCE = Counter(
    'parsing_errors_by_source_total',
    'Total number of parsing errors by source',
    ['source', 'error_type']
)

PARSING_DURATION_BY_SOURCE = Histogram(
    'parsing_duration_by_source_seconds',
    'Time spent parsing products by source',
    ['source']
)

AI_GENERATION_SUCCESS_BY_SOURCE = Counter(
    'ai_generation_success_by_source_total',
    'Successful AI description generations by source',
    ['source']
)

AI_GENERATION_ERRORS_BY_SOURCE = Counter(
    'ai_generation_errors_by_source_total',
    'Failed AI description generations by source',
    ['source']
)

USER_LINK_SUBMISSIONS = Counter(
    'user_link_submissions_total',
    'Number of product links submitted by users',
    ['source']
)

RANDOM_POSTS_BY_SOURCE = Counter(
    'random_posts_by_source_total',
    'Number of random posts published by source',
    ['source']
)

# ========== НОВЫЕ МЕТРИКИ ==========

# Метрики реакций
REACTIONS_ADDED = Counter(
    'reactions_added_total',
    'Total number of reactions added to posts',
    ['status']  # success/failed
)

REACTIONS_LATENCY = Histogram(
    'reactions_latency_seconds',
    'Time spent adding reactions'
)

# Метрики команд бота
COMMANDS_PROCESSED = Counter(
    'telegram_commands_processed_total',
    'Total number of commands processed',
    ['command', 'status']
)

COMMAND_LATENCY = Histogram(
    'command_processing_latency_seconds',
    'Time spent processing commands',
    ['command']
)

# Метрики сообщений
MESSAGES_RECEIVED = Counter(
    'telegram_messages_received_total',
    'Total number of messages received',
    ['message_type', 'chat_type']
)

# Метрики API
API_REQUESTS = Counter(
    'api_requests_total',
    'Total number of API requests',
    ['api', 'endpoint', 'status']
)

API_LATENCY = Histogram(
    'api_response_time_seconds',
    'API response time',
    ['api', 'endpoint'],
    buckets=(0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

# Метрики БД
DB_QUERY_DURATION = Histogram(
    'database_query_duration_seconds',
    'Time spent executing database queries',
    ['operation']  # select/insert/update/delete
)

DB_CONNECTIONS = Gauge(
    'database_connections_active',
    'Number of active database connections'
)

# Гейджи (текущие значения)
ACTIVE_USERS = Gauge(
    'active_users_count',
    'Number of active users'
)

SCHEDULED_POSTS = Gauge(
    'scheduled_posts_count',
    'Number of scheduled posts'
)

PENDING_PAYMENTS = Gauge(
    'pending_payments_count',
    'Number of pending payments'
)

CHANNEL_MEMBERS = Gauge(
    'telegram_channel_members',
    'Number of channel members',
    ['channel']
)

# Системные метрики
MEMORY_USAGE = Gauge(
    'bot_memory_usage_bytes',
    'Memory usage in bytes'
)

# Метрики ошибок
ERROR_COUNTER = Counter(
    'bot_errors_total',
    'Total number of errors',
    ['error_type', 'module']
)

# Метрики кэширования
CACHE_HITS = Counter(
    'cache_hits_total',
    'Total number of cache hits',
    ['cache_type']
)

CACHE_MISSES = Counter(
    'cache_misses_total',
    'Total number of cache misses',
    ['cache_type']
)


# ========== ДЕКОРАТОРЫ ==========

def track_time(histogram, **labels):
    """Декоратор для отслеживания времени выполнения"""

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    histogram.labels(**labels).observe(duration)
                else:
                    histogram.observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    histogram.labels(**labels).observe(duration)
                else:
                    histogram.observe(duration)

        # Возвращаем правильную обертку в зависимости от типа функции
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def track_errors(counter_metric, error_type_label="error", module_label="unknown"):
    """Декоратор для отслеживания ошибок"""

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                ERROR_COUNTER.labels(
                    error_type=type(e).__name__,
                    module=module_label
                ).inc()
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                ERROR_COUNTER.labels(
                    error_type=type(e).__name__,
                    module=module_label
                ).inc()
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ========== ФУНКЦИИ ОБНОВЛЕНИЯ МЕТРИК ==========

async def update_system_metrics():
    """Обновляет системные метрики"""
    try:
        import psutil
        process = psutil.Process()
        MEMORY_USAGE.set(process.memory_info().rss)
    except Exception as e:
        logger.error(f"Failed to update system metrics: {e}")


async def update_business_metrics():
    """Обновляет бизнес-метрики из БД"""
    try:
        from services.database import async_session
        from models.models import Post, User, Payment
        from sqlalchemy import select, func

        async with async_session() as session:
            # Количество запланированных постов
            scheduled_count = await session.execute(
                select(func.count(Post.id)).where(Post.status == 'scheduled')
            )
            SCHEDULED_POSTS.set(scheduled_count.scalar() or 0)

            # Количество активных пользователей
            active_count = await session.execute(
                select(func.count(User.id)).where(User.is_active == True)
            )
            ACTIVE_USERS.set(active_count.scalar() or 0)

            # Количество ожидающих платежей
            pending_count = await session.execute(
                select(func.count(Payment.id)).where(Payment.status == 'pending')
            )
            PENDING_PAYMENTS.set(pending_count.scalar() or 0)

            # Активные подключения к БД
            result = await session.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
            )
            DB_CONNECTIONS.set(result.scalar() or 0)

    except Exception as e:
        logger.error(f"Failed to update business metrics: {e}")
        ERROR_COUNTER.labels(error_type=type(e).__name__, module="metrics").inc()


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def record_parse_attempt(source: str, success: bool, duration: float = None, error_type: str = None):
    """Записывает попытку парсинга"""
    PRODUCTS_PARSED_BY_SOURCE.labels(source=source).inc()

    if not success and error_type:
        PARSING_ERRORS_BY_SOURCE.labels(source=source, error_type=error_type).inc()

    if duration is not None:
        PARSING_DURATION_BY_SOURCE.labels(source=source).observe(duration)


def record_publish_attempt(source: str, success: bool, duration: float = None):
    """Записывает попытку публикации"""
    if success:
        POSTS_PUBLISHED.inc()
        PRODUCTS_PUBLISHED_BY_SOURCE.labels(source=source).inc()
    else:
        POSTS_FAILED.inc()

    if duration is not None:
        PUBLISH_LATENCY.observe(duration)


def record_reaction_attempt(success: bool, duration: float = None):
    """Записывает попытку добавления реакции"""
    status = "success" if success else "failed"
    REACTIONS_ADDED.labels(status=status).inc()

    if duration is not None:
        REACTIONS_LATENCY.observe(duration)


def record_command(command: str, status: str, duration: float = None):
    """Записывает выполнение команды"""
    COMMANDS_PROCESSED.labels(command=command, status=status).inc()

    if duration is not None:
        COMMAND_LATENCY.labels(command=command).observe(duration)


def record_api_call(api: str, endpoint: str, status: str, duration: float = None):
    """Записывает вызов API"""
    API_REQUESTS.labels(api=api, endpoint=endpoint, status=status).inc()

    if duration is not None:
        API_LATENCY.labels(api=api, endpoint=endpoint).observe(duration)


def record_message(message_type: str, chat_type: str):
    """Записывает полученное сообщение"""
    MESSAGES_RECEIVED.labels(message_type=message_type, chat_type=chat_type).inc()


def record_cache_access(cache_type: str, hit: bool):
    """Записывает обращение к кэшу"""
    if hit:
        CACHE_HITS.labels(cache_type=cache_type).inc()
    else:
        CACHE_MISSES.labels(cache_type=cache_type).inc()


# ========== ИНИЦИАЛИЗАЦИЯ ==========

def start_prometheus_server(port: int = 8000):
    """Запускает HTTP сервер для экспорта метрик"""
    try:
        start_http_server(port)
        logger.info(f"📊 Metrics server started on port {port}")

        # Устанавливаем базовую информацию о боте
        BOT_INFO.info({
            'version': '1.0.0',
            'environment': 'production',
            'started_at': str(time.time())
        })
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
        raise
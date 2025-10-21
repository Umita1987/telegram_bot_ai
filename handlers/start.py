
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from handlers.keyboards import generate_reply_main_menu
from services.database import async_session
from models.models import Post
from sqlalchemy.future import select

from logs import get_logger

logger = get_logger("start")
router = Router()


def get_main_keyboard():
    return generate_reply_main_menu()


@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    # Получаем аргументы команды /start, разбив текст по пробелам
    parts = message.text.split(maxsplit=1)
    args = parts[1] if len(parts) > 1 else ""

    if args == "after_payment":
        await message.answer("Спасибо за оплату! Теперь выберите время публикации поста.")
        return

    user_data = await state.get_data()
    if not user_data.get("first_time"):
        await state.update_data(first_time=True)
        await message.answer(
            "👋 Привет! Я бот, который помогает создавать красивые описания товаров для публикаций. "
            "Отправьте мне ссылку на товар с Wildberries и Ozon, и я сделаю всё остальное!\n\n"
            "ℹ️ Используйте /about, чтобы узнать больше.",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            "👋 С возвращением! Чем могу помочь?",
            reply_markup=get_main_keyboard()
        )


@router.message(Command("about"))
async def about_command(message: Message):
    await message.answer(
        "ℹ️ Этот бот помогает вам создавать и публиковать товарные посты в Telegram. "
        "Просто отправьте ссылку на товар, подтвердите описание и оплатите публикацию!"
    )


def split_message(text: str, max_length: int = 4000) -> list:
    """Разбивает текст на части по max_length символов."""
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]


@router.message(lambda message: message.text == "📜 Посмотреть опубликованные посты")
async def view_published_posts(message: Message):
    """
    Выводит список опубликованных постов пользователя.
    """
    user_id = message.from_user.id
    async with async_session() as session:
        result = await session.execute(
            select(Post)
            .where(Post.user_id == user_id, Post.status == "published")
            .order_by(Post.published_at.desc())
        )
        posts = result.scalars().all()

    if not posts:
        await message.answer("❌ У вас пока нет опубликованных постов.")
    else:
        response = "📝 Ваши опубликованные посты:\n\n"
        for post in posts:
            response += (
                f"📌 [{post.content[:30]}...] (опубликован {post.published_at.strftime('%H:%M UTC')})\n"
                f"🔗 [Посмотреть в канале](https://t.me/wildberriesStuff1/{post.telegram_message_id})\n\n"
            )
        MAX_LENGTH = 4000
        if len(response) > MAX_LENGTH:
            parts = split_message(response, MAX_LENGTH)
            for part in parts:
                await message.answer(part, parse_mode="Markdown")
        else:
            await message.answer(response, parse_mode="Markdown")


@router.message(lambda message: message.text == "➕ Разместить ещё один пост")
async def add_new_post(message: Message):
    """
    Позволяет пользователю добавить новый пост.
    """
    await message.answer(
        "📢 Отправьте мне ссылку на товар с Wildberries, и я помогу создать публикацию!"
    )


@router.message(lambda message: message.text == "📊 Статистика постов")
async def redirect_to_stats(message: Message):
    from handlers.stats_handlers import view_post_stats  # Импортируем обработчик из stats_handlers.py
    await view_post_stats(message)  # Вызываем функцию получения статистики, передавая объект сообщения



def register_start_handlers(dp):
    dp.include_router(router)
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import update
from sqlalchemy.future import select

# Импортируем функции клавиатур из keyboards.py
from handlers.keyboards import generate_reply_main_menu, generate_full_action_keyboard
from models.models import Post, User
from services.content_generator import generate_product_description
from services.database import async_session

logger = logging.getLogger("callback_handlers")
router = Router()

# Состояние для редактирования текста
class EditPostState(StatesGroup):
    waiting_for_text = State()


@router.callback_query(lambda c: c.data == "generate_text")
async def generate_ad_text(callback: CallbackQuery, state: FSMContext):
    """Генерация текста объявления."""

    user_id = callback.from_user.id
    username = callback.from_user.username or "unknown_user"

    data = await state.get_data()
    if "product_data" not in data:
        await callback.message.answer("❌ Данные о товаре не найдены. Попробуйте снова отправить ссылку.")
        return

    product_data = data["product_data"]

    try:
        publication_text = await generate_product_description(
            name=product_data["title"],
            description=product_data["description"]
        )
        publication_text = (
            f"✨ {publication_text} ✨\n\n"
            f"💰 Цена: {product_data['price']}\n"
            f"📦 Заказывайте уже сейчас по ссылке: {product_data['url']}"
        )
        product_data["generated_description"] = publication_text
    except Exception as e:
        logger.error(f"❌ Ошибка генерации текста: {e}", exc_info=True)
        await callback.message.answer(f"❌ Ошибка генерации описания: {e}")
        return

    try:
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(select(User).filter_by(id=user_id))
                user = result.scalars().first()
                if not user:
                    new_user = User(id=user_id, username=username, is_premium=False)
                    session.add(new_user)

                post = Post(
                    user_id=user_id,
                    content=product_data["title"],
                    description=publication_text,
                    price=product_data["price"].replace("₽", "").strip(),
                    image_url=product_data.get("image_url"),
                    link=product_data.get("url"),
                    status="draft"
                )
                session.add(post)
                await session.flush()

                await session.execute(
                    update(Post)
                    .where(
                        Post.user_id == user_id,
                        Post.id != post.id,
                        Post.status.in_(["draft", "accepted", "paid"])
                    )
                    .values(status="obsolete")
                )
                post_id = post.id
            logger.info(f"✅ Черновик поста сохранён: {post_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка работы с БД: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка сохранения поста.")
        return

    # ✅ Отправляем НОВОЕ сообщение вместо редактирования старого
    await callback.message.answer_photo(
        photo=product_data["image_url"],
        caption=publication_text,
        reply_markup=generate_full_action_keyboard(post_id)
    )


@router.callback_query(lambda c: c.data.startswith("edit_post_text:"))
async def edit_post_text(callback: CallbackQuery, state: FSMContext):
    """Обработчик редактирования текста поста."""
    # Убираем inline-клавиатуру, чтобы предотвратить повторное нажатие
    await callback.message.edit_reply_markup(reply_markup=None)

    try:
        post_id = int(callback.data.split(":")[1])
    except ValueError:
        await callback.message.answer("❌ Неверный формат данных.")
        return

    async with async_session() as session:
        async with session.begin():
            post_query = await session.execute(select(Post).where(Post.id == post_id))
            post = post_query.scalars().first()
            if not post:
                await callback.message.answer("❌ Пост не найден.")
                return

            # Сохраняем post_id в состояние FSM для последующего обновления
            await state.update_data(editing_post_id=post.id, message_id=callback.message.message_id)
            await callback.message.answer("✏️ Введите новый текст для поста. Отправьте его следующим сообщением.")
            await state.set_state(EditPostState.waiting_for_text)

@router.message(EditPostState.waiting_for_text)
async def save_edited_text(message: Message, state: FSMContext):
    """Сохранение отредактированного текста поста."""
    new_text = message.text
    user_id = message.from_user.id
    try:
        async with async_session() as session:
            async with session.begin():
                data = await state.get_data()
                post_id = data.get("editing_post_id")
                if not post_id:
                    await message.answer("❌ Ошибка: не найден ID поста для редактирования.")
                    return

                post_query = await session.execute(select(Post).where(Post.id == post_id, Post.user_id == user_id))
                post = post_query.scalars().first()
                if not post:
                    await message.answer("❌ Пост не найден.")
                    return

                # Обновляем данные поста внутри одной транзакции
                post.description = new_text
                post.status = "draft"
                post_id = post.id  # Сохраняем ID для дальнейшего использования
            logger.info(f"✅ Пост ID {post_id} успешно обновлён!")
    except Exception as e:
        logger.error(f"❌ Ошибка обновления поста: {e}", exc_info=True)
        await message.answer("❌ Ошибка обновления поста.")
        return

    full_text = (
        f"✨ {new_text} ✨\n\n"
        f"💰 Цена: {post.price} ₽\n"
        f"📦 Заказывайте по ссылке: {post.link}"
    )
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer_photo(
        photo=post.image_url,
        caption=full_text[:1024],
        reply_markup=generate_full_action_keyboard(post_id)
    )
    await state.clear()

@router.callback_query(lambda c: c.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    """Обработчик кнопки 'Назад' для возврата в главное меню."""
    try:
        await callback.message.answer("👇 Главное меню", reply_markup=generate_reply_main_menu())
    except Exception as e:
        logger.error(f"❌ Ошибка при возврате в главное меню: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка при возврате в меню.")

def register_callback_query_handlers(dp):
    dp.include_router(router)

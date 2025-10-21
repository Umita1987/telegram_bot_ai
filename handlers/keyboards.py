from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def generate_action_keyboard() -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с кнопками "✅ Принять пост" и "♻️ Перегенерировать текст".
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять пост", callback_data="accept_post")
    builder.button(text="♻️ Перегенерировать текст", callback_data="regenerate_text")
    builder.adjust(1)
    return builder.as_markup()

def generate_publish_keyboard(post_id: int, slots: list) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for slot in slots:
        slot_str = slot.isoformat()
        button = InlineKeyboardButton(
            text=slot.strftime("%d.%m %H:%M MSK"),
            callback_data=f"slot_{post_id}_{slot_str}"
        )
        keyboard.inline_keyboard.append([button])
    return keyboard

def generate_payment_keyboard(post_id: int):
    """
    Генерирует инлайн-клавиатуру с кнопкой оплаты.
    Callback data имеет формат "pay_post:<post_id>"
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay_post:{post_id}")]
        ]
    )

def generate_full_action_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """
    Генерирует клавиатуру с кнопками:
    - "✅ Принять пост" (с передачей post_id),
    - "🔄 Сгенерировать ещё раз",
    - "✏️ Отредактировать текст" (с передачей post_id),
    - "🔙 Вернуться назад".
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять пост", callback_data=f"accept_post:{post_id}"),
                InlineKeyboardButton(text="🔄 Сгенерировать ещё раз", callback_data="regenerate_text")
            ],
            [
                InlineKeyboardButton(text="✏️ Отредактировать текст", callback_data=f"edit_post_text:{post_id}"),
                InlineKeyboardButton(text="🔙 Вернуться назад", callback_data="back_to_main_menu")
            ]
        ]
    )

def generate_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Посмотреть размещённые посты", callback_data="view_posts")],
            [InlineKeyboardButton(text="📊 Статистика постов", callback_data="view_post_stats")],
            [InlineKeyboardButton(text="➕ Разместить ещё один пост", callback_data="create_new_post")]
        ]
    )

def generate_reply_main_menu() -> ReplyKeyboardMarkup:
    """
    Генерирует главное меню с кнопками в виде ReplyKeyboard (для удобства пользователей).
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📜 Посмотреть опубликованные посты")],
            [KeyboardButton(text="➕ Разместить ещё один пост")],
            [KeyboardButton(text="📊 Статистика постов")]
        ],
        resize_keyboard=True
    )

def generate_generate_text_keyboard() -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с кнопкой "Сгенерировать рекламный текст".
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сгенерировать рекламный текст", callback_data="generate_text")]
    ])

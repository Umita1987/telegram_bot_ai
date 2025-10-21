from aiogram import Router
from aiogram.types import CallbackQuery
from logs import get_logger

logger = get_logger("admin_handlers")

router = Router()

@router.callback_query(lambda c: c.data == "approve_post")
async def approve_post(callback: CallbackQuery):
    await callback.message.edit_text("Пост утвержден!")
    await callback.answer()

def register_admin_handlers(dp):
    dp.include_router(router)
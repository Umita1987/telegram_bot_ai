import random
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
from telethon.errors import RPCError
from logs import get_logger
from services.telethon_client import get_client

logger = get_logger("reaction_sender")

ALL_REACTIONS = ["👍", "❤️", "🔥", "🥰", "👏", "🎉", "😍"]
MAX_UNIQUE_REACTIONS = 11  # Лимит для паблик-канала Telegram

async def send_reactions(channel_username: str, message_id: int):
    client = get_client()
    try:
        entity = await client.get_entity(channel_username)
        message = await client.get_messages(channel_username, ids=message_id)

        # Получаем список уже существующих уникальных реакций на сообщении
        existing_emojis = []
        if hasattr(message, "reactions") and message.reactions:
            for result in message.reactions.results:
                if hasattr(result.reaction, "emoticon"):
                    existing_emojis.append(result.reaction.emoticon)

        # Если достигнут лимит по уникальным реакциям — ставим только существующие
        if len(existing_emojis) >= MAX_UNIQUE_REACTIONS:
            if not existing_emojis:
                logger.warning(f"⚠️ Нет доступных реакций для сообщения {message_id}.")
                return
            selected_emojis = random.choices(existing_emojis, k=random.randint(1, len(existing_emojis)))
        else:
            selected_emojis = random.choices(ALL_REACTIONS, k=random.randint(1, 3))

        selected_reactions = [ReactionEmoji(emoticon=emoji) for emoji in selected_emojis]

        await client(SendReactionRequest(
            peer=entity,
            msg_id=message_id,
            reaction=selected_reactions
        ))
        logger.info(f"✅ Добавлены реакции {selected_emojis} к сообщению {message_id}")

    except RPCError as e:
        logger.error(f"❌ Ошибка при добавлении реакций: {e}")
    except Exception as e:
        logger.exception(f"❌ Непредвиденная ошибка при добавлении реакций к сообщению {message_id}: {e}")
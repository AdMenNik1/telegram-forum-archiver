import os
import asyncio
import random
from telethon import TelegramClient
from telethon.tl.functions.channels import (
    CreateForumTopicRequest,
    GetForumTopicsRequest
)
from telethon.tl.types import UpdateNewChannelMessage
from telethon.errors import RPCError, FloodWaitError
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# 🔧 Конфигурация
api_id              = int(os.getenv("API_ID"))
api_hash            = os.getenv("API_HASH")
phone               = os.getenv("PHONE")
source_channel_id   = int(os.getenv("SOURCE_CHANNEL_ID"))
post_id             = int(os.getenv("POST_ID"))
target_channel_id   = int(os.getenv("TARGET_CHANNEL_ID"))
ICON_EMOJI_ID       = int(os.getenv("ICON_EMOJI_ID"))

async def load_forum_topics(client, channel, limit=100):
    res = await client(GetForumTopicsRequest(
        channel=channel,
        offset_date=0,
        offset_id=0,
        offset_topic=0,
        limit=limit
    ))
    topics = {}
    for t in res.topics:
        top = t.top_message
        sid = top if isinstance(top, int) else top.id
        topics[t.title.strip()] = sid
    return topics

async def main():
    client = TelegramClient('session', api_id, api_hash)
    await client.start(phone)
    print("✅ Авторизация успешна.")

    source = await client.get_entity(source_channel_id)
    target = await client.get_entity(target_channel_id)

    try:
        existing = await load_forum_topics(client, target, limit=100)
        print(f"📋 Тем найдено: {len(existing)}")
    except RPCError as e:
        print(f"❌ Ошибка загрузки тем: {e}")
        return

    current_id = post_id
    missing_count = 0
    max_missing = 2000

    while True:
        msg = await client.get_messages(source, ids=current_id)
        if not msg:
            print(f"⚠️ Пост #{current_id} не найден, пропускаем.")
            missing_count += 1
            if missing_count >= max_missing:
                print("⚠️ Слишком много подряд пропущенных постов, завершаем.")
                break
            current_id += 1
            continue

        missing_count = 0

        text = msg.text or ""
        lines = text.split('\n')
        topic_title = lines[1].strip() if len(lines) >= 2 and lines[1].strip() else f"Пост #{current_id}"

        # Создание или выбор темы
        if topic_title in existing:
            service_msg_id = existing[topic_title]
            print(f"⚠️ Тема уже существует: «{topic_title}»")
        else:
            try:
                result = await client(CreateForumTopicRequest(
                    channel=target,
                    title=topic_title,
                    icon_emoji_id=ICON_EMOJI_ID
                ))
                service_msg_id = None
                for upd in result.updates:
                    if isinstance(upd, UpdateNewChannelMessage):
                        service_msg_id = upd.message.id
                        break
                if service_msg_id is None:
                    existing = await load_forum_topics(client, target)
                    service_msg_id = existing.get(topic_title)
                if service_msg_id is None:
                    print(f"❌ Не удалось получить service_msg_id темы «{topic_title}»")
                    current_id += 1
                    continue
                existing[topic_title] = service_msg_id
                print(f"✅ Создана тема «{topic_title}»")
            except RPCError as e:
                print(f"❌ Ошибка создания темы: {e}")
                current_id += 1
                continue

        # Отправка главного медиа-поста
        if msg.photo or msg.video:
            try:
                await client.send_file(
                    entity=target,
                    file=msg.media,
                    caption=text,
                    reply_to=service_msg_id
                )
                print(f"📌 Основной медиа-пост #{msg.id} отправлен.")
                await asyncio.sleep(random.uniform(15, 20))
            except FloodWaitError as e:
                print(f"⏳ FloodWait {e.seconds}s — ждём")
                await asyncio.sleep(e.seconds)
                await client.send_file(
                    entity=target,
                    file=msg.media,
                    caption=text,
                    reply_to=service_msg_id
                )
                await asyncio.sleep(random.uniform(15, 20))
            except Exception as e:
                print(f"❌ Ошибка отправки основного медиа-поста: {e}")
        else:
            print(f"⏭ Пропущен основной пост #{msg.id} — не фото/видео.")

        # Сбор медиа из комментариев
        media_files = []
        async for reply in client.iter_messages(source, reply_to=msg.id, reverse=True):
            if reply.photo or reply.video:
                media_files.append((reply.media, reply.text))
            else:
                print(f"⏭ Пропущен комментарий #{reply.id} — не фото/видео.")

        # Отправка альбомами по 10 файлов
        chunk_size = 10
        for i in range(0, len(media_files), chunk_size):
            chunk = media_files[i:i+chunk_size]
            files = [m[0] for m in chunk]
            caption = next((m[1] for m in chunk if m[1]), None)
            try:
                await client.send_file(
                    entity=target,
                    file=files,
                    caption=caption,
                    reply_to=service_msg_id
                )
                print(f"📤 Альбом из {len(files)} медиа отправлен.")
                await asyncio.sleep(random.uniform(15, 20))
            except FloodWaitError as e:
                print(f"⏳ FloodWait {e.seconds}s — ждём")
                await asyncio.sleep(e.seconds)
                await client.send_file(
                    entity=target,
                    file=files,
                    caption=caption,
                    reply_to=service_msg_id
                )
                await asyncio.sleep(random.uniform(15, 20))
            except Exception as e:
                print(f"❌ Ошибка отправки альбома: {e}")

        # Если не было медиа — заглушка
        if not media_files:
            print("⚠️ Нет медиа — отправляем заглушку.")
            try:
                await client.send_message(
                    entity=target,
                    message="Контент утерян, пытаюсь восстановить.",
                    reply_to=service_msg_id
                )
                await asyncio.sleep(random.uniform(15, 20))
            except FloodWaitError as e:
                print(f"⏳ FloodWait {e.seconds}s — ждём")
                await asyncio.sleep(e.seconds)
                await client.send_message(
                    entity=target,
                    message="Контент утерян, пытаюсь восстановить.",
                    reply_to=service_msg_id
                )
                await asyncio.sleep(random.uniform(15, 20))
            except Exception as e:
                print(f"❌ Ошибка отправки заглушки: {e}")

        current_id += 1

    print("✅ Все посты обработаны.")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())

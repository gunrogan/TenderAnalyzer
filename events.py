# events.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from config import settings

STATUS_CHANNEL = "tenders:status"


def _new_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


def format_event(payload: dict[str, Any], event_type: str = "status") -> str:
    """Преобразует payload в SSE-фрейм вида `event: ...\\ndata: ...\\n\\n`."""
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"


async def publish_status(
    file_id: UUID,
    status: str,
    error_message: str | None = None,
) -> None:
    """Публикует сообщение о смене статуса в Redis-канал."""
    payload = {
        "type": "status",
        "file_id": str(file_id),
        "status": status,
        "error_message": error_message,
        "ts": datetime.now(UTC).isoformat(),
    }
    client = _new_client()
    try:
        await client.publish(STATUS_CHANNEL, json.dumps(payload, ensure_ascii=False))
    finally:
        await client.aclose()


async def status_event_stream():
    """Асинхронный генератор SSE-событий о смене статусов файлов."""
    client = _new_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(STATUS_CHANNEL)
    try:
        yield format_event(
            {"type": "connected", "ts": datetime.now(UTC).isoformat()},
            "connected",
        )
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=15
            )
            if message is None:
                yield format_event(
                    {"type": "ping", "ts": datetime.now(UTC).isoformat()},
                    "ping",
                )
                continue
            data = message.get("data")
            if data:
                yield f"event: status\ndata: {data}\n\n"
    finally:
        try:
            await pubsub.unsubscribe(STATUS_CHANNEL)
        except Exception:
            pass
        await pubsub.aclose()
        await client.aclose()
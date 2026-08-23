# tests/test_events.py
import json
from uuid import uuid4

import pytest

import events as events_module
from events import format_event, publish_status


class FakePubsub:
    def __init__(self, messages):
        self._messages = list(messages)
        self.subscribed = None
        self.closed = False

    async def subscribe(self, *channels):
        self.subscribed = channels

    async def get_message(self, ignore_subscribe_messages=False, timeout=None):
        if self._messages:
            return {
                "type": "message",
                "channel": events_module.STATUS_CHANNEL,
                "data": self._messages.pop(0),
            }
        return None

    async def unsubscribe(self, *channels):
        pass

    async def aclose(self):
        self.closed = True


class FakeClient:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.published = []
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def publish(self, channel, payload):
        self.published.append((channel, payload))

    async def aclose(self):
        self.closed = True


def test_format_event_produces_sse_frame():
    frame = format_event({"status": "completed"}, "status")
    assert frame.startswith("event: status\n")
    assert "data: " in frame
    assert frame.endswith("\n\n")
    assert "completed" in frame


@pytest.mark.asyncio
async def test_status_event_stream_yields_connected_then_status(monkeypatch):
    payload = json.dumps(
        {"type": "status", "file_id": str(uuid4()), "status": "completed"}
    )
    pubsub = FakePubsub([payload])
    client = FakeClient(pubsub)
    monkeypatch.setattr(events_module, "_new_client", lambda: client)

    stream = events_module.status_event_stream()
    first = await anext(stream)
    assert first.startswith("event: connected")

    second = await anext(stream)
    assert second.startswith("event: status")
    assert "completed" in second

    await stream.aclose()
    assert pubsub.closed
    assert client.closed


@pytest.mark.asyncio
async def test_publish_status_publishes_to_redis(monkeypatch):
    client = FakeClient(FakePubsub([]))
    monkeypatch.setattr(events_module, "_new_client", lambda: client)

    await publish_status(uuid4(), "processing")
    assert client.published
    channel, raw = client.published[0]
    assert channel == events_module.STATUS_CHANNEL
    data = json.loads(raw)
    assert data["status"] == "processing"
"""Message-oriented communication middleware, backed by Redis Streams.

Producers call publish_event() and move on immediately; the event sits
on the `parking_events` stream until a consumer reads it. Producer and
consumer are decoupled in time — this is what distinguishes it from a
direct RPC call.
"""

import json
import time
from datetime import datetime, timezone

import redis

import config

_client = None


def get_redis_client():
    global _client
    if _client is None:
        _client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    return _client


def publish_event(event_type: str, source: str, data: dict | None = None):
    """Publish an event onto the parking_events stream. Fire-and-forget."""
    client = get_redis_client()
    payload = {
        "event": event_type,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": json.dumps(data or {}),
    }
    try:
        client.xadd(config.REDIS_STREAM, payload, maxlen=500, approximate=True)
    except redis.exceptions.RedisError as exc:
        print(f"[MESSAGE_BUS] Failed to publish {event_type}: {exc}")


def consume_events(last_id: str = "$", block_ms: int = 2000):
    """Blocking generator that yields new events appended to the stream.

    Starts from `last_id` ('$' = only events published after this call).
    Independent from any RPC path — this is a separate consumer loop.
    """
    client = get_redis_client()
    while True:
        try:
            response = client.xread({config.REDIS_STREAM: last_id}, block=block_ms, count=10)
        except redis.exceptions.RedisError as exc:
            print(f"[MESSAGE_BUS] Redis read error: {exc}")
            time.sleep(1)
            continue

        if not response:
            continue

        for _stream_name, entries in response:
            for entry_id, fields in entries:
                last_id = entry_id
                event = dict(fields)
                event["id"] = entry_id
                try:
                    event["data"] = json.loads(event.get("data", "{}"))
                except json.JSONDecodeError:
                    event["data"] = {}
                yield event


def read_recent_events(count: int = 20):
    """One-shot read of the most recent events (for a REST snapshot on page load)."""
    client = get_redis_client()
    try:
        entries = client.xrevrange(config.REDIS_STREAM, count=count)
    except redis.exceptions.RedisError as exc:
        print(f"[MESSAGE_BUS] Redis read error: {exc}")
        return []

    events = []
    for entry_id, fields in entries:
        event = dict(fields)
        event["id"] = entry_id
        try:
            event["data"] = json.loads(event.get("data", "{}"))
        except json.JSONDecodeError:
            event["data"] = {}
        events.append(event)
    return list(reversed(events))

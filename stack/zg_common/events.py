"""TMF688-style event publishing on Apache Kafka (KRaft mode, Apache-2.0). Events only – never commands (ADR-003)."""
import asyncio, json, uuid, datetime
from aiokafka import AIOKafkaProducer
from .config import KAFKA_BOOTSTRAP, KAFKA_TOPIC

_p = None
_lock = asyncio.Lock()

async def _producer():
    global _p
    async with _lock:
        if _p is None:
            _p = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, acks="all", enable_idempotence=True, request_timeout_ms=5000)
            await _p.start()
    return _p

def envelope(event_type, resource, source, run_id=None):
    return {"eventId": str(uuid.uuid4()), "eventTime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "eventType": event_type, "source": source, "correlationId": run_id,
            "event": resource, "@type": event_type, "@baseType": "Event"}

async def apublish(event_type, resource, source, run_id=None):
    try:
        p = await _producer()
        ev = envelope(event_type, resource, source, run_id)
        await p.send_and_wait(KAFKA_TOPIC, json.dumps(ev, default=str).encode(), key=event_type.encode())
        return ev
    except Exception as e:  # events must never break the business call
        print("Kafka publish failed", e)
        return None

"""L8 · TMF688-style event recorder: Kafka consumer group zg-l8-audit on tmf688-events → l8.events (audit trail)."""
import asyncio, json
from aiokafka import AIOKafkaConsumer
from stack.zg_common.config import KAFKA_BOOTSTRAP, KAFKA_TOPIC
from stack.zg_common.db import q, J

async def main():
    c = AIOKafkaConsumer(KAFKA_TOPIC, bootstrap_servers=KAFKA_BOOTSTRAP, group_id="zg-l8-audit", auto_offset_reset="earliest",
                         enable_auto_commit=False)
    for i in range(60):
        try:
            await c.start(); break
        except Exception:
            await asyncio.sleep(1)
    print(f"L8 event recorder consuming {KAFKA_TOPIC}", flush=True)
    async for m in c:
        b = json.loads(m.value)
        q("insert into l8.events(subject, run_id, body) values(%s,%s,%s)", f"tmf688.{b.get('eventType')}", b.get("correlationId"), J(b))
        await c.commit()

if __name__ == "__main__":
    asyncio.run(main())

import json
import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

from confluent_kafka import Producer
from prometheus_client import Counter

from app.models.schemas import CreatedOrder

_PRODUCER: Producer | None = None
ORDER_EVENTS_PRODUCED_TOTAL = Counter(
    "order_events_produced_total",
    "Total number of order-created events successfully produced by order-service",
)
ORDER_EVENTS_PRODUCE_FAILED_TOTAL = Counter(
    "order_events_produce_failed_total",
    "Total number of order-created event publish attempts that failed in order-service",
)


def kafka_enabled() -> bool:
    return os.getenv("KAFKA_ENABLED", "false").strip().lower() == "true"


def publish_order_created(order: CreatedOrder) -> dict:
    topic = _order_created_topic()
    event_id = str(uuid4())
    event = {
        "event_id": event_id,
        "event_type": "order.created",
        "emitted_at": datetime.now(UTC).isoformat(),
        "order": order.model_dump(mode="json"),
    }

    producer = _producer()
    delivery = {}
    delivered = threading.Event()

    def _on_delivery(err, msg) -> None:
        delivery["error"] = err
        if msg is not None:
            delivery["topic"] = msg.topic()
            delivery["partition"] = msg.partition()
            delivery["offset"] = msg.offset()
        delivered.set()

    producer.produce(
        topic=topic,
        key=order.order_id.encode("utf-8"),
        value=json.dumps(event).encode("utf-8"),
        on_delivery=_on_delivery,
    )
    producer.poll(0)

    timeout_seconds = _send_timeout_seconds()
    remaining = producer.flush(timeout=timeout_seconds)
    if remaining != 0 or not delivered.wait(timeout=timeout_seconds):
        ORDER_EVENTS_PRODUCE_FAILED_TOTAL.inc()
        raise TimeoutError("Kafka delivery callback timed out")
    if delivery.get("error") is not None:
        ORDER_EVENTS_PRODUCE_FAILED_TOTAL.inc()
        raise RuntimeError(f"Kafka delivery failed: {delivery['error']}")

    ORDER_EVENTS_PRODUCED_TOTAL.inc()

    return {
        "event_id": event_id,
        "topic": delivery.get("topic"),
        "partition": delivery.get("partition"),
        "offset": delivery.get("offset"),
    }


def close_producer() -> None:
    global _PRODUCER
    if _PRODUCER is None:
        return
    _PRODUCER.flush(timeout=5)
    _PRODUCER = None


def _producer() -> Producer:
    global _PRODUCER
    if _PRODUCER is None:
        _PRODUCER = Producer(
            {
                "bootstrap.servers": ",".join(_bootstrap_servers()),
                "client.id": os.getenv("KAFKA_CLIENT_ID", "order-service-producer"),
                "acks": os.getenv("KAFKA_ACKS", "all"),
                "retries": _producer_retries(),
                "linger.ms": _linger_ms(),
            }
        )
    return _PRODUCER


def _bootstrap_servers() -> list[str]:
    raw = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _order_created_topic() -> str:
    return os.getenv("KAFKA_ORDER_CREATED_TOPIC", "orders.created")


def _producer_retries() -> int:
    raw = os.getenv("KAFKA_PRODUCER_RETRIES", "5")
    try:
        value = int(raw)
    except ValueError:
        return 5
    return value if value >= 0 else 0


def _linger_ms() -> int:
    raw = os.getenv("KAFKA_PRODUCER_LINGER_MS", "5")
    try:
        value = int(raw)
    except ValueError:
        return 5
    return value if value >= 0 else 0


def _send_timeout_seconds() -> float:
    raw = os.getenv("KAFKA_SEND_TIMEOUT_SECONDS", "10")
    try:
        value = float(raw)
    except ValueError:
        return 10.0
    return value if value > 0 else 10.0

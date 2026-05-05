import json
import logging
import os
import threading

from confluent_kafka import Consumer
from prometheus_client import Counter

from app.models.schemas import ReduceStockRequest
from app.services.inventory_service import reduce_stock

logger = logging.getLogger("uvicorn.error")
ORDER_EVENTS_PROCESSED_TOTAL = Counter(
    "order_events_processed_total",
    "Total number of order-created events successfully processed by a service",
)
ORDER_EVENTS_PROCESS_FAILED_TOTAL = Counter(
    "order_events_process_failed_total",
    "Total number of order-created event processing failures in a service",
)

_STOP_EVENT = threading.Event()
_THREAD: threading.Thread | None = None
_CONSUMER: Consumer | None = None


def kafka_enabled() -> bool:
    return os.getenv("KAFKA_ENABLED", "false").strip().lower() == "true"


def start_consumer() -> None:
    global _THREAD
    if not kafka_enabled():
        logger.info("Inventory Kafka consumer disabled because KAFKA_ENABLED is false")
        return
    if _THREAD is not None and _THREAD.is_alive():
        logger.info("Inventory Kafka consumer thread already running")
        return

    _STOP_EVENT.clear()
    logger.info(
        "Starting inventory Kafka consumer (topic=%s, group_id=%s, bootstrap_servers=%s)",
        _topic(),
        os.getenv("KAFKA_INVENTORY_GROUP_ID", "inventory-service-group"),
        ",".join(_bootstrap_servers()),
    )
    _THREAD = threading.Thread(target=_consume_loop, name="inventory-order-events-consumer", daemon=True)
    _THREAD.start()


def stop_consumer() -> None:
    global _CONSUMER, _THREAD
    _STOP_EVENT.set()

    if _CONSUMER is not None:
        _CONSUMER.close()
        _CONSUMER = None

    if _THREAD is not None and _THREAD.is_alive():
        _THREAD.join(timeout=2)
    _THREAD = None
    logger.info("Inventory Kafka consumer stopped")


def _consume_loop() -> None:
    global _CONSUMER
    try:
        _CONSUMER = Consumer(
            {
                "bootstrap.servers": ",".join(_bootstrap_servers()),
                "group.id": os.getenv("KAFKA_INVENTORY_GROUP_ID", "inventory-service-group"),
                "auto.offset.reset": os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest"),
                "enable.auto.commit": True,
            }
        )
        _CONSUMER.subscribe([_topic()])
        logger.info("Inventory Kafka consumer subscribed to topic '%s'", _topic())
    except Exception:
        logger.exception("Failed to initialize inventory Kafka consumer")
        _CONSUMER = None
        return

    poll_count = 0
    while not _STOP_EVENT.is_set() and _CONSUMER is not None:
        try:
            messages = _CONSUMER.consume(
                num_messages=_max_poll_records(),
                timeout=_poll_timeout_ms() / 1000.0,
            )
            poll_count += 1
            if poll_count % 100 == 0:
                logger.info(f"[INVENTORY CONSUMER] Poll #{poll_count}: received {len(messages) if messages else 0} messages")
            
            if not messages:
                continue
            for msg in messages:
                if msg is None:
                    continue
                if msg.error():
                    logger.error("Inventory Kafka consumer error: %s", msg.error())
                    continue
                raw_value = msg.value()
                if raw_value is None:
                    logger.warning("Inventory Kafka consumer received empty message")
                    continue
                event = json.loads(raw_value.decode("utf-8"))
                order_id = event.get("order", {}).get("order_id", "unknown")
                logger.info(
                    "Inventory consumed event topic=%s partition=%s offset=%s order_id=%s",
                    msg.topic(),
                    msg.partition(),
                    msg.offset(),
                    order_id,
                )
                _process_order_created_event(event)
        except Exception:
            logger.exception("Inventory Kafka consumer loop failed")


def _process_order_created_event(event: dict) -> None:
    try:
        order = event["order"]
        payload = ReduceStockRequest(
            order_id=order["order_id"],
            items=order["items"],
        )
        reduce_stock(payload)
        ORDER_EVENTS_PROCESSED_TOTAL.inc()
        logger.info("Inventory processed order-created event order_id=%s", payload.order_id)
    except Exception:
        ORDER_EVENTS_PROCESS_FAILED_TOTAL.inc()
        logger.exception("Failed to process order-created event in inventory service")


def _bootstrap_servers() -> list[str]:
    raw = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _topic() -> str:
    return os.getenv("KAFKA_ORDER_CREATED_TOPIC", "orders.created")


def _poll_timeout_ms() -> int:
    raw = os.getenv("KAFKA_CONSUMER_POLL_TIMEOUT_MS", "1000")
    try:
        value = int(raw)
    except ValueError:
        return 1000
    return value if value > 0 else 1000


def _max_poll_records() -> int:
    raw = os.getenv("KAFKA_CONSUMER_MAX_RECORDS", "100")
    try:
        value = int(raw)
    except ValueError:
        return 100
    return value if value > 0 else 100

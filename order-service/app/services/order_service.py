import os
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from time import sleep
from uuid import uuid4

from prometheus_client import Counter

from app.clients import email_client, inventory_client
from app.cache.redis_client import get_redis_client
from app.config.feature_flags import is_redis_enabled, should_prefer_cache
from app.messaging import kafka_enabled, publish_order_created
from app.models.schemas import CreateOrderRequest, CreateOrderResponse, CreatedOrder, DownstreamResult

logger = logging.getLogger("uvicorn.error")

# Metrics for API calls (sync mode)
api_calls_total = Counter(
    'api_calls_total',
    'Total API calls made by order service',
    ['service', 'status']
)

ORDERS: dict[str, CreatedOrder] = {}


def create_order(payload: CreateOrderRequest) -> CreateOrderResponse:
    if _inventory_http_precheck_enabled():
        # Pre-check inventory availability before creating order
        try:
            check_result = inventory_client.check_stock_availability(
                [item.model_dump() for item in payload.items]
            )
            logger.info(f"Stock check result: {check_result}")
            if not check_result.get("available", False):
                # Stock not available - reject order
                unavailable_items = [
                    detail.get("product_id")
                    for detail in check_result.get("details", [])
                    if not detail.get("in_stock", False)
                ]
                error_message = f"Insufficient stock for items: {', '.join(unavailable_items)}"
                logger.warning(f"Order rejected: {error_message}")

                order_id = str(uuid4())
                order = CreatedOrder(
                    order_id=order_id,
                    user_id=payload.user_id,
                    email=payload.email,
                    items=payload.items,
                    status="rejected",
                    created_at=datetime.now(UTC),
                )

                inventory_result = DownstreamResult(
                    success=False,
                    service="inventory-service",
                    message=error_message,
                    data=check_result,
                )

                email_result = DownstreamResult(
                    success=False,
                    service="email-service",
                    message="Order rejected due to insufficient stock",
                    data={"reason": "stock_unavailable"},
                )

                ORDERS[order.order_id] = order
                return CreateOrderResponse(
                    order=order,
                    email_service=email_result,
                    inventory_service=inventory_result,
                )
        except Exception as exc:
            logger.warning(
                f"Stock availability check failed: {exc}, proceeding with order creation"
            )
    
    order_id = str(uuid4())
    created_at = datetime.now(UTC)

    order = CreatedOrder(
        order_id=order_id,
        user_id=payload.user_id,
        email=payload.email,
        items=payload.items,
        status="created",
        created_at=created_at,
    )

    if kafka_enabled():
        return _create_order_with_kafka(order)

    email_result = _run_email_confirmation(order)
    inventory_result = _run_inventory_reduction(order)

    if email_result.success and inventory_result.success:
        order.status = "processed"
    else:
        order.status = "partial-failure"

    ORDERS[order.order_id] = order

    return CreateOrderResponse(
        order=order,
        email_service=email_result,
        inventory_service=inventory_result,
    )


def _create_order_with_kafka(order: CreatedOrder) -> CreateOrderResponse:
    fallback_sync = _kafka_fallback_sync_enabled()
    reservation = _reserve_inventory_for_order(order)

    if reservation is not None and not reservation["success"]:
        order.status = "rejected"
        inventory_result = DownstreamResult(
            success=False,
            service="inventory-service",
            message=reservation["message"],
            data=reservation,
        )
        email_result = DownstreamResult(
            success=False,
            service="email-service",
            message="Order rejected due to insufficient stock",
            data={"reason": "stock_unavailable"},
        )
        ORDERS[order.order_id] = order
        return CreateOrderResponse(
            order=order,
            email_service=email_result,
            inventory_service=inventory_result,
        )

    try:
        if reservation is not None:
            publish_meta = publish_order_created(
                order,
                inventory_reservation=reservation["event"],
            )
        else:
            publish_meta = publish_order_created(order)
    except Exception as exc:
        if reservation is not None and reservation["success"]:
            _release_inventory_reservation(order, reservation)

        if not fallback_sync:
            failure_message = f"Kafka publish failed: {exc}"
            order.status = "partial-failure"
            failure_data = {"mode": "kafka", "error": str(exc)}
            email_result = DownstreamResult(
                success=False,
                service="email-service",
                message=failure_message,
                data=failure_data,
            )
            inventory_result = DownstreamResult(
                success=False,
                service="inventory-service",
                message=failure_message,
                data=failure_data,
            )
            ORDERS[order.order_id] = order
            return CreateOrderResponse(
                order=order,
                email_service=email_result,
                inventory_service=inventory_result,
            )

        email_result = _run_email_confirmation(order)
        inventory_result = _run_inventory_reduction(order)
        mode_data = {
            "mode": "sync-fallback",
            "kafka_error": str(exc),
        }
        email_result = _merge_result_data(email_result, mode_data)
        inventory_result = _merge_result_data(inventory_result, mode_data)

        if email_result.success and inventory_result.success:
            order.status = "processed"
        else:
            order.status = "partial-failure"

        ORDERS[order.order_id] = order
        return CreateOrderResponse(
            order=order,
            email_service=email_result,
            inventory_service=inventory_result,
        )

    order.status = "queued"
    queued_data = {
        "mode": "kafka",
        "event": publish_meta,
    }
    if reservation is not None and reservation["success"]:
        queued_data["inventory_reservation"] = reservation["event"]
    email_result = DownstreamResult(
        success=True,
        service="email-service",
        message="Order event queued for async email processing",
        data=queued_data,
    )
    inventory_result = DownstreamResult(
        success=True,
        service="inventory-service",
        message="Order event queued for async inventory processing",
        data=queued_data,
    )

    ORDERS[order.order_id] = order
    return CreateOrderResponse(
        order=order,
        email_service=email_result,
        inventory_service=inventory_result,
    )


def _run_email_confirmation(order: CreatedOrder) -> DownstreamResult:
    payload = {
        "order_id": order.order_id,
        "user_id": order.user_id,
        "email": str(order.email),
        "items": [item.model_dump() for item in order.items],
    }

    return _call_with_retry(
        service_name="email-service",
        call=lambda: email_client.confirm_order(payload),
    )


def _run_inventory_reduction(order: CreatedOrder) -> DownstreamResult:
    return _call_with_retry(
        service_name="inventory-service",
        call=lambda: inventory_client.reduce_stock(
            order_id=order.order_id,
            items=[item.model_dump() for item in order.items],
        ),
    )


def _call_with_retry(service_name: str, call: Callable[[], DownstreamResult]) -> DownstreamResult:
    max_retries = _get_int_env("DOWNSTREAM_MAX_RETRIES", 4, minimum=0)
    initial_backoff = _get_float_env("DOWNSTREAM_INITIAL_BACKOFF_SECONDS", 0.1, minimum=0.0)
    backoff_multiplier = _get_float_env("DOWNSTREAM_BACKOFF_MULTIPLIER", 2.0, minimum=1.0)
    max_backoff = _get_float_env("DOWNSTREAM_MAX_BACKOFF_SECONDS", 2.0, minimum=0.0)

    attempts_allowed = max_retries + 1
    current_backoff = min(initial_backoff, max_backoff)
    last_error = "unknown error"

    for attempt in range(1, attempts_allowed + 1):
        try:
            result = call()
            result_data = dict(result.data or {})
            result_data["attempts"] = attempt
            api_calls_total.labels(service=service_name, status="success").inc()
            return DownstreamResult(
                success=result.success,
                service=result.service,
                message=result.message,
                data=result_data,
            )
        except Exception as exc:
            last_error = str(exc)
            if attempt == attempts_allowed:
                break
            if current_backoff > 0:
                sleep(current_backoff)
            current_backoff = min(current_backoff * backoff_multiplier, max_backoff)

    api_calls_total.labels(service=service_name, status="failure").inc()
    return DownstreamResult(
        success=False,
        service=service_name,
        message=(
            f"{service_name} call failed after {attempts_allowed} attempts. "
            f"Last error: {last_error}"
        ),
        data={"attempts": attempts_allowed, "last_error": last_error},
    )


def _get_int_env(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else minimum


def _get_float_env(name: str, default: float, minimum: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= minimum else minimum


def _kafka_fallback_sync_enabled() -> bool:
    raw = os.getenv("KAFKA_FALLBACK_SYNC", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _inventory_http_precheck_enabled() -> bool:
    raw = os.getenv("INVENTORY_HTTP_PRECHECK_ENABLED", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _inventory_redis_reservation_enabled() -> bool:
    raw = os.getenv("INVENTORY_REDIS_RESERVATION_ENABLED", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _merge_result_data(result: DownstreamResult, extra_data: dict) -> DownstreamResult:
    merged = dict(result.data or {})
    merged.update(extra_data)
    return DownstreamResult(
        success=result.success,
        service=result.service,
        message=result.message,
        data=merged,
    )


def _reserve_inventory_for_order(order: CreatedOrder) -> dict | None:
    if not (
        _inventory_redis_reservation_enabled()
        and is_redis_enabled()
        and should_prefer_cache()
    ):
        return None

    redis_client = get_redis_client()
    reserved_results: list[dict] = []

    try:
        if not redis_client.is_connected():
            return _reservation_failure(
                order=order,
                message="Inventory reservation failed because Redis is not connected",
                results=[],
            )

        for item in order.items:
            success, remaining = redis_client.check_and_reserve_stock(
                item.product_id,
                item.quantity,
            )
            if success:
                available_before = remaining + item.quantity
                result = {
                    "product_id": item.product_id,
                    "requested": item.quantity,
                    "reduced": item.quantity,
                    "remaining": remaining,
                    "reason": None,
                }
                reserved_results.append(result)
                logger.info(
                    "Order reserved inventory in Redis order_id=%s product_id=%s requested=%s available_before=%s remaining=%s",
                    order.order_id,
                    item.product_id,
                    item.quantity,
                    available_before,
                    remaining,
                )
                continue

            _release_reserved_results(reserved_results)
            result = {
                "product_id": item.product_id,
                "requested": item.quantity,
                "reduced": 0,
                "remaining": remaining,
                "reason": "insufficient_stock",
            }
            logger.warning(
                "Order rejected by Redis reservation order_id=%s product_id=%s requested=%s available=%s",
                order.order_id,
                item.product_id,
                item.quantity,
                remaining,
            )
            return _reservation_failure(
                order=order,
                message=f"Insufficient stock for items: {item.product_id}",
                results=[*reserved_results, result],
            )
    except Exception as exc:
        _release_reserved_results(reserved_results)
        logger.exception("Inventory reservation failed order_id=%s", order.order_id)
        return _reservation_failure(
            order=order,
            message=f"Inventory reservation failed: {exc}",
            results=reserved_results,
        )

    event = {
        "stock_reserved": True,
        "source": "order-service-redis",
        "results": reserved_results,
    }
    return {
        "success": True,
        "message": "Stock reserved in Redis",
        "order_id": order.order_id,
        "event": event,
        "results": reserved_results,
    }


def _reservation_failure(order: CreatedOrder, message: str, results: list[dict]) -> dict:
    return {
        "success": False,
        "message": message,
        "order_id": order.order_id,
        "event": None,
        "results": results,
    }


def _release_inventory_reservation(order: CreatedOrder, reservation: dict) -> None:
    released = _release_reserved_results(reservation.get("results", []))
    logger.warning(
        "Released Redis inventory reservation after Kafka publish failure order_id=%s released=%s",
        order.order_id,
        released,
    )


def _release_reserved_results(results: list[dict]) -> list[dict]:
    redis_client = get_redis_client()
    released = []
    for result in results:
        reduced = int(result.get("reduced") or 0)
        if reduced <= 0:
            continue
        product_id = result["product_id"]
        remaining = redis_client.increase_stock(product_id, reduced)
        released.append(
            {
                "product_id": product_id,
                "released": reduced,
                "remaining": remaining,
            }
        )
    return released



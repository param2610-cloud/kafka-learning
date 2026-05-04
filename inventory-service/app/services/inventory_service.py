import random
import os
from time import sleep

from fastapi import HTTPException
from prometheus_client import Counter

from app.models.schemas import (
    FailureModeStatus,
    FailureModeUpdate,
    ReduceStockRequest,
    ReduceStockResponse,
    ReduceStockResult,
)

# Metrics for API calls (sync mode)
api_calls_total = Counter(
    'api_calls_total',
    'Total API calls received and processed by inventory service',
    ['endpoint', 'status']
)

# In-memory stock map for MVP.
STOCK: dict[str, int] = {
    "pencil": 100,
    "notebook": 50,
    "eraser": 75,
}
FAILURE_MODE: dict[str, bool | str | float] = {
    "enabled": False,
    "mode": "error",
    "error_rate": 1.0,
    "delay_seconds": 0.0,
}


def reduce_stock(payload: ReduceStockRequest) -> ReduceStockResponse:
    _simulate_db_call()
    _apply_failure_mode()

    # Check for special email trigger product
    has_special_trigger = any(
        item.product_id == "SPECIAL-EMAIL-TRIGGER"
        for item in payload.items
    )

    results: list[ReduceStockResult] = []

    for item in payload.items:
        current = STOCK.get(item.product_id, 0)
        if current >= item.quantity:
            STOCK[item.product_id] = current - item.quantity
            results.append(
                ReduceStockResult(
                    product_id=item.product_id,
                    requested=item.quantity,
                    reduced=item.quantity,
                    remaining=STOCK[item.product_id],
                    reason=None,
                )
            )
        else:
            results.append(
                ReduceStockResult(
                    product_id=item.product_id,
                    requested=item.quantity,
                    reduced=0,
                    remaining=current,
                    reason="insufficient_stock",
                )
            )

    success = all(result.reduced == result.requested for result in results)
    message = "Stock reduced" if success else "Some items could not be reduced"

    if has_special_trigger:
        # Log special inventory trigger for immediate visibility
        import logging
        logger = logging.getLogger("uvicorn.error")
        logger.info(f"[SPECIAL INVENTORY TRIGGER] Immediate stock update processed for SPECIAL-EMAIL-TRIGGER")

    api_calls_total.labels(endpoint="reduce-stock", status="success" if success else "failure").inc()

    return ReduceStockResponse(success=success, message=message, results=results)


def get_stock() -> dict[str, int]:
    return STOCK


def update_failure_mode(config: FailureModeUpdate) -> FailureModeStatus:
    FAILURE_MODE["enabled"] = config.enabled
    FAILURE_MODE["mode"] = config.mode
    FAILURE_MODE["error_rate"] = config.error_rate
    FAILURE_MODE["delay_seconds"] = config.delay_seconds
    return get_failure_mode()


def get_failure_mode() -> FailureModeStatus:
    return FailureModeStatus(
        service="inventory-service",
        enabled=bool(FAILURE_MODE["enabled"]),
        mode=str(FAILURE_MODE["mode"]),
        error_rate=float(FAILURE_MODE["error_rate"]),
        delay_seconds=float(FAILURE_MODE["delay_seconds"]),
    )


def _apply_failure_mode() -> None:
    if not bool(FAILURE_MODE["enabled"]):
        return

    mode = str(FAILURE_MODE["mode"])
    delay_seconds = float(FAILURE_MODE["delay_seconds"])

    if mode == "delay" and delay_seconds > 0:
        sleep(delay_seconds)
        return

    if mode == "error":
        error_rate = float(FAILURE_MODE["error_rate"])
        if random.random() <= error_rate:
            raise HTTPException(status_code=503, detail="Simulated inventory service failure")


def _simulate_db_call() -> None:
    delay_seconds = _db_call_delay_seconds()
    if delay_seconds > 0:
        import logging
        logger = logging.getLogger("uvicorn.error")
        logger.info(f"[INVENTORY_SERVICE] Simulating DB call with {delay_seconds}s delay")
        sleep(delay_seconds)


def _db_call_delay_seconds() -> float:
    raw = os.getenv("INVENTORY_DB_CALL_DELAY_SECONDS", "0")
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value if value > 0 else 0.0

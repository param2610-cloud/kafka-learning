import random
from datetime import UTC, datetime
from time import sleep
from uuid import uuid4

from fastapi import HTTPException

from app.models.schemas import (
    ConfirmOrderRequest,
    ConfirmOrderResponse,
    FailureModeStatus,
    FailureModeUpdate,
)

SENT_CONFIRMATIONS: list[dict] = []
FAILURE_MODE: dict[str, bool | str | float] = {
    "enabled": False,
    "mode": "error",
    "error_rate": 1.0,
    "delay_seconds": 0.0,
}


def confirm_order(payload: ConfirmOrderRequest) -> ConfirmOrderResponse:
    _apply_failure_mode()

    confirmation_id = str(uuid4())
    sent_at = datetime.now(UTC)

    SENT_CONFIRMATIONS.append(
        {
            "confirmation_id": confirmation_id,
            "order_id": payload.order_id,
            "email": str(payload.email),
            "sent_at": sent_at,
        }
    )

    return ConfirmOrderResponse(
        success=True,
        message="Order confirmation email sent",
        confirmation_id=confirmation_id,
        sent_at=sent_at,
    )


def update_failure_mode(config: FailureModeUpdate) -> FailureModeStatus:
    FAILURE_MODE["enabled"] = config.enabled
    FAILURE_MODE["mode"] = config.mode
    FAILURE_MODE["error_rate"] = config.error_rate
    FAILURE_MODE["delay_seconds"] = config.delay_seconds
    return get_failure_mode()


def get_failure_mode() -> FailureModeStatus:
    return FailureModeStatus(
        service="email-service",
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
            raise HTTPException(status_code=503, detail="Simulated email service failure")

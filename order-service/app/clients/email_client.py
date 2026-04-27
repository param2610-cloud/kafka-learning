import os

import httpx

from app.models.schemas import DownstreamResult


EMAIL_SERVICE_URL = os.getenv("EMAIL_SERVICE_URL", "http://localhost:8001")


def _timeout_seconds() -> float:
    raw = os.getenv("DOWNSTREAM_REQUEST_TIMEOUT_SECONDS", "2")
    try:
        value = float(raw)
    except ValueError:
        return 2.0
    return value if value > 0 else 2.0


def confirm_order(order_payload: dict) -> DownstreamResult:
    url = f"{EMAIL_SERVICE_URL}/confirm-order"
    with httpx.Client(timeout=_timeout_seconds()) as client:
        response = client.post(url, json=order_payload)
        response.raise_for_status()
        payload = response.json()

    return DownstreamResult(
        success=True,
        service="email-service",
        message="Order confirmation sent",
        data=payload,
    )

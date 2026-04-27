import os

import httpx

from app.models.schemas import DownstreamResult


INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8002")


def _timeout_seconds() -> float:
    raw = os.getenv("DOWNSTREAM_REQUEST_TIMEOUT_SECONDS", "2")
    try:
        value = float(raw)
    except ValueError:
        return 2.0
    return value if value > 0 else 2.0


def reduce_stock(order_id: str, items: list[dict]) -> DownstreamResult:
    url = f"{INVENTORY_SERVICE_URL}/reduce-stock"
    payload = {"order_id": order_id, "items": items}

    with httpx.Client(timeout=_timeout_seconds()) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    return DownstreamResult(
        success=bool(data.get("success", False)),
        service="inventory-service",
        message=data.get("message", "Inventory updated"),
        data=data,
    )

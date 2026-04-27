from fastapi.testclient import TestClient
import pytest

from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_failure_mode():
    payload = {
        "enabled": False,
        "mode": "error",
        "error_rate": 1.0,
        "delay_seconds": 0,
    }
    client.post("/failure-mode", json=payload)
    yield
    client.post("/failure-mode", json=payload)


def test_reduce_stock_success():
    response = client.post(
        "/reduce-stock",
        json={
            "order_id": "o-1",
            "items": [{"product_id": "pencil", "quantity": 2}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True


def test_reduce_stock_insufficient():
    response = client.post(
        "/reduce-stock",
        json={
            "order_id": "o-2",
            "items": [{"product_id": "unknown-item", "quantity": 10}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["results"][0]["reason"] == "insufficient_stock"


def test_reduce_stock_with_simulated_failure():
    client.post(
        "/failure-mode",
        json={
            "enabled": True,
            "mode": "error",
            "error_rate": 1.0,
            "delay_seconds": 0,
        },
    )

    response = client.post(
        "/reduce-stock",
        json={
            "order_id": "o-3",
            "items": [{"product_id": "pencil", "quantity": 1}],
        },
    )

    assert response.status_code == 503

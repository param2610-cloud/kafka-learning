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


def test_confirm_order():
    response = client.post(
        "/confirm-order",
        json={
            "order_id": "o-1",
            "user_id": "u-1",
            "email": "user@example.com",
            "items": [{"product_id": "pencil", "quantity": 1}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["confirmation_id"]


def test_confirm_order_with_simulated_failure():
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
        "/confirm-order",
        json={
            "order_id": "o-2",
            "user_id": "u-2",
            "email": "user2@example.com",
            "items": [{"product_id": "pencil", "quantity": 1}],
        },
    )

    assert response.status_code == 503

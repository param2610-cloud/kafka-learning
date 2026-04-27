from fastapi.testclient import TestClient

from app.models.schemas import DownstreamResult
from main import app

client = TestClient(app)


def test_create_order_success(monkeypatch):
    monkeypatch.setenv("DOWNSTREAM_MAX_RETRIES", "0")
    monkeypatch.setenv("DOWNSTREAM_INITIAL_BACKOFF_SECONDS", "0")

    def fake_confirm_order(order_payload):
        return DownstreamResult(
            success=True,
            service="email-service",
            message="ok",
            data={"confirmation_id": "c-1"},
        )

    def fake_reduce_stock(order_id, items):
        return DownstreamResult(
            success=True,
            service="inventory-service",
            message="ok",
            data={"success": True},
        )

    monkeypatch.setattr("app.clients.email_client.confirm_order", fake_confirm_order)
    monkeypatch.setattr("app.clients.inventory_client.reduce_stock", fake_reduce_stock)

    response = client.post(
        "/orders",
        json={
            "user_id": "u-1",
            "email": "user@example.com",
            "items": [{"product_id": "pencil", "quantity": 2}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "processed"
    assert payload["email_service"]["success"] is True
    assert payload["inventory_service"]["success"] is True


def test_create_order_partial_failure(monkeypatch):
    monkeypatch.setenv("DOWNSTREAM_MAX_RETRIES", "1")
    monkeypatch.setenv("DOWNSTREAM_INITIAL_BACKOFF_SECONDS", "0")

    def broken_confirm_order(order_payload):
        raise RuntimeError("email unavailable")

    def fake_reduce_stock(order_id, items):
        return DownstreamResult(
            success=True,
            service="inventory-service",
            message="ok",
            data={"success": True},
        )

    monkeypatch.setattr("app.clients.email_client.confirm_order", broken_confirm_order)
    monkeypatch.setattr("app.clients.inventory_client.reduce_stock", fake_reduce_stock)

    response = client.post(
        "/orders",
        json={
            "user_id": "u-2",
            "email": "user2@example.com",
            "items": [{"product_id": "notebook", "quantity": 1}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "partial-failure"
    assert payload["email_service"]["success"] is False
    assert payload["email_service"]["data"]["attempts"] == 2
    assert payload["inventory_service"]["success"] is True


def test_create_order_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("DOWNSTREAM_MAX_RETRIES", "3")
    monkeypatch.setenv("DOWNSTREAM_INITIAL_BACKOFF_SECONDS", "0")

    attempts = {"count": 0}

    def flaky_confirm_order(order_payload):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary email outage")
        return DownstreamResult(
            success=True,
            service="email-service",
            message="ok",
            data={"confirmation_id": "c-2"},
        )

    def fake_reduce_stock(order_id, items):
        return DownstreamResult(
            success=True,
            service="inventory-service",
            message="ok",
            data={"success": True},
        )

    monkeypatch.setattr("app.clients.email_client.confirm_order", flaky_confirm_order)
    monkeypatch.setattr("app.clients.inventory_client.reduce_stock", fake_reduce_stock)

    response = client.post(
        "/orders",
        json={
            "user_id": "u-3",
            "email": "user3@example.com",
            "items": [{"product_id": "pencil", "quantity": 1}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert attempts["count"] == 3
    assert payload["order"]["status"] == "processed"
    assert payload["email_service"]["success"] is True
    assert payload["email_service"]["data"]["attempts"] == 3

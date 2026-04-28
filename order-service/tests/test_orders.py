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


def test_create_order_kafka_queued(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_FALLBACK_SYNC", "false")

    def fake_publish_order_created(order):
        return {
            "event_id": "evt-1",
            "topic": "orders.created",
            "partition": 0,
            "offset": 12,
        }

    def should_not_call_sync_path(*args, **kwargs):
        raise AssertionError("Synchronous downstream call should not execute when Kafka publish succeeds")

    monkeypatch.setattr("app.services.order_service.publish_order_created", fake_publish_order_created)
    monkeypatch.setattr("app.clients.email_client.confirm_order", should_not_call_sync_path)
    monkeypatch.setattr("app.clients.inventory_client.reduce_stock", should_not_call_sync_path)

    response = client.post(
        "/orders",
        json={
            "user_id": "u-kafka-1",
            "email": "kafka1@example.com",
            "items": [{"product_id": "pencil", "quantity": 1}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "queued"
    assert payload["email_service"]["success"] is True
    assert payload["inventory_service"]["success"] is True
    assert payload["email_service"]["data"]["mode"] == "kafka"
    assert payload["email_service"]["data"]["event"]["event_id"] == "evt-1"


def test_create_order_kafka_publish_failure_without_fallback(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_FALLBACK_SYNC", "false")

    def broken_publish_order_created(order):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr("app.services.order_service.publish_order_created", broken_publish_order_created)

    response = client.post(
        "/orders",
        json={
            "user_id": "u-kafka-2",
            "email": "kafka2@example.com",
            "items": [{"product_id": "notebook", "quantity": 1}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "partial-failure"
    assert payload["email_service"]["success"] is False
    assert payload["inventory_service"]["success"] is False
    assert payload["email_service"]["data"]["mode"] == "kafka"
    assert "broker unavailable" in payload["email_service"]["data"]["error"]


def test_create_order_kafka_publish_failure_with_sync_fallback(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_FALLBACK_SYNC", "true")
    monkeypatch.setenv("DOWNSTREAM_MAX_RETRIES", "0")
    monkeypatch.setenv("DOWNSTREAM_INITIAL_BACKOFF_SECONDS", "0")

    def broken_publish_order_created(order):
        raise RuntimeError("temporary broker outage")

    def fake_confirm_order(order_payload):
        return DownstreamResult(
            success=True,
            service="email-service",
            message="ok",
            data={"confirmation_id": "c-fallback"},
        )

    def fake_reduce_stock(order_id, items):
        return DownstreamResult(
            success=True,
            service="inventory-service",
            message="ok",
            data={"success": True},
        )

    monkeypatch.setattr("app.services.order_service.publish_order_created", broken_publish_order_created)
    monkeypatch.setattr("app.clients.email_client.confirm_order", fake_confirm_order)
    monkeypatch.setattr("app.clients.inventory_client.reduce_stock", fake_reduce_stock)

    response = client.post(
        "/orders",
        json={
            "user_id": "u-kafka-3",
            "email": "kafka3@example.com",
            "items": [{"product_id": "eraser", "quantity": 2}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "processed"
    assert payload["email_service"]["success"] is True
    assert payload["inventory_service"]["success"] is True
    assert payload["email_service"]["data"]["mode"] == "sync-fallback"
    assert payload["inventory_service"]["data"]["mode"] == "sync-fallback"
    assert "temporary broker outage" in payload["email_service"]["data"]["kafka_error"]

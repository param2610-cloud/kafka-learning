from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


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



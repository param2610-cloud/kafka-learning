from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
import httpx

from app.models.schemas import RunDetails, StartRunRequest, StartRunResponse, StopRunResponse
from app.services import runner

router = APIRouter(prefix="/api", tags=["orchestrator"])

# Inventory service URL
INVENTORY_SERVICE_URL = "http://inventory-service:8002"


class SpecialOrderRequest(BaseModel):
    user_id: str
    email: str
    product_id: str = "pencil"
    quantity: int = 1


class SetStockRequest(BaseModel):
    pencil: int = 100
    notebook: int = 50
    eraser: int = 75


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "load-orchestrator", "status": "ok"}


@router.get("/stock")
def get_stock() -> dict:
    """Get current stock from inventory service"""
    try:
        response = httpx.get(
            f"{INVENTORY_SERVICE_URL}/stock",
            timeout=5.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stock: {str(e)}")


@router.post("/stock")
def set_stock(payload: SetStockRequest) -> dict:
    """Initialize/Set stock in inventory service"""
    try:
        # Get previous stock first
        try:
            prev_response = httpx.get(
                f"{INVENTORY_SERVICE_URL}/stock",
                timeout=5.0
            )
            prev_response.raise_for_status()
            previous_stock = prev_response.json()
        except:
            previous_stock = {}
        
        # Set new stock
        stock_data = {
            "pencil": payload.pencil,
            "notebook": payload.notebook,
            "eraser": payload.eraser,
        }
        
        response = httpx.post(
            f"{INVENTORY_SERVICE_URL}/stock",
            json=stock_data,
            timeout=5.0
        )
        response.raise_for_status()
        new_stock = response.json()
        
        return {
            "message": "Stock initialized successfully",
            "previous": previous_stock,
            "current": new_stock
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set stock: {str(e)}")


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "load-orchestrator", "status": "ok"}


@router.post("/runs", response_model=StartRunResponse)
def start_run(payload: StartRunRequest) -> StartRunResponse:
    summary = runner.start_run(payload)
    return StartRunResponse(run=summary, message="k6 run started")


@router.get("/runs")
def list_runs() -> dict[str, list]:
    return {"runs": runner.list_runs()}


@router.get("/runs/{run_id}", response_model=RunDetails)
def get_run(run_id: str) -> RunDetails:
    details = runner.get_run_status(run_id)
    if not details:
        raise HTTPException(status_code=404, detail="run not found")
    return RunDetails(**details)


@router.delete("/runs/{run_id}", response_model=StopRunResponse)
def stop_run(run_id: str) -> StopRunResponse:
    stopped = runner.stop_run(run_id)
    if not stopped:
        raise HTTPException(status_code=404, detail="run not found")
    return StopRunResponse(run_id=run_id, status="stopped", message="run stopped")


@router.post("/special-order")
def special_order(payload: SpecialOrderRequest):
    """Trigger a special order with specified product and quantity."""
    import httpx

    order_payload = {
        "user_id": payload.user_id,
        "email": payload.email,
        "items": [
            {"product_id": payload.product_id, "quantity": payload.quantity}
        ]
    }

    try:
        response = httpx.post(
            "http://order-service:8000/orders",
            json=order_payload,
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger special order: {str(e)}")


@router.get("/special", response_class=HTMLResponse)
def special_order_page():
    """Serve a simple HTML form to trigger special orders."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Special Order Trigger</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input[type="text"], input[type="email"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
            button { background-color: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
            button:hover { background-color: #0056b3; }
            .result { margin-top: 20px; padding: 15px; border-radius: 4px; }
            .success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Special Order Trigger</h1>
            <p>Trigger a special order with SPECIAL-EMAIL-TRIGGER product to send immediate email confirmation.</p>
            <div class="form-group">
                <label for="user_id">User ID:</label>
                <input type="text" id="user_id" placeholder="Enter user ID" />
            </div>
            <div class="form-group">
                <label for="email">Email:</label>
                <input type="email" id="email" placeholder="Enter email address" />
            </div>
            <button onclick="triggerSpecialOrder()">Trigger Special Order</button>
            <div id="result"></div>
        </div>

        <script>
            async function triggerSpecialOrder() {
                const userId = document.getElementById('user_id').value.trim();
                const email = document.getElementById('email').value.trim();
                const resultDiv = document.getElementById('result');

                if (!userId || !email) {
                    resultDiv.innerHTML = '<div class="result error">Please fill in both User ID and Email</div>';
                    return;
                }

                resultDiv.innerHTML = '<div class="result">Triggering special order...</div>';

                try {
                    const response = await fetch('/api/special-order', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ user_id: userId, email: email })
                    });

                    if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.detail || 'Failed to trigger special order');
                    }

                    const data = await response.json();
                    resultDiv.innerHTML = `
                        <div class="result success">
                            <h3>Special Order Triggered Successfully!</h3>
                            <p><strong>Order ID:</strong> ${data.order.order_id}</p>
                            <p><strong>Status:</strong> ${data.order.status}</p>
                            <p><strong>Email Service:</strong> ${data.email_service.message}</p>
                        </div>
                    `;
                } catch (error) {
                    resultDiv.innerHTML = `<div class="result error">Error: ${error.message}</div>`;
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

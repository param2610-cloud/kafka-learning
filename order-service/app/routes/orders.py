from fastapi import APIRouter

from app.models.schemas import CreateOrderRequest, CreateOrderResponse
from app.services.order_service import create_order

router = APIRouter(tags=["orders"])


@router.post("/orders", response_model=CreateOrderResponse)
def create_order_endpoint(payload: CreateOrderRequest) -> CreateOrderResponse:
    return create_order(payload)

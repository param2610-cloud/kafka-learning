from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class OrderItem(BaseModel):
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)


class CreateOrderRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    email: EmailStr
    items: list[OrderItem] = Field(..., min_length=1)


class DownstreamResult(BaseModel):
    success: bool
    service: str
    message: str
    data: dict | None = None


class CreatedOrder(BaseModel):
    order_id: str
    user_id: str
    email: EmailStr
    items: list[OrderItem]
    status: str
    created_at: datetime


class CreateOrderResponse(BaseModel):
    order: CreatedOrder
    email_service: DownstreamResult
    inventory_service: DownstreamResult

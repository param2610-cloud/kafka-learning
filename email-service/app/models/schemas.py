from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class OrderItem(BaseModel):
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)


class ConfirmOrderRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    email: EmailStr
    items: list[OrderItem] = Field(..., min_length=1)


class ConfirmOrderResponse(BaseModel):
    success: bool
    message: str
    confirmation_id: str
    sent_at: datetime


class FailureModeUpdate(BaseModel):
    enabled: bool = False
    mode: Literal["error", "delay"] = "error"
    error_rate: float = Field(1.0, ge=0.0, le=1.0)
    delay_seconds: float = Field(0.0, ge=0.0, le=30.0)


class FailureModeStatus(FailureModeUpdate):
    service: str

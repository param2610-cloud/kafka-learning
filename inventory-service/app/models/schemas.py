from typing import Literal

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)


class ReduceStockRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
    items: list[OrderItem] = Field(..., min_length=1)


class ReduceStockResult(BaseModel):
    product_id: str
    requested: int
    reduced: int
    remaining: int
    reason: str | None = None


class ReduceStockResponse(BaseModel):
    success: bool
    message: str
    results: list[ReduceStockResult]


class FailureModeUpdate(BaseModel):
    enabled: bool = False
    mode: Literal["error", "delay"] = "error"
    error_rate: float = Field(1.0, ge=0.0, le=1.0)
    delay_seconds: float = Field(0.0, ge=0.0, le=30.0)


class FailureModeStatus(FailureModeUpdate):
    service: str

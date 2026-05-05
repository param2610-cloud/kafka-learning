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


class CheckStockAvailabilityRequest(BaseModel):
    items: list[OrderItem] = Field(..., min_length=1)


class CheckStockAvailabilityResponse(BaseModel):
    available: bool
    message: str
    details: list[dict] = Field(default_factory=list)



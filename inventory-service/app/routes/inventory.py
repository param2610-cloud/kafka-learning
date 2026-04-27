import os

from fastapi import APIRouter

from app.models.schemas import (
    FailureModeStatus,
    FailureModeUpdate,
    ReduceStockRequest,
    ReduceStockResponse,
)
from app.services.inventory_service import (
    get_failure_mode,
    get_stock,
    reduce_stock,
    update_failure_mode,
)

router = APIRouter(tags=["inventory"])


@router.post("/reduce-stock", response_model=ReduceStockResponse)
def reduce_stock_endpoint(payload: ReduceStockRequest) -> ReduceStockResponse:
    return reduce_stock(payload)


@router.get("/stock")
def get_stock_endpoint() -> dict[str, int]:
    return get_stock()


@router.get("/failure-mode", response_model=FailureModeStatus)
def get_failure_mode_endpoint() -> FailureModeStatus:
    return get_failure_mode()


@router.post("/failure-mode", response_model=FailureModeStatus)
def update_failure_mode_endpoint(payload: FailureModeUpdate) -> FailureModeStatus:
    return update_failure_mode(payload)


@router.post("/simulate-crash")
def simulate_crash_endpoint() -> dict[str, str]:
    os._exit(1)

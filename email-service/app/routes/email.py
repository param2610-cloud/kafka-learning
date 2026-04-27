import os

from fastapi import APIRouter

from app.models.schemas import (
    ConfirmOrderRequest,
    ConfirmOrderResponse,
    FailureModeStatus,
    FailureModeUpdate,
)
from app.services.email_service import confirm_order, get_failure_mode, update_failure_mode

router = APIRouter(tags=["email"])


@router.post("/confirm-order", response_model=ConfirmOrderResponse)
def confirm_order_endpoint(payload: ConfirmOrderRequest) -> ConfirmOrderResponse:
    return confirm_order(payload)


@router.get("/failure-mode", response_model=FailureModeStatus)
def get_failure_mode_endpoint() -> FailureModeStatus:
    return get_failure_mode()


@router.post("/failure-mode", response_model=FailureModeStatus)
def update_failure_mode_endpoint(payload: FailureModeUpdate) -> FailureModeStatus:
    return update_failure_mode(payload)


@router.post("/simulate-crash")
def simulate_crash_endpoint() -> dict[str, str]:
    os._exit(1)

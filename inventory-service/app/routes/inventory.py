import os

from fastapi import APIRouter
from pydantic import BaseModel

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
    initialize_stock,
)
from app.config.feature_flags import get_feature_flags, update_feature_flags, FeatureFlags

router = APIRouter(tags=["inventory"])


class FeatureFlagsResponse(BaseModel):
    redis_cache_enabled: bool
    redis_prefer_cache: bool


class SetStockRequest(BaseModel):
    pencil: int = 100
    notebook: int = 50
    eraser: int = 75


@router.post("/reduce-stock", response_model=ReduceStockResponse)
def reduce_stock_endpoint(payload: ReduceStockRequest) -> ReduceStockResponse:
    return reduce_stock(payload)


@router.get("/stock")
def get_stock_endpoint() -> dict[str, int]:
    return get_stock()


@router.post("/stock")
def set_stock_endpoint(payload: SetStockRequest) -> dict[str, int]:
    """Initialize/Set stock levels"""
    stock_data = {
        "pencil": payload.pencil,
        "notebook": payload.notebook,
        "eraser": payload.eraser,
    }
    return initialize_stock(stock_data)


@router.get("/failure-mode", response_model=FailureModeStatus)
def get_failure_mode_endpoint() -> FailureModeStatus:
    return get_failure_mode()


@router.post("/failure-mode", response_model=FailureModeStatus)
def update_failure_mode_endpoint(payload: FailureModeUpdate) -> FailureModeStatus:
    return update_failure_mode(payload)


@router.get("/feature-flags", response_model=FeatureFlagsResponse)
def get_feature_flags_endpoint() -> FeatureFlagsResponse:
    """Get current feature flags status"""
    flags = get_feature_flags()
    return FeatureFlagsResponse(
        redis_cache_enabled=flags.redis_cache_enabled,
        redis_prefer_cache=flags.redis_prefer_cache,
    )


@router.post("/feature-flags", response_model=FeatureFlagsResponse)
def update_feature_flags_endpoint(payload: FeatureFlagsResponse) -> FeatureFlagsResponse:
    """Update feature flags at runtime"""
    flags = FeatureFlags(**payload.dict())
    updated = update_feature_flags(flags)
    return FeatureFlagsResponse(
        redis_cache_enabled=updated.redis_cache_enabled,
        redis_prefer_cache=updated.redis_prefer_cache,
    )


@router.post("/simulate-crash")
def simulate_crash_endpoint() -> dict[str, str]:
    os._exit(1)

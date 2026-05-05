from fastapi import APIRouter
from pydantic import BaseModel

from app.config.feature_flags import (
    get_feature_flags,
    update_feature_flags,
    FeatureFlags,
)

router = APIRouter(tags=["config"])


class FeatureFlagsResponse(BaseModel):
    redis_cache_enabled: bool
    redis_prefer_cache: bool


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

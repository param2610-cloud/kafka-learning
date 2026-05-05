import os
from pydantic import BaseModel


class FeatureFlags(BaseModel):
    """Feature flags configuration"""

    redis_cache_enabled: bool
    redis_prefer_cache: bool = True

    class Config:
        frozen = True


# Global feature flags state
_feature_flags: dict[str, bool] = {
    "redis_cache_enabled": os.getenv("REDIS_ENABLED", "false").lower() == "true",
    "redis_prefer_cache": os.getenv("REDIS_PREFER_CACHE", "true").lower() == "true",
}


def get_feature_flags() -> FeatureFlags:
    """Get current feature flags"""
    return FeatureFlags(**_feature_flags)


def update_feature_flags(flags: FeatureFlags) -> FeatureFlags:
    """Update feature flags at runtime"""
    global _feature_flags
    _feature_flags["redis_cache_enabled"] = flags.redis_cache_enabled
    _feature_flags["redis_prefer_cache"] = flags.redis_prefer_cache
    return get_feature_flags()


def is_redis_enabled() -> bool:
    """Check if Redis cache is enabled"""
    return _feature_flags.get("redis_cache_enabled", False)


def should_prefer_cache() -> bool:
    """Check if cache should be preferred over DB"""
    return _feature_flags.get("redis_prefer_cache", True)

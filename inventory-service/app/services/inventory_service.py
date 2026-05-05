import os
from time import sleep
import logging

from prometheus_client import Counter

from app.models.schemas import (
    ReduceStockRequest,
    ReduceStockResponse,
    ReduceStockResult,
    CheckStockAvailabilityRequest,
    CheckStockAvailabilityResponse,
)
from app.cache.redis_client import get_redis_client
from app.config.feature_flags import is_redis_enabled, should_prefer_cache

logger = logging.getLogger("uvicorn.error")

# Metrics for API calls (sync mode)
api_calls_total = Counter(
    'api_calls_total',
    'Total API calls received and processed by inventory service',
    ['endpoint', 'status']
)

# In-memory stock map for MVP.
STOCK: dict[str, int] = {
    "pencil": 100,
    "notebook": 50,
    "eraser": 75,
}

# Track if Redis cache was initialized
_redis_initialized: bool = False


def _ensure_redis_initialized() -> None:
    """Initialize Redis cache with current stock data if enabled"""
    global _redis_initialized
    if not _redis_initialized and is_redis_enabled():
        try:
            redis_client = get_redis_client()
            if redis_client.is_connected():
                redis_client.initialize_stock(STOCK)
                _redis_initialized = True
                logger.info(f"Redis cache initialized with stock data: {STOCK}")
            else:
                logger.warning("Redis is enabled but not connected")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis: {e}")
            _redis_initialized = False
    elif not is_redis_enabled():
        logger.info("Redis is disabled")


def check_stock_availability(payload: CheckStockAvailabilityRequest) -> CheckStockAvailabilityResponse:
    """Check if all items are available before order creation"""
    _ensure_redis_initialized()
    
    # Use Redis if enabled and preferred, otherwise use database
    if is_redis_enabled() and should_prefer_cache():
        return _check_stock_availability_redis(payload)
    
    return _check_stock_availability_db(payload)


def _check_stock_availability_redis(payload: CheckStockAvailabilityRequest) -> CheckStockAvailabilityResponse:
    """Check stock availability using Redis"""
    redis_client = get_redis_client()
    details = []
    all_available = True
    
    try:
        for item in payload.items:
            stock = redis_client.get_stock(item.product_id)
            available = stock >= item.quantity
            details.append({
                "product_id": item.product_id,
                "requested": item.quantity,
                "available": stock,
                "in_stock": available,
            })
            if not available:
                all_available = False
        
        message = "All items in stock" if all_available else "Some items out of stock"
        api_calls_total.labels(endpoint="check-availability", status="success").inc()
        return CheckStockAvailabilityResponse(available=all_available, message=message, details=details)
    except Exception as e:
        logger.error(f"Redis stock check failed: {e}")
        # Fallback to database
        logger.info("Falling back to database for stock check")
        return _check_stock_availability_db(payload)


def _check_stock_availability_db(payload: CheckStockAvailabilityRequest) -> CheckStockAvailabilityResponse:
    """Check stock availability using in-memory database"""
    details = []
    all_available = True
    
    for item in payload.items:
        current = STOCK.get(item.product_id, 0)
        available = current >= item.quantity
        details.append({
            "product_id": item.product_id,
            "requested": item.quantity,
            "available": current,
            "in_stock": available,
        })
        if not available:
            all_available = False
    
    message = "All items in stock" if all_available else "Some items out of stock"
    logger.info(f"Stock check (DB): {message}, details={details}")
    api_calls_total.labels(endpoint="check-availability", status="success").inc()
    return CheckStockAvailabilityResponse(available=all_available, message=message, details=details)


def reduce_stock(payload: ReduceStockRequest) -> ReduceStockResponse:
    _ensure_redis_initialized()
    
    # If Redis is enabled and should be preferred, use it
    if is_redis_enabled() and should_prefer_cache():
        return _reduce_stock_redis(payload)
    
    # Otherwise use traditional database approach
    return _reduce_stock_db(payload)


def _reduce_stock_redis(payload: ReduceStockRequest) -> ReduceStockResponse:
    """Reduce stock using Redis cache"""
    has_special_trigger = any(
        item.product_id == "SPECIAL-EMAIL-TRIGGER"
        for item in payload.items
    )

    results: list[ReduceStockResult] = []
    redis_client = get_redis_client()

    try:
        for item in payload.items:
            success, remaining = redis_client.check_and_reserve_stock(
                item.product_id, item.quantity
            )
            
            if success:
                results.append(
                    ReduceStockResult(
                        product_id=item.product_id,
                        requested=item.quantity,
                        reduced=item.quantity,
                        remaining=remaining,
                        reason=None,
                    )
                )
            else:
                results.append(
                    ReduceStockResult(
                        product_id=item.product_id,
                        requested=item.quantity,
                        reduced=0,
                        remaining=remaining,
                        reason="insufficient_stock",
                    )
                )

        success_all = all(result.reduced == result.requested for result in results)
        message = "Stock reduced (Redis)" if success_all else "Some items could not be reduced (Redis)"

        if has_special_trigger:
            logger.info(
                f"[SPECIAL INVENTORY TRIGGER] Redis stock update for SPECIAL-EMAIL-TRIGGER"
            )

        api_calls_total.labels(
            endpoint="reduce-stock", status="success" if success_all else "failure"
        ).inc()

        return ReduceStockResponse(success=success_all, message=message, results=results)
    except Exception as e:
        logger.error(f"Redis stock reduction failed: {e}")
        # Fallback to database
        logger.info("Falling back to database for stock reduction")
        return _reduce_stock_db(payload)


def _reduce_stock_db(payload: ReduceStockRequest) -> ReduceStockResponse:
    """Reduce stock using in-memory database"""
    _simulate_db_call()

    # Check for special email trigger product
    has_special_trigger = any(
        item.product_id == "SPECIAL-EMAIL-TRIGGER"
        for item in payload.items
    )

    results: list[ReduceStockResult] = []

    for item in payload.items:
        current = STOCK.get(item.product_id, 0)
        if current >= item.quantity:
            STOCK[item.product_id] = current - item.quantity
            results.append(
                ReduceStockResult(
                    product_id=item.product_id,
                    requested=item.quantity,
                    reduced=item.quantity,
                    remaining=STOCK[item.product_id],
                    reason=None,
                )
            )
        else:
            results.append(
                ReduceStockResult(
                    product_id=item.product_id,
                    requested=item.quantity,
                    reduced=0,
                    remaining=current,
                    reason="insufficient_stock",
                )
            )

    success = all(result.reduced == result.requested for result in results)
    message = "Stock reduced" if success else "Some items could not be reduced"

    if has_special_trigger:
        logger.info(f"[SPECIAL INVENTORY TRIGGER] Database stock update for SPECIAL-EMAIL-TRIGGER")

    api_calls_total.labels(endpoint="reduce-stock", status="success" if success else "failure").inc()

    return ReduceStockResponse(success=success, message=message, results=results)


def get_stock() -> dict[str, int]:
    """Get stock from Redis (if enabled and preferred) or from database"""
    _ensure_redis_initialized()
    
    if is_redis_enabled() and should_prefer_cache():
        try:
            redis_client = get_redis_client()
            redis_stock = redis_client.get_all_stock()
            if redis_stock:
                logger.debug("Returning stock from Redis cache")
                return redis_stock
        except Exception as e:
            logger.warning(f"Failed to get stock from Redis: {e}")
    
    # Fallback to database
    return STOCK


def initialize_stock(stock_data: dict[str, int]) -> dict[str, int]:
    """Initialize stock levels in both database and Redis"""
    global STOCK
    global _redis_initialized
    
    # Update in-memory database
    STOCK.update(stock_data)
    logger.info(f"Stock initialized in database: {STOCK}")
    
    # Update Redis cache if enabled
    if is_redis_enabled():
        try:
            redis_client = get_redis_client()
            if redis_client.is_connected():
                redis_client.initialize_stock(stock_data)
                _redis_initialized = True
                logger.info(f"Stock initialized in Redis cache: {stock_data}")
        except Exception as e:
            logger.warning(f"Failed to initialize stock in Redis: {e}")
    
    return STOCK


def _simulate_db_call() -> None:
    delay_seconds = _db_call_delay_seconds()
    if delay_seconds > 0:
        import logging
        logger = logging.getLogger("uvicorn.error")
        logger.info(f"[INVENTORY_SERVICE] Simulating DB call with {delay_seconds}s delay")
        sleep(delay_seconds)


def _db_call_delay_seconds() -> float:
    raw = os.getenv("INVENTORY_DB_CALL_DELAY_SECONDS", "0")
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value if value > 0 else 0.0

import json
import logging
import os
from typing import Any, Optional

import redis

logger = logging.getLogger("uvicorn.error")


class RedisClient:
    """Redis cache client for managing inventory cache"""

    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.db = 0
        self.connection_pool = None
        self._redis = None

    def _get_client(self) -> redis.Redis:
        """Get or create redis client"""
        if self._redis is None:
            try:
                self._redis = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
                # Test connection
                self._redis.ping()
                logger.info(f"Connected to Redis at {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._redis = None
                raise

        return self._redis

    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        try:
            client = self._get_client()
            client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis connection check failed: {e}")
            return False

    def get_stock(self, product_id: str) -> Optional[int]:
        """Get stock for a product from Redis cache"""
        try:
            client = self._get_client()
            value = client.get(f"stock:{product_id}")
            return int(value) if value is not None else None
        except Exception as e:
            logger.warning(f"Failed to get stock from Redis for {product_id}: {e}")
            return None

    def set_stock(self, product_id: str, quantity: int) -> bool:
        """Set stock for a product in Redis cache"""
        try:
            client = self._get_client()
            client.set(f"stock:{product_id}", quantity)
            return True
        except Exception as e:
            logger.error(f"Failed to set stock in Redis for {product_id}: {e}")
            return False

    def increase_stock(self, product_id: str, quantity: int) -> Optional[int]:
        """Increase stock by quantity, returns new stock level or None on error"""
        try:
            client = self._get_client()
            return client.incrby(f"stock:{product_id}", quantity)
        except Exception as e:
            logger.error(f"Failed to increase stock in Redis for {product_id}: {e}")
            return None

    def decrease_stock(self, product_id: str, quantity: int) -> Optional[int]:
        """Decrease stock by quantity, returns new stock level or None on error"""
        try:
            client = self._get_client()
            new_value = client.decrby(f"stock:{product_id}", quantity)
            if new_value < 0:
                # Restore if went negative (oversell prevention)
                client.incrby(f"stock:{product_id}", quantity)
                return None
            return new_value
        except Exception as e:
            logger.error(f"Failed to decrease stock in Redis for {product_id}: {e}")
            return None

    def get_all_stock(self) -> dict[str, int]:
        """Get all stock levels from Redis cache"""
        try:
            client = self._get_client()
            keys = client.keys("stock:*")
            result = {}
            for key in keys:
                product_id = key.replace("stock:", "")
                value = client.get(key)
                if value is not None:
                    result[product_id] = int(value)
            return result
        except Exception as e:
            logger.warning(f"Failed to get all stock from Redis: {e}")
            return {}

    def initialize_stock(self, stock_data: dict[str, int]) -> bool:
        """Initialize Redis cache with stock data"""
        try:
            client = self._get_client()
            pipe = client.pipeline()
            for product_id, quantity in stock_data.items():
                pipe.set(f"stock:{product_id}", quantity)
            pipe.execute()
            logger.info(f"Initialized Redis cache with {len(stock_data)} products")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            return False

    def clear_cache(self) -> bool:
        """Clear all stock cache from Redis"""
        try:
            client = self._get_client()
            keys = client.keys("stock:*")
            if keys:
                client.delete(*keys)
            logger.info(f"Cleared Redis cache ({len(keys)} keys removed)")
            return True
        except Exception as e:
            logger.error(f"Failed to clear Redis cache: {e}")
            return False

    def check_and_reserve_stock(
        self, product_id: str, quantity: int
    ) -> tuple[bool, int]:
        """
        Atomically check stock and reserve (decrease) if available.
        Returns (success, remaining_stock)
        """
        try:
            client = self._get_client()
            # Use Lua script for atomic check-and-set
            lua_script = """
            local stock_key = KEYS[1]
            local quantity = tonumber(ARGV[1])
            local current = tonumber(redis.call('get', stock_key) or '0')
            
            if current >= quantity then
                redis.call('decrby', stock_key, quantity)
                return {1, current - quantity}
            else
                return {0, current}
            end
            """
            result = client.eval(lua_script, 1, f"stock:{product_id}", quantity)
            return bool(result[0]), result[1]
        except Exception as e:
            logger.error(
                f"Failed to check and reserve stock in Redis for {product_id}: {e}"
            )
            return False, 0


# Global Redis client instance
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """Get or create global Redis client"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


def close_redis() -> None:
    """Close Redis connection"""
    global _redis_client
    if _redis_client and _redis_client._redis:
        try:
            _redis_client._redis.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")
        _redis_client = None

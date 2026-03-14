# =============================================================================
# services/redis_cache.py — Redis Rate Limiting & Caching
# =============================================================================
# Implements a sliding-window rate limiter using Redis.
# Ensures the widget endpoint isn't spammed (default: 20 req/min per API key).
# =============================================================================

import logging
import time
from typing import Optional
import redis.asyncio as redis
from core.config import get_settings

logger = logging.getLogger(__name__)

# --- Module-level Redis client ---
_redis: Optional[redis.Redis] = None


async def connect_redis() -> None:
    """
    Initialize the async Redis connection.
    Called during FastAPI lifespan startup.
    """
    global _redis
    settings = get_settings()
    logger.info(f"Connecting to Redis: {settings.REDIS_URL}")
    _redis = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    # Test connection
    await _redis.ping()
    logger.info("Redis connected successfully.")


async def close_redis() -> None:
    """Close the Redis connection. Called during shutdown."""
    global _redis
    if _redis:
        await _redis.close()
        logger.info("Redis connection closed.")


def get_redis() -> redis.Redis:
    """Get the current Redis client instance."""
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call connect_redis() first.")
    return _redis


async def check_rate_limit(
    api_key: str,
    limit: Optional[int] = None,
    window: Optional[int] = None,
) -> bool:
    """
    Check if an API key has exceeded its rate limit.
    
    Uses a sliding-window counter pattern in Redis:
    - Key: "rate_limit:{api_key}"
    - Each request adds the current timestamp to a sorted set
    - Old entries (outside the window) are pruned
    - Count of remaining entries determines if limit is exceeded
    
    Args:
        api_key: The API key to rate-limit.
        limit: Max requests allowed in the window (default from config).
        window: Time window in seconds (default from config).
        
    Returns:
        True if the request is ALLOWED, False if rate-limited (→ 429).
    """
    settings = get_settings()
    limit = limit or settings.RATE_LIMIT_REQUESTS
    window = window or settings.RATE_LIMIT_WINDOW_SECONDS

    r = get_redis()
    key = f"rate_limit:{api_key}"
    now = time.time()
    window_start = now - window

    # Use a Redis pipeline for atomicity
    pipe = r.pipeline()

    # Remove entries older than the window
    pipe.zremrangebyscore(key, 0, window_start)

    # Count current entries in the window
    pipe.zcard(key)

    # Add the current request
    pipe.zadd(key, {str(now): now})

    # Set TTL on the key to auto-cleanup
    pipe.expire(key, window)

    results = await pipe.execute()

    # results[1] is the count BEFORE adding this request
    current_count = results[1]

    if current_count >= limit:
        logger.warning(
            f"Rate limit exceeded for API key '{api_key[:8]}...' "
            f"({current_count}/{limit} in {window}s)"
        )
        return False  # Rate limited

    return True  # Allowed

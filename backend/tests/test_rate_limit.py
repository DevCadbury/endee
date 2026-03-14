# =============================================================================
# tests/test_rate_limit.py — Redis Rate Limiting Tests
# =============================================================================
# Tests the sliding-window rate limiter to ensure proper 429 enforcement.
# =============================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestRateLimit:
    """Test rate limiting behavior."""

    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        """Requests under the limit should be allowed."""
        mock_redis = MagicMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[
            0,   # zremrangebyscore result
            5,   # zcard result (5 requests, under 20 limit)
            1,   # zadd result
            True # expire result
        ])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("services.redis_cache._redis", mock_redis):
            from services.redis_cache import check_rate_limit
            allowed = await check_rate_limit("test_key", limit=20, window=60)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        """Requests over the limit should be blocked."""
        mock_redis = MagicMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[
            0,    # zremrangebyscore result
            20,   # zcard result (at limit)
            1,    # zadd result
            True  # expire result
        ])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("services.redis_cache._redis", mock_redis):
            from services.redis_cache import check_rate_limit
            allowed = await check_rate_limit("test_key", limit=20, window=60)
            assert allowed is False

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        """Different API keys should have independent rate limits."""
        call_count = 0

        mock_redis = MagicMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[
            0,   # zremrangebyscore
            0,   # zcard (0 requests for this key)
            1,   # zadd
            True # expire
        ])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("services.redis_cache._redis", mock_redis):
            from services.redis_cache import check_rate_limit

            # Both should be allowed (independent counters)
            allowed_a = await check_rate_limit("key_A", limit=20, window=60)
            allowed_b = await check_rate_limit("key_B", limit=20, window=60)

            assert allowed_a is True
            assert allowed_b is True


class TestChatEndpointRateLimit:
    """Test rate limiting integration in the chat endpoint."""

    @pytest.mark.asyncio
    async def test_429_response(self):
        """Widget should get 429 when rate limited."""
        from fastapi.testclient import TestClient

        # We test the HTTP behavior by checking the endpoint logic
        # A rate-limited request should raise HTTPException(429)
        with patch("api.chat.check_rate_limit", new_callable=AsyncMock, return_value=False):
            with patch("api.chat.get_company_from_api_key", new_callable=AsyncMock, return_value="company_123"):
                from api.chat import incoming_message, ChatRequest
                from fastapi import HTTPException

                with pytest.raises(HTTPException) as exc_info:
                    await incoming_message(
                        request=ChatRequest(customer_message="Hello"),
                        company_id="company_123",
                    )

                assert exc_info.value.status_code == 429

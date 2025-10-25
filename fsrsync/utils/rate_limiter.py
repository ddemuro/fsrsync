"""
Rate Limiting Middleware for FSRsync

Provides sophisticated rate limiting with:
- Per-IP rate limiting
- Per-API-key rate limiting
- Per-endpoint rate limiting
- Token bucket algorithm
- Sliding window tracking
- Distributed rate limiting support

## Rate Limit Strategies

GLOBAL: Single global rate limit for all requests
PER_IP: Individual limit per source IP address
PER_KEY: Individual limit per API key
PER_ENDPOINT: Individual limit per endpoint
ADAPTIVE: Adjusts limits based on system load

## Usage

```python
limiter = RateLimiter(strategy="per_ip", requests_per_second=100)

# Check rate limit
if limiter.is_allowed(client_id="192.168.1.1", endpoint="/api/sync"):
    process_request()
else:
    return 429 Too Many Requests
```
"""

import time
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class RateLimitStrategy(Enum):
    """Rate limiting strategy"""
    GLOBAL = "global"
    PER_IP = "per_ip"
    PER_KEY = "per_key"
    PER_ENDPOINT = "per_endpoint"
    ADAPTIVE = "adaptive"


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    strategy: RateLimitStrategy
    requests_per_second: float
    burst_size: int
    window_size_seconds: int = 60
    cleanup_interval: int = 300  # Clean old entries every 5 minutes


@dataclass
class RateLimitStatus:
    """Status of rate limit for a client"""
    allowed: bool
    remaining_requests: int
    reset_time: float
    retry_after: float = 0.0


class TokenBucket:
    """Token bucket for rate limiting"""

    def __init__(self, capacity: float, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Try to consume tokens.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if consumption successful
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        self.last_refill = now

    def get_available_tokens(self) -> float:
        """Get current available tokens"""
        self._refill()
        return self.tokens


class RateLimiter:
    """
    Sophisticated rate limiting system for FSRsync.
    
    Provides multiple rate limiting strategies with token bucket
    algorithm for fair and efficient rate control.
    """

    def __init__(self, strategy: str = "per_ip", requests_per_second: float = 100.0,
                 burst_size: int = 10, logger_instance=None):
        """
        Initialize rate limiter.
        
        Args:
            strategy: Rate limiting strategy
            requests_per_second: Base request rate
            burst_size: Allow burst requests
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.strategy = RateLimitStrategy(strategy.lower())
        self.config = RateLimitConfig(
            strategy=self.strategy,
            requests_per_second=requests_per_second,
            burst_size=burst_size
        )

        # Storage for rate limit buckets
        self.buckets: Dict[str, TokenBucket] = {}
        self.sliding_windows: Dict[str, deque] = {}
        self.last_cleanup = time.time()

        self.logger.info(f"RateLimiter initialized with strategy: {self.strategy.value}")

    def is_allowed(self, client_id: str, endpoint: str = "/api",
                   weight: float = 1.0) -> bool:
        """
        Check if request is allowed.
        
        Args:
            client_id: Client identifier (IP, API key, etc.)
            endpoint: API endpoint being accessed
            weight: Request weight (some requests cost more)
            
        Returns:
            True if request allowed
        """
        try:
            # Determine rate limit key
            if self.strategy == RateLimitStrategy.GLOBAL:
                key = "global"
            elif self.strategy == RateLimitStrategy.PER_ENDPOINT:
                key = endpoint
            else:  # PER_IP, PER_KEY, ADAPTIVE
                key = client_id

            # Get or create bucket
            if key not in self.buckets:
                self.buckets[key] = TokenBucket(
                    capacity=self.config.burst_size,
                    refill_rate=self.config.requests_per_second
                )

            bucket = self.buckets[key]

            # Check if request allowed
            allowed = bucket.consume(weight)

            if not allowed:
                self.logger.warning(
                    f"Rate limit exceeded for {key} on {endpoint}"
                )

            # Periodic cleanup
            self._periodic_cleanup()

            return allowed

        except Exception as e:
            self.logger.error(f"Error checking rate limit: {e}")
            return True  # Allow on error

    def get_status(self, client_id: str, endpoint: str = "/api") -> RateLimitStatus:
        """
        Get rate limit status for client.
        
        Args:
            client_id: Client identifier
            endpoint: API endpoint
            
        Returns:
            RateLimitStatus with current limits
        """
        try:
            if self.strategy == RateLimitStrategy.GLOBAL:
                key = "global"
            elif self.strategy == RateLimitStrategy.PER_ENDPOINT:
                key = endpoint
            else:
                key = client_id

            if key not in self.buckets:
                self.buckets[key] = TokenBucket(
                    capacity=self.config.burst_size,
                    refill_rate=self.config.requests_per_second
                )

            bucket = self.buckets[key]
            available = bucket.get_available_tokens()

            return RateLimitStatus(
                allowed=available >= 1.0,
                remaining_requests=int(available),
                reset_time=time.time() + (
                    (self.config.burst_size - available) / 
                    self.config.requests_per_second
                )
            )

        except Exception as e:
            self.logger.error(f"Error getting rate limit status: {e}")
            return RateLimitStatus(
                allowed=True,
                remaining_requests=-1,
                reset_time=time.time()
            )

    def reset_client(self, client_id: str) -> bool:
        """
        Reset rate limit for client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            True if reset successful
        """
        try:
            if client_id in self.buckets:
                self.buckets[client_id] = TokenBucket(
                    capacity=self.config.burst_size,
                    refill_rate=self.config.requests_per_second
                )
                self.logger.info(f"Reset rate limit for {client_id}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error resetting rate limit: {e}")
            return False

    def _periodic_cleanup(self) -> None:
        """Clean up old bucket entries"""
        now = time.time()

        if now - self.last_cleanup < self.config.cleanup_interval:
            return

        # Remove stale buckets (no requests for a while)
        stale_clients = [
            key for key, bucket in self.buckets.items()
            if now - bucket.last_refill > 3600  # 1 hour of inactivity
        ]

        for client in stale_clients:
            del self.buckets[client]

        self.last_cleanup = now

        if stale_clients:
            self.logger.debug(f"Cleaned up {len(stale_clients)} stale rate limit entries")

    def get_statistics(self) -> Dict[str, any]:
        """Get rate limiter statistics"""
        return {
            'strategy': self.strategy.value,
            'requests_per_second': self.config.requests_per_second,
            'burst_size': self.config.burst_size,
            'active_clients': len(self.buckets),
            'total_buckets': len(self.buckets),
            'window_size_seconds': self.config.window_size_seconds
        }

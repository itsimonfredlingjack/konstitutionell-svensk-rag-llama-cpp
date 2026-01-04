#!/usr/bin/env python3
"""
Rate limiter for Swedish kommun document scraping.
Provides adaptive rate limiting based on kommun size and response times.
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

# Rate limits per kommun type
RATE_LIMITS = {
    "storstad": {
        "delay": 5.0,  # Seconds between requests
        "max_concurrent": 3,  # Max concurrent requests
        "burst_limit": 10,  # Max requests per burst window
        "burst_window": 60,  # Burst window in seconds
        "population_min": 100000,
    },
    "stor": {
        "delay": 7.0,
        "max_concurrent": 2,
        "burst_limit": 8,
        "burst_window": 60,
        "population_min": 50000,
    },
    "medelstor": {
        "delay": 10.0,
        "max_concurrent": 2,
        "burst_limit": 6,
        "burst_window": 60,
        "population_min": 20000,
    },
    "liten": {
        "delay": 12.0,
        "max_concurrent": 1,
        "burst_limit": 5,
        "burst_window": 60,
        "population_min": 0,
    },
}

# Priority to kommun type mapping
PRIORITY_TO_TYPE = {5: "storstad", 4: "stor", 3: "medelstor", 2: "liten", 1: "liten"}


@dataclass
class RequestStats:
    """Statistics for a single domain."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    last_request_time: float = 0.0
    consecutive_errors: int = 0


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts based on:
    - Kommun size/priority
    - Response times
    - Error rates
    """

    def __init__(self, kommun_type: str = "medelstor"):
        self.config = RATE_LIMITS.get(kommun_type, RATE_LIMITS["medelstor"])
        self.base_delay = self.config["delay"]
        self.current_delay = self.base_delay
        self.lock = threading.Lock()
        self.last_request = 0.0
        self.request_times: list = []  # Sliding window of request timestamps
        self.stats = RequestStats()

    @classmethod
    def from_priority(cls, priority: int) -> "AdaptiveRateLimiter":
        """Create rate limiter from kommun priority (1-5)."""
        kommun_type = PRIORITY_TO_TYPE.get(priority, "medelstor")
        return cls(kommun_type)

    @classmethod
    def from_population(cls, population: int) -> "AdaptiveRateLimiter":
        """Create rate limiter based on population."""
        if population >= 100000:
            return cls("storstad")
        elif population >= 50000:
            return cls("stor")
        elif population >= 20000:
            return cls("medelstor")
        else:
            return cls("liten")

    def wait(self) -> float:
        """
        Wait for rate limit. Returns actual wait time.
        Thread-safe.
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request

            # Check burst limit
            self._clean_request_window(now)
            if len(self.request_times) >= self.config["burst_limit"]:
                # Wait until oldest request exits the window
                wait_until = self.request_times[0] + self.config["burst_window"]
                wait_time = max(0, wait_until - now)
                if wait_time > 0:
                    time.sleep(wait_time)
                    now = time.time()
                    self._clean_request_window(now)

            # Apply delay
            if elapsed < self.current_delay:
                wait_time = self.current_delay - elapsed
                time.sleep(wait_time)
                now = time.time()
            else:
                wait_time = 0

            self.last_request = now
            self.request_times.append(now)
            self.stats.total_requests += 1

            return wait_time

    def _clean_request_window(self, now: float):
        """Remove requests outside the burst window."""
        cutoff = now - self.config["burst_window"]
        self.request_times = [t for t in self.request_times if t > cutoff]

    def record_success(self, response_time: float):
        """Record a successful request. May decrease delay."""
        with self.lock:
            self.stats.successful_requests += 1
            self.stats.total_response_time += response_time
            self.stats.consecutive_errors = 0

            # Adaptive: speed up if responses are fast
            avg_response = self.stats.total_response_time / max(1, self.stats.successful_requests)
            if avg_response < 1.0 and self.stats.consecutive_errors == 0:
                # Allow slight speedup, but not below base
                self.current_delay = max(self.base_delay * 0.8, self.current_delay * 0.95)

    def record_error(self, is_rate_limit: bool = False):
        """Record a failed request. May increase delay."""
        with self.lock:
            self.stats.failed_requests += 1
            self.stats.consecutive_errors += 1

            if is_rate_limit or self.stats.consecutive_errors >= 3:
                # Exponential backoff
                self.current_delay = min(60.0, self.current_delay * 2)
            else:
                # Linear increase
                self.current_delay = min(60.0, self.current_delay * 1.2)

    def get_stats(self) -> dict:
        """Get current statistics."""
        with self.lock:
            return {
                "total_requests": self.stats.total_requests,
                "successful": self.stats.successful_requests,
                "failed": self.stats.failed_requests,
                "current_delay": round(self.current_delay, 2),
                "base_delay": self.base_delay,
                "avg_response_time": round(
                    self.stats.total_response_time / max(1, self.stats.successful_requests), 3
                ),
                "error_rate": round(
                    self.stats.failed_requests / max(1, self.stats.total_requests), 3
                ),
            }

    def reset(self):
        """Reset the rate limiter state."""
        with self.lock:
            self.current_delay = self.base_delay
            self.last_request = 0.0
            self.request_times.clear()
            self.stats = RequestStats()


class GlobalRateLimitManager:
    """
    Manager for rate limiting across multiple domains/kommuner.
    Ensures we don't overwhelm any single server.
    """

    def __init__(self):
        self.limiters: dict[str, AdaptiveRateLimiter] = {}
        self.lock = threading.Lock()
        self.global_stats = defaultdict(lambda: RequestStats())

    def get_limiter(self, domain: str, priority: int = 3) -> AdaptiveRateLimiter:
        """Get or create a rate limiter for a domain."""
        with self.lock:
            if domain not in self.limiters:
                self.limiters[domain] = AdaptiveRateLimiter.from_priority(priority)
            return self.limiters[domain]

    def wait(self, domain: str, priority: int = 3) -> float:
        """Wait for rate limit on a specific domain."""
        limiter = self.get_limiter(domain, priority)
        return limiter.wait()

    def record_request(
        self, domain: str, success: bool, response_time: float = 0.0, is_rate_limit: bool = False
    ):
        """Record a request result."""
        with self.lock:
            if domain in self.limiters:
                if success:
                    self.limiters[domain].record_success(response_time)
                else:
                    self.limiters[domain].record_error(is_rate_limit)

    def get_all_stats(self) -> dict[str, dict]:
        """Get statistics for all domains."""
        with self.lock:
            return {domain: limiter.get_stats() for domain, limiter in self.limiters.items()}


# Global instance for shared use
_global_manager: Optional[GlobalRateLimitManager] = None


def get_rate_limit_manager() -> GlobalRateLimitManager:
    """Get the global rate limit manager singleton."""
    global _global_manager
    if _global_manager is None:
        _global_manager = GlobalRateLimitManager()
    return _global_manager


def get_delay_for_kommun(priority: int) -> float:
    """Get recommended delay for a kommun based on priority."""
    kommun_type = PRIORITY_TO_TYPE.get(priority, "medelstor")
    return RATE_LIMITS[kommun_type]["delay"]


if __name__ == "__main__":
    # Demo/test
    print("Rate Limiter Configuration:")
    print("-" * 50)
    for kommun_type, config in RATE_LIMITS.items():
        print(f"\n{kommun_type.upper()}:")
        for key, value in config.items():
            print(f"  {key}: {value}")

    print("\n" + "=" * 50)
    print("Testing adaptive rate limiter...")

    limiter = AdaptiveRateLimiter("storstad")

    for i in range(5):
        wait_time = limiter.wait()
        print(f"Request {i+1}: waited {wait_time:.2f}s")
        limiter.record_success(0.5)

    print("\nSimulating errors...")
    for i in range(3):
        limiter.record_error(is_rate_limit=True)
        print(f"After error {i+1}: delay = {limiter.current_delay:.2f}s")

    print("\nFinal stats:")
    print(limiter.get_stats())

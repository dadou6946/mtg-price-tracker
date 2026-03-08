"""
Retry utilities with exponential backoff, jitter, and Retry-After support.
Handles resilience for scraping, API calls, and Celery tasks.
"""

import time
import random
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Optional
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError,
)

logger = logging.getLogger(__name__)


class RetryableException(Exception):
    """Base exception for retryable errors."""
    pass


class RateLimitError(RetryableException):
    """429 Too Many Requests - should respect Retry-After."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class ServiceUnavailableError(RetryableException):
    """503 Service Unavailable - temporary."""
    pass


class TimeoutError(RetryableException):
    """Request timeout - network issue."""
    pass


def categorize_error(exception: Exception) -> Tuple[str, bool]:
    """
    Categorize an exception and determine if it's retryable.

    Returns:
        (error_type, is_retryable) where error_type is one of:
        - RATE_LIMITED (429)
        - SERVICE_UNAVAILABLE (503)
        - TIMEOUT
        - CONNECTION_ERROR
        - NOT_FOUND (404) → not retryable
        - SERVER_ERROR (500)
        - UNKNOWN
    """
    error_str = str(exception).lower()

    if isinstance(exception, RateLimitError):
        return 'RATE_LIMITED', True
    if isinstance(exception, ServiceUnavailableError):
        return 'SERVICE_UNAVAILABLE', True
    if isinstance(exception, requests.Timeout):
        return 'TIMEOUT', True
    if isinstance(exception, requests.ConnectionError):
        return 'CONNECTION_ERROR', True

    if isinstance(exception, requests.HTTPError):
        status_code = exception.response.status_code
        if status_code == 404:
            return 'NOT_FOUND', False  # Card not on this store
        if status_code == 429:
            return 'RATE_LIMITED', True
        if status_code == 503:
            return 'SERVICE_UNAVAILABLE', True
        if 500 <= status_code < 600:
            return 'SERVER_ERROR', True

    if 'database is locked' in error_str or 'locked' in error_str:
        return 'DB_LOCKED', True
    if 'timeout' in error_str:
        return 'TIMEOUT', True
    if 'connection' in error_str or 'refused' in error_str:
        return 'CONNECTION_ERROR', True

    return 'UNKNOWN', False


def extract_retry_after(response: requests.Response) -> Optional[int]:
    """
    Extract Retry-After from response headers.

    RFC 7231: Retry-After can be:
    - Delta seconds (integer): "120"
    - HTTP-date (string): "Wed, 21 Oct 2025 07:28:00 GMT"

    Returns seconds to wait, or None if not present.
    """
    retry_after = response.headers.get('Retry-After')
    if not retry_after:
        return None

    try:
        # Try to parse as seconds (integer)
        return int(retry_after)
    except ValueError:
        # It's an HTTP-date - parse it (simplified: assume 60s default)
        logger.debug(f"Retry-After is HTTP-date: {retry_after}, using 60s default")
        return 60


def calculate_backoff_with_jitter(attempt: int, base_seconds: int = 1) -> int:
    """
    Calculate exponential backoff with jitter.

    Formula: (base * 2^attempt) + random(0, jitter_max)

    Example: attempt 0,1,2 with base=1:
    - Attempt 0: 1 + random(0,1) = 0-2s
    - Attempt 1: 2 + random(0,2) = 2-4s
    - Attempt 2: 4 + random(0,4) = 4-8s

    Prevents "thundering herd" where all workers retry at same time.
    """
    exp_backoff = base_seconds * (2 ** attempt)
    jitter = random.uniform(0, exp_backoff)
    return exp_backoff + jitter


def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_seconds: int = 1,
    on_retry: Optional[Callable] = None,
) -> any:
    """
    Execute function with exponential backoff + jitter + Retry-After support.

    Args:
        func: Callable to execute
        max_retries: Max attempts (total attempts = max_retries + 1)
        base_seconds: Base backoff (1s → 2s → 4s with jitter)
        on_retry: Optional callback on retry: on_retry(attempt, error, wait_time)

    Returns:
        Result from func

    Raises:
        Original exception if all retries exhausted
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            error_type, is_retryable = categorize_error(e)

            if attempt >= max_retries or not is_retryable:
                # No more retries or not retryable error
                logger.error(
                    f"Function failed permanently. Type: {error_type}, "
                    f"Attempt: {attempt + 1}/{max_retries + 1}, Error: {str(e)}"
                )
                raise

            # Calculate wait time
            wait_time = calculate_backoff_with_jitter(attempt, base_seconds)

            # Check for Retry-After header (if HTTPError with response)
            if isinstance(e, requests.HTTPError) and hasattr(e, 'response'):
                retry_after = extract_retry_after(e.response)
                if retry_after:
                    wait_time = retry_after
                    error_type = 'RATE_LIMITED_WITH_RETRY_AFTER'

            # Notify callback if provided
            if on_retry:
                on_retry(attempt + 1, error_type, wait_time)
            else:
                logger.warning(
                    f"Retrying in {wait_time:.1f}s. Type: {error_type}, "
                    f"Attempt: {attempt + 1}/{max_retries + 1}"
                )

            time.sleep(wait_time)

    # Should not reach here, but just in case
    raise RuntimeError(f"Failed after {max_retries + 1} attempts")


def retryable_task(
    max_retries: int = 3,
    base_seconds: int = 1,
):
    """
    Decorator for Celery tasks with automatic retry on failure.

    Usage:
        @retryable_task(max_retries=3, base_seconds=2)
        def my_task():
            ...

    Wraps with tenacity for clean retryable behavior.
    """
    def decorator(func: Callable) -> Callable:
        @retry(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(multiplier=base_seconds, min=base_seconds, max=60),
            retry=retry_if_exception_type((
                requests.RequestException,
                RateLimitError,
                ServiceUnavailableError,
                TimeoutError,
            )),
            reraise=True,
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

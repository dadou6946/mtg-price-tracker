"""
Tests for retry utilities and error categorization.
"""

import pytest
import requests
from unittest.mock import Mock, patch
from cards.retry_utils import (
    categorize_error,
    calculate_backoff_with_jitter,
    extract_retry_after,
    retry_with_backoff,
    RateLimitError,
    ServiceUnavailableError,
    TimeoutError,
)


class TestCategorizeError:
    """Test error categorization logic."""

    def test_categorize_rate_limit_error(self):
        exc = RateLimitError("Too many requests", retry_after=30)
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'RATE_LIMITED'
        assert is_retryable is True

    def test_categorize_service_unavailable(self):
        exc = ServiceUnavailableError("Service temporarily unavailable")
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'SERVICE_UNAVAILABLE'
        assert is_retryable is True

    def test_categorize_timeout(self):
        exc = requests.Timeout("Connection timed out")
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'TIMEOUT'
        assert is_retryable is True

    def test_categorize_connection_error(self):
        exc = requests.ConnectionError("Connection refused")
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'CONNECTION_ERROR'
        assert is_retryable is True

    def test_categorize_http_404(self):
        response = Mock()
        response.status_code = 404
        exc = requests.HTTPError(response=response)
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'NOT_FOUND'
        assert is_retryable is False

    def test_categorize_http_429(self):
        response = Mock()
        response.status_code = 429
        exc = requests.HTTPError(response=response)
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'RATE_LIMITED'
        assert is_retryable is True

    def test_categorize_http_503(self):
        response = Mock()
        response.status_code = 503
        exc = requests.HTTPError(response=response)
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'SERVICE_UNAVAILABLE'
        assert is_retryable is True

    def test_categorize_http_500(self):
        response = Mock()
        response.status_code = 500
        exc = requests.HTTPError(response=response)
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'SERVER_ERROR'
        assert is_retryable is True

    def test_categorize_db_locked(self):
        exc = Exception("database is locked")
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'DB_LOCKED'
        assert is_retryable is True

    def test_categorize_unknown(self):
        exc = Exception("Something weird happened")
        error_type, is_retryable = categorize_error(exc)
        assert error_type == 'UNKNOWN'
        assert is_retryable is False


class TestExtractRetryAfter:
    """Test Retry-After header extraction."""

    def test_extract_retry_after_seconds(self):
        response = Mock()
        response.headers = {'Retry-After': '120'}
        retry_after = extract_retry_after(response)
        assert retry_after == 120

    def test_extract_retry_after_http_date(self):
        response = Mock()
        response.headers = {'Retry-After': 'Wed, 21 Oct 2025 07:28:00 GMT'}
        retry_after = extract_retry_after(response)
        assert retry_after == 60  # Default fallback

    def test_extract_retry_after_missing(self):
        response = Mock()
        response.headers = {}
        retry_after = extract_retry_after(response)
        assert retry_after is None


class TestCalculateBackoffWithJitter:
    """Test exponential backoff with jitter."""

    def test_backoff_attempt_0(self):
        # Attempt 0: 1 + random(0, 1) = 0-2s
        wait_time = calculate_backoff_with_jitter(attempt=0, base_seconds=1)
        assert 0 <= wait_time <= 2

    def test_backoff_attempt_1(self):
        # Attempt 1: 2 + random(0, 2) = 2-4s
        wait_time = calculate_backoff_with_jitter(attempt=1, base_seconds=1)
        assert 2 <= wait_time <= 4

    def test_backoff_attempt_2(self):
        # Attempt 2: 4 + random(0, 4) = 4-8s
        wait_time = calculate_backoff_with_jitter(attempt=2, base_seconds=1)
        assert 4 <= wait_time <= 8

    def test_backoff_custom_base(self):
        # Custom base: 2s → attempt 0: 2 + random(0, 2) = 2-4s
        wait_time = calculate_backoff_with_jitter(attempt=0, base_seconds=2)
        assert 2 <= wait_time <= 4


class TestRetryWithBackoff:
    """Test retry_with_backoff function."""

    def test_success_first_attempt(self):
        def fn():
            return "success"

        result = retry_with_backoff(fn, max_retries=3)
        assert result == "success"

    def test_success_after_retry(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise requests.Timeout("Timeout")
            return "success"

        result = retry_with_backoff(fn, max_retries=3, base_seconds=0.001)
        assert result == "success"
        assert call_count == 2

    def test_max_retries_exhausted(self):
        def fn():
            raise requests.Timeout("Always timeout")

        with pytest.raises(requests.Timeout):
            retry_with_backoff(fn, max_retries=2, base_seconds=0.001)

    def test_non_retryable_error(self):
        def fn():
            raise ValueError("This is not retryable")

        with pytest.raises(ValueError):
            retry_with_backoff(fn, max_retries=3, base_seconds=0.001)

    def test_retry_after_header(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                response = Mock()
                response.status_code = 429
                response.headers = {'Retry-After': '1'}
                exc = requests.HTTPError(response=response)
                raise exc
            return "success"

        result = retry_with_backoff(fn, max_retries=3, base_seconds=1)
        assert result == "success"
        assert call_count == 2

    def test_callback_on_retry(self):
        retry_calls = []

        def on_retry(attempt, error_type, wait_time):
            retry_calls.append((attempt, error_type, wait_time))

        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise requests.Timeout("Timeout")
            return "success"

        result = retry_with_backoff(
            fn, max_retries=3, base_seconds=0.001, on_retry=on_retry
        )
        assert result == "success"
        assert len(retry_calls) == 1
        assert retry_calls[0][0] == 1  # First retry attempt
        assert retry_calls[0][1] == 'TIMEOUT'

# Error Handling & Retry Logic - Implementation Guide

## Overview

This document describes the comprehensive error handling and retry system implemented in the MTG Price Tracker backend (Step 6 - Niveau 1 + 2).

## Architecture Components

### 1. **Retry Utilities** (`cards/retry_utils.py`)

Core retry and error categorization logic:

- **`categorize_error(exception)`**: Maps exceptions to error types
  - Returns: `(error_type: str, is_retryable: bool)`
  - Error types: `RATE_LIMITED`, `SERVICE_UNAVAILABLE`, `TIMEOUT`, `CONNECTION_ERROR`, `NOT_FOUND`, `SERVER_ERROR`, `DB_LOCKED`, `UNKNOWN`

- **`extract_retry_after(response)`**: Reads `Retry-After` header from HTTP responses
  - Supports: Delta-seconds or HTTP-date format
  - Returns: Seconds to wait (or None)

- **`calculate_backoff_with_jitter(attempt, base_seconds)`**: Exponential backoff + jitter
  - Formula: `(base * 2^attempt) + random(0, exp_backoff)`
  - Prevents "thundering herd" problem (all workers retrying at same time)
  - Example: attempt 0,1,2 → 0-2s, 2-4s, 4-8s

- **`retry_with_backoff(func, max_retries=3, ...)`**: Execute with automatic retry
  - Handles retryable exceptions
  - Respects `Retry-After` header if present
  - Logs each retry attempt

- **`@retryable_task` decorator**: For Celery tasks
  - Uses `tenacity` library for clean retry syntax
  - Automatic retry on `requests.RequestException`, timeouts, rate limits

### 2. **Celery Task Improvements**

#### Import Tasks
```python
@shared_task(bind=True,
    autoretry_for=(requests.RequestException,),  # Auto-retry on network errors
    retry_kwargs={'max_retries': 3, 'countdown': 5})  # 5s delay between retries
def import_card_task(...):
    pass
```

- Auto-retry on network errors (connection refused, timeouts)
- Respects Retry-After headers from Scryfall
- Better error categorization in response

#### Scrape Tasks
```python
def _scrape_store(...):
    try:
        created, updated = retry_with_backoff(
            scrape_fn,
            max_retries=3,
            base_seconds=1,
            on_retry=on_retry,
        )
    except Exception as e:
        error_type, is_retryable = categorize_error(e)
        # Circuit breaker integration
        if error_type in ('RATE_LIMITED', 'SERVICE_UNAVAILABLE'):
            cb.record_error()
```

- Exponential backoff with jitter (1s, 2s, 4s)
- Circuit breaker integration for persistent failures
- Error categorization for frontend

### 3. **Dead-Letter Queue** (`TaskFailureLog` model)

Failed task logging for manual retry and analysis:

```python
class TaskFailureLog(models.Model):
    task_name: str          # Task name (e.g., cards.tasks.import_card_task)
    task_id: str            # Celery task ID (unique)
    task_args: JSON         # Positional arguments
    task_kwargs: JSON       # Named arguments
    error_type: str         # RATE_LIMITED, TIMEOUT, etc.
    error_message: str      # Short error message
    traceback: str          # Full stack trace
    attempt_count: int      # How many times retried
    max_retries: int        # Configured max retries
    is_retryable: bool      # Can be manually retried?
    is_resolved: bool       # Has been manually resolved?
    failed_at: DateTime     # When the task failed
    resolved_at: DateTime   # When manually resolved (if applicable)
```

#### Integration
- Celery signal handler: `task_failure.connect` → logs failures automatically
- Django admin integration: View, filter, retry failed tasks
- Management command: `python manage.py retry_failed_tasks`

### 4. **Celery Signal Handler** (`config/celery.py`)

Automatically logs failed tasks:

```python
@task_failure.connect
def task_failure_handler(sender, task_id, exception, ...):
    error_type, is_retryable = categorize_error(exception)
    TaskFailureLog.objects.create(
        task_name=sender.name,
        task_id=task_id,
        error_type=error_type,
        is_retryable=is_retryable,
        ...
    )
```

## Error Categories & Handling

| Error Type | Cause | HTTP Code | Retry? | Strategy |
|---|---|---|---|---|
| **RATE_LIMITED** | Store rate-limiting | 429 | ✓ Yes | Respect Retry-After, exponential backoff, circuit breaker |
| **SERVICE_UNAVAILABLE** | Server maintenance | 503 | ✓ Yes | Exponential backoff, circuit breaker |
| **TIMEOUT** | Connection slow | - | ✓ Yes | Increase timeout, exponential backoff |
| **CONNECTION_ERROR** | Network down | - | ✓ Yes | Exponential backoff |
| **SERVER_ERROR** | Server error | 5xx | ✓ Yes | Exponential backoff (limit to 2 retries) |
| **NOT_FOUND** | Card not on store | 404 | ✗ No | Skip, log warning |
| **DB_LOCKED** | SQLite contention | - | ✓ Yes | Exponential backoff |
| **UNKNOWN** | Unknown error | - | ✗ No | Log error, manual investigation |

## Usage Examples

### 1. View Failed Tasks (Admin)
```
- Go to /admin/cards/taskfailurelog/
- Filter by error_type, is_resolved, failed_at
- Bulk actions: Mark as resolved, Retry
```

### 2. Retry Failed Tasks (CLI)
```bash
# Retry all unresolved retryable tasks
python manage.py retry_failed_tasks --unresolved

# Retry specific error type
python manage.py retry_failed_tasks --error-type RATE_LIMITED

# Dry-run (show what would be retried)
python manage.py retry_failed_tasks --unresolved --dry-run

# Retry specific task
python manage.py retry_failed_tasks --task-id abc123def456
```

### 3. Circuit Breaker + Retry
```python
# _scrape_store() checks circuit breaker before retry
cb = StoreCircuitBreaker.objects.get(store=store)
if not cb.is_available():
    return store.name, {'error': 'Circuit breaker OPEN', 'error_type': 'CIRCUIT_BREAKER_OPEN'}

# Retry with exponential backoff
created, updated = retry_with_backoff(scrape_fn, max_retries=3)

# On success: reset circuit breaker
cb.record_success()

# On rate-limit/service error: increment circuit breaker
cb.record_error()
```

## Configuration

### Celery Settings (`settings.py`)
```python
# Task failure handling
CELERY_TASK_ACKS_LATE = True           # Ack after execution
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # Reject if worker dies
CELERY_ENABLE_UTC = False              # Use Montreal timezone

# For specific tasks (example):
@shared_task(
    autoretry_for=(RequestException,),
    retry_kwargs={'max_retries': 3, 'countdown': 5}
)
def my_task(...):
    pass
```

### Retry Constants
- **Base delay**: 1 second (exponential: 1s, 2s, 4s, 8s, ...)
- **Max retries**: 3 (total attempts = 4)
- **Jitter**: random(0, exp_backoff) to prevent thundering herd
- **Retry-After**: Respected if server sends header

## Monitoring & Observability

### Logs
- Task retry attempts: `[WARNING] Retrying in Xs. Type: ERROR_TYPE, Attempt: N/M`
- Task failures: `[ERROR] Function failed permanently. Type: ERROR_TYPE, Error: ...`
- Circuit breaker changes: `[WARNING] Circuit breaker STORE: CLOSED -> OPEN`

### Metrics (via Admin)
- TaskFailureLog: Count unresolved failures by error_type
- StoreCircuitBreaker: Monitor store health, recovery rate
- Import task retries: Track Scryfall API reliability

### Dead-Letter Queue Status
```bash
# Check failed tasks
python manage.py shell
>>> from cards.models import TaskFailureLog
>>> TaskFailureLog.objects.filter(is_resolved=False).count()
>>> TaskFailureLog.objects.values('error_type').annotate(Count('id'))
```

## Migration

Create migration for `TaskFailureLog` model:

```bash
python manage.py makemigrations cards
python manage.py migrate
```

Then register in Django admin (already done in `admin.py`).

## Testing

Example test for retry logic:

```python
# Test categorize_error
from cards.retry_utils import categorize_error, RateLimitError

error_type, is_retryable = categorize_error(RateLimitError("429", retry_after=30))
assert error_type == 'RATE_LIMITED'
assert is_retryable == True

# Test calculate_backoff_with_jitter
wait_time = calculate_backoff_with_jitter(attempt=1, base_seconds=1)
assert 2 <= wait_time <= 4  # 2^1 + random(0,2)

# Test retry_with_backoff
call_count = 0
def flaky_fn():
    global call_count
    call_count += 1
    if call_count < 2:
        raise TimeoutError("Timeout")
    return "success"

result = retry_with_backoff(flaky_fn, max_retries=3)
assert result == "success"
assert call_count == 2
```

## Future Improvements

1. **Advanced Retry Strategies**
   - Adaptive retry delays based on error history
   - Per-store retry configuration
   - Exponential backoff with max delay ceiling

2. **Monitoring**
   - Prometheus metrics for retry rates
   - Grafana dashboard for error trends
   - Alerting on high failure rates

3. **Advanced Logging**
   - Structured logging with context
   - Error aggregation and deduplication
   - Automated retry suggestions

4. **Dead-Letter Queue UI**
   - Interactive retry dashboard
   - Bulk operations (mark resolved, retry)
   - Export failed task logs to CSV

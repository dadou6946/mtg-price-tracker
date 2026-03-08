# MTG Price Tracker - API Documentation

## Overview

Complete REST API for tracking Magic: The Gathering card prices across Montreal game stores.

- **Base URL**: `http://localhost:8000/api/`
- **Production**: `https://api.mtg-price-tracker.com/api/`
- **Authentication**: JWT (Bearer token)
- **Rate Limiting**: Per-user or per-IP
- **Async Operations**: Celery-backed with polling

## Documentation Links

- **Interactive Swagger UI**: `/api/docs/`
- **ReDoc (alternative)**: `/api/redoc/`
- **OpenAPI Schema JSON**: `/api/schema/`

---

## Authentication

### Get Token (Login)

```http
POST /api/token/
Content-Type: application/json

{
  "username": "demo",
  "password": "demo123"
}
```

**Response** (200 OK):
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Refresh Token

```http
POST /api/token/refresh/
Content-Type: application/json

{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response** (200 OK):
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Using Token

Include in all authenticated requests:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Endpoints

### 1. Cards

#### List Cards

```http
GET /api/cards/
```

**Query Parameters**:
- `search`: Search by card name or set name
- `set_code`: Filter by set code (e.g., "KHM", "DMU")
- `rarity`: Filter by rarity (common, uncommon, rare, mythic)
- `is_tracked`: Filter tracked cards (true/false)
- `ordering`: Sort by field (name, set_code, created_at, -created_at)

**Example**:
```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/cards/?set_code=KHM&rarity=rare&search=Dragon"
```

**Response** (200 OK):
```json
{
  "count": 42,
  "next": "http://localhost:8000/api/cards/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Goldspan Dragon",
      "set_code": "KHM",
      "set_name": "Kaldheim",
      "collector_number": "139",
      "rarity": "rare",
      "is_tracked": true,
      "created_at": "2025-03-08T12:00:00Z",
      "updated_at": "2025-03-08T12:00:00Z"
    }
  ]
}
```

#### Get Card Detail

```http
GET /api/cards/{id}/
```

**Response** (200 OK):
```json
{
  "id": 1,
  "name": "Goldspan Dragon",
  "set_code": "KHM",
  "set_name": "Kaldheim",
  "collector_number": "139",
  "rarity": "rare",
  "image_url": "https://cards.scryfall.io/...",
  "is_tracked": true,
  "created_at": "2025-03-08T12:00:00Z",
  "updated_at": "2025-03-08T12:00:00Z",

  "current_prices": [
    {
      "store": "Face to Face Games",
      "price": 15.99,
      "currency": "CAD",
      "condition": "NM",
      "foil": false,
      "in_stock": true,
      "url": "https://www.facetofacegames.com/...",
      "scraped_at": "2025-03-08T12:00:00Z"
    }
  ],

  "lowest_price": 14.99,
  "stores_count": 5,
  "in_stock_count": 4,

  "price_history": [
    {
      "date": "2025-03-08",
      "price_min": 14.99,
      "price_max": 19.99,
      "price_avg": 17.49,
      "stores_count": 5
    }
  ]
}
```

#### List Tracked Cards

```http
GET /api/cards/tracked/
```

Returns only cards with `is_tracked=true`. Uses same filtering as list.

#### Toggle Card Tracking

```http
POST /api/cards/{id}/toggle_tracking/
```

**Response** (200 OK):
```json
{
  "message": "Suivi active",
  "card": { ... }
}
```

#### Import Card (Async)

```http
POST /api/cards/import/
Content-Type: application/json

{
  "name": "Goldspan Dragon",
  "set_code": "KHM",
  "track": true
}
```

**Parameters**:
- `name` (required): Card name (exact or fuzzy match)
- `set_code` (optional): Set code for exact match
- `track` (optional): Track card after import (default: false)

**Response** (202 ACCEPTED):
```json
{
  "task_id": "abc123def456",
  "status": "queued",
  "message": "Import task queued"
}
```

**Polling**: Use `/api/tasks/{task_id}/` to check status

**Rate Limit**: 10/hour

#### Import Set (Async)

```http
POST /api/cards/import_set/
Content-Type: application/json

{
  "set_code": "KHM",
  "rarities": ["rare", "mythic"],
  "track": true
}
```

**Parameters**:
- `set_code` (required): Set code (e.g., "KHM", "DMU")
- `rarities` (optional): Array of rarities (common, uncommon, rare, mythic) - default: ["rare", "mythic"]
- `track` (optional): Track imported cards (default: false)

**Response** (202 ACCEPTED):
```json
{
  "task_id": "xyz789uvw012",
  "status": "queued",
  "message": "Set import task queued"
}
```

**Rate Limit**: 10/hour

---

### 2. Stores

#### List Active Stores

```http
GET /api/stores/
```

**Response** (200 OK):
```json
[
  {
    "id": 1,
    "name": "Face to Face Games",
    "url": "https://www.facetofacegames.com",
    "location": "Montréal",
    "is_active": true
  },
  {
    "id": 2,
    "name": "Le Valet de Coeur",
    "url": "https://levaletdecoeur.com",
    "location": "Montréal",
    "is_active": true
  }
]
```

---

### 3. Prices

#### List Prices

```http
GET /api/prices/
```

**Query Parameters**:
- `card`: Filter by card ID
- `store`: Filter by store ID
- `condition`: Filter by condition (NM, LP, MP, HP, DMG)
- `foil`: Filter by foil (true/false)
- `in_stock`: Filter by stock status (true/false)
- `language`: Filter by language code (EN, FR, JP, etc.)

**Example**:
```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/prices/?card=1&foil=false&in_stock=true"
```

**Response** (200 OK):
```json
{
  "count": 15,
  "results": [
    {
      "id": 1,
      "card": 1,
      "store": 1,
      "price": 15.99,
      "currency": "CAD",
      "condition": "NM",
      "foil": false,
      "language": "EN",
      "in_stock": true,
      "quantity": 3,
      "url": "https://...",
      "scraped_at": "2025-03-08T12:00:00Z"
    }
  ]
}
```

---

### 4. Async Tasks

#### Poll Task Status

```http
GET /api/tasks/{task_id}/
```

**Response** (200 OK) - During Processing:
```json
{
  "task_id": "abc123def456",
  "status": "PROGRESS",
  "progress": {
    "completed": 25,
    "total": 50,
    "card": "Goldspan Dragon"
  }
}
```

**Response** (200 OK) - After Success:
```json
{
  "task_id": "abc123def456",
  "status": "SUCCESS",
  "result": {
    "status": "done",
    "total_cards": 50,
    "total_created": 145,
    "total_updated": 320
  }
}
```

**Response** (200 OK) - After Failure:
```json
{
  "task_id": "abc123def456",
  "status": "FAILURE",
  "error": "Scryfall API timeout"
}
```

**Possible Status Values**:
- `PENDING`: Task queued, not started
- `STARTED`: Task execution started
- `PROGRESS`: Task in progress with meta information
- `SUCCESS`: Task completed successfully
- `FAILURE`: Task failed with error

#### Scrape Single Card (Async)

```http
POST /api/cards/{id}/scrape/
```

Scrape prices for one card from all active stores.

**Response** (202 ACCEPTED):
```json
{
  "task_id": "def789ghi012",
  "status": "queued"
}
```

**Rate Limit**: 10/hour

#### Scrape All Tracked Cards (Async)

```http
POST /api/scrape/
```

Scrape prices for all tracked cards from all stores. Processes in batches of 50.

**Response** (202 ACCEPTED):
```json
{
  "task_id": "jkl345mno678",
  "status": "processing",
  "total_cards": 150,
  "total_batches": 3,
  "batch_size": 50
}
```

**Rate Limit**: 10/hour

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | OK | Successful GET request |
| 201 | Created | Successful POST that created resource |
| 202 | Accepted | Async task queued |
| 400 | Bad Request | Missing required field |
| 401 | Unauthorized | Missing or invalid token |
| 403 | Forbidden | Permission denied |
| 404 | Not Found | Resource doesn't exist |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Unexpected error |

### Error Response Format

```json
{
  "error": "Descriptive error message",
  "error_type": "RATE_LIMITED|TIMEOUT|NOT_FOUND|...",
  "details": {
    "field": ["error message for field"]
  }
}
```

### Rate Limiting

Rate limits are per-user:
- **Anonymous**: 10 requests/hour
- **Authenticated**: 100 requests/hour
- **Scrape endpoint**: 10/hour
- **Import endpoint**: 10/hour

**Rate limit headers**:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 3
X-RateLimit-Reset: 1709898000
```

When limit exceeded, returns 429 with:
```json
{
  "detail": "Request was throttled. Expected available in 3540 seconds."
}
```

---

## Async Workflow Example

### 1. Queue Import Task

```bash
curl -X POST http://localhost:8000/api/cards/import/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Goldspan Dragon", "set_code": "KHM", "track": true}'
```

Response:
```json
{
  "task_id": "abc123def456",
  "status": "queued"
}
```

### 2. Poll Status (repeat until completion)

```bash
curl http://localhost:8000/api/tasks/abc123def456/ \
  -H "Authorization: Bearer TOKEN"
```

Response (processing):
```json
{
  "task_id": "abc123def456",
  "status": "PROGRESS",
  "progress": {"step": 1, "total": 3}
}
```

Response (completed):
```json
{
  "task_id": "abc123def456",
  "status": "SUCCESS",
  "result": {
    "status": "created",
    "card": {
      "id": 1,
      "name": "Goldspan Dragon",
      "set_code": "KHM"
    }
  }
}
```

### 3. Use Result

Frontend displays card details and can now track prices.

---

## Pagination

List endpoints support pagination:

```http
GET /api/cards/?page=1&page_size=20
```

**Response**:
```json
{
  "count": 1042,
  "next": "http://localhost:8000/api/cards/?page=2",
  "previous": null,
  "results": [...]
}
```

---

## Filtering & Searching

### Search
```http
GET /api/cards/?search=dragon
```

Searches: `name`, `set_name`

### Filter by Field
```http
GET /api/cards/?set_code=KHM&rarity=rare&is_tracked=true
```

Available filters: `set_code`, `rarity`, `is_tracked`

### Ordering
```http
GET /api/cards/?ordering=-created_at
```

Available fields: `name`, `set_code`, `created_at`

Prefix with `-` for descending order.

---

## Example: Frontend Integration

### JavaScript/Vue.js Example

```javascript
const API_URL = 'http://localhost:8000/api';
const token = localStorage.getItem('token');

// 1. Import a card
const importCard = async (name, setCode, track) => {
  const response = await fetch(`${API_URL}/cards/import/`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ name, set_code: setCode, track })
  });
  const data = await response.json();
  return data.task_id;
};

// 2. Poll task status
const pollTask = async (taskId) => {
  const response = await fetch(`${API_URL}/tasks/${taskId}/`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return await response.json();
};

// 3. Use with setInterval
const taskId = await importCard('Goldspan Dragon', 'KHM', true);
const interval = setInterval(async () => {
  const status = await pollTask(taskId);
  console.log(status.status, status.progress);
  if (status.status === 'SUCCESS' || status.status === 'FAILURE') {
    clearInterval(interval);
    console.log(status.result || status.error);
  }
}, 500);
```

---

## Testing

### Using cURL

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}' \
  | jq -r '.access')

# List cards
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/cards/

# Import card
curl -X POST http://localhost:8000/api/cards/import/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Goldspan Dragon","set_code":"KHM","track":true}'
```

### Using Swagger UI

Visit `/api/docs/` to test endpoints directly in browser.

### Using Postman

Import the OpenAPI schema from `/api/schema/` for complete Postman collection.

---

## Versioning

API version: **1.0.0**

Future versions will maintain backward compatibility or provide clear migration paths.

---

## Support & Feedback

- **Issues**: Report on GitHub
- **Documentation**: See `/api/docs/` for interactive Swagger UI
- **Schema**: `/api/schema/` for OpenAPI JSON


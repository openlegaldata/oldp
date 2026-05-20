# Case Statistics API

This document describes the API endpoints for retrieving aggregated case statistics, designed for plotting and data analysis.

## Overview

The statistics API provides aggregated case counts with date-bucketed time series. A root endpoint returns the overall time series, and four sub-endpoints break down counts by a specific dimension (country, state, court, or source), where each result item includes its own total and date buckets.

All endpoints default to the **last year** with **monthly** buckets.

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/cases/stats/` | Overall total and date-bucketed time series |
| `GET /api/cases/stats/by_country/` | Grouped by country |
| `GET /api/cases/stats/by_state/` | Grouped by state |
| `GET /api/cases/stats/by_court/` | Grouped by court (requires `court__state` filter) |
| `GET /api/cases/stats/by_source/` | Grouped by data source |

## Authentication

All endpoints are publicly readable (anonymous access returns statistics for accepted cases only). Authenticated requests follow the same visibility rules as the cases API.

## Query Parameters

### Root endpoint (`/api/cases/stats/`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `date_after` | string (YYYY-MM-DD) | One year ago | Filter cases with `date >= value` |
| `date_before` | string (YYYY-MM-DD) | Today | Filter cases with `date <= value` |
| `bucket` | string | `month` | Time bucket size: `year`, `month`, or `day` |
| `review_status` | string | — | Staff only. Filter by review status: `pending`, `accepted`, or `rejected` |

### Sub-endpoints (`by_country`, `by_state`, `by_court`, `by_source`)

All parameters from the root endpoint, plus:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `court` | integer | No | Filter by court ID |
| `court_slug` | string | No | Filter by court slug (alternative to `court`) |
| `court__state` | integer | **Yes** for `by_court` (unless `state_slug` is provided), No for others | Filter by state ID (via court relation) |
| `state_slug` | string | **Yes** for `by_court` (unless `court__state` is provided), No for others | Filter by state slug (alternative to `court__state`) |
| `source` | integer | No | Filter by source ID |

## Visibility Rules

- **Anonymous / non-staff users**: Statistics reflect only cases with `review_status="accepted"`
- **Staff users**: Statistics include all cases (accepted, pending, rejected). Use the `review_status` parameter to filter by a specific status.

## Response Format

### Root endpoint

Returns an overall total and date-bucketed time series.

```json
{
  "filters": {
    "date_after": "2025-03-23",
    "date_before": "2026-03-23",
    "bucket": "month"
  },
  "total": 48250,
  "buckets": [
    {"date": "2025-04", "count": 3820},
    {"date": "2025-05", "count": 4105},
    {"date": "2025-06", "count": 3950},
    {"date": "2025-07", "count": 4200},
    {"date": "2025-08", "count": 3780},
    {"date": "2025-09", "count": 4050},
    {"date": "2025-10", "count": 4310},
    {"date": "2025-11", "count": 3900},
    {"date": "2025-12", "count": 4180},
    {"date": "2026-01", "count": 4120},
    {"date": "2026-02", "count": 3835},
    {"date": "2026-03", "count": 4000}
  ]
}
```

### Sub-endpoints

Each result item includes its own `total` and `buckets`, allowing per-item time series plots.

**`/api/cases/stats/by_country/`**

```json
{
  "filters": {
    "date_after": "2025-03-23",
    "date_before": "2026-03-23",
    "bucket": "month"
  },
  "total": 48250,
  "results": [
    {
      "id": 1,
      "code": "DE",
      "name": "Germany",
      "total": 47800,
      "buckets": [
        {"date": "2025-04", "count": 3790},
        {"date": "2025-05", "count": 4070},
        {"date": "2025-06", "count": 3920}
      ]
    },
    {
      "id": 2,
      "code": "AT",
      "name": "Austria",
      "total": 450,
      "buckets": [
        {"date": "2025-04", "count": 30},
        {"date": "2025-05", "count": 35},
        {"date": "2025-06", "count": 30}
      ]
    }
  ]
}
```

**`/api/cases/stats/by_state/`**

```json
{
  "filters": {"date_after": "2025-03-23", "date_before": "2026-03-23", "bucket": "month"},
  "total": 48250,
  "results": [
    {
      "id": 1,
      "name": "Nordrhein-Westfalen",
      "total": 8500,
      "buckets": [
        {"date": "2025-04", "count": 680},
        {"date": "2025-05", "count": 720}
      ]
    },
    {
      "id": 2,
      "name": "Bayern",
      "total": 7200,
      "buckets": [
        {"date": "2025-04", "count": 590},
        {"date": "2025-05", "count": 610}
      ]
    }
  ]
}
```

**`/api/cases/stats/by_court/?court__state=1`**

The `court__state` filter is required for this endpoint to limit the number of results.

```json
{
  "filters": {"date_after": "2025-03-23", "date_before": "2026-03-23", "bucket": "month"},
  "total": 8500,
  "results": [
    {
      "id": 10,
      "name": "Oberlandesgericht Düsseldorf",
      "total": 1250,
      "buckets": [
        {"date": "2025-04", "count": 98},
        {"date": "2025-05", "count": 110}
      ]
    },
    {
      "id": 25,
      "name": "Landgericht Köln",
      "total": 980,
      "buckets": [
        {"date": "2025-04", "count": 75},
        {"date": "2025-05", "count": 82}
      ]
    }
  ]
}
```

**`/api/cases/stats/by_source/`**

```json
{
  "filters": {"date_after": "2025-03-23", "date_before": "2026-03-23", "bucket": "month"},
  "total": 48250,
  "results": [
    {
      "id": 1,
      "name": "openjur",
      "total": 32000,
      "buckets": [
        {"date": "2025-04", "count": 2550},
        {"date": "2025-05", "count": 2700}
      ]
    },
    {
      "id": 2,
      "name": "gesetze-im-internet",
      "total": 16250,
      "buckets": [
        {"date": "2025-04", "count": 1270},
        {"date": "2025-05", "count": 1405}
      ]
    }
  ]
}
```

## Examples

### Get overall monthly statistics for the last year (default)

```bash
curl -X GET "https://de.openlegaldata.io/api/cases/stats/" \
  -H "Accept: application/json"
```

### Get yearly statistics over a longer period

```bash
curl -X GET "https://de.openlegaldata.io/api/cases/stats/?bucket=year&date_after=2015-01-01&date_before=2026-12-31" \
  -H "Accept: application/json"
```

### Get court breakdown for a specific state (by ID)

```bash
curl -X GET "https://de.openlegaldata.io/api/cases/stats/by_court/?court__state=1" \
  -H "Accept: application/json"
```

### Get court breakdown for a specific state (by slug)

```bash
curl -X GET "https://de.openlegaldata.io/api/cases/stats/by_court/?state_slug=nordrhein-westfalen" \
  -H "Accept: application/json"
```

### Get source breakdown with daily buckets for the last month

```bash
curl -X GET "https://de.openlegaldata.io/api/cases/stats/by_source/?bucket=day&date_after=2026-02-23&date_before=2026-03-23" \
  -H "Accept: application/json"
```

### Staff: statistics for pending cases only

```bash
curl -X GET "https://de.openlegaldata.io/api/cases/stats/by_source/?review_status=pending" \
  -H "Authorization: Token YOUR_STAFF_API_TOKEN" \
  -H "Accept: application/json"
```

### Python: plot cases per source over time

```python
import requests
import matplotlib.pyplot as plt

response = requests.get("https://de.openlegaldata.io/api/cases/stats/by_source/")
data = response.json()

plt.figure(figsize=(12, 5))
for source in data["results"]:
    dates = [b["date"] for b in source["buckets"]]
    counts = [b["count"] for b in source["buckets"]]
    plt.plot(dates, counts, label=f"{source['name']} ({source['total']})")

plt.xlabel("Month")
plt.ylabel("Cases")
plt.title(f"Cases per source (total: {data['total']})")
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```

## Error Responses

### 400 Bad Request - Missing required filter

```json
{
  "detail": "The 'court__state' or 'state_slug' filter is required for this endpoint."
}
```

### 400 Bad Request - Invalid bucket

```json
{
  "detail": "Invalid bucket 'weekly'. Must be one of: year, month, day."
}
```

### 400 Bad Request - Invalid ID value

```json
{
  "detail": "Invalid value 'de' for 'court__state'. Expected a numeric ID."
}
```

### 400 Bad Request - Invalid date

```json
{
  "detail": "Invalid date format for 'date_after': 'not-a-date'. Use YYYY-MM-DD."
}
```

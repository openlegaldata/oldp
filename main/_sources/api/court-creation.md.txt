# Court Creation API

This document describes the API endpoint for programmatically creating new courts.

## Overview

The Court Creation API allows authenticated users with write permissions to create new courts. The API handles:

- **Automatic state resolution**: States are identified from their name, not requiring foreign key IDs
- **Automatic city resolution**: Cities are resolved from name within a state, or created if not found
- **Duplicate prevention**: Courts with the same code are rejected
- **API token tracking**: The token used for creation is recorded for audit purposes
- **Review workflow**: API-submitted courts are set to `pending` review status

## Endpoint

```
POST /api/courts/
```

## Authentication

Requires a valid API token with `courts:write` permission.

```bash
Authorization: Token YOUR_API_TOKEN
```

## Request Format

### Headers

```
Content-Type: application/json
Authorization: Token YOUR_API_TOKEN
```

### Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string (max 200) | Yes | Full name of the court with location |
| `code` | string (max 20) | Yes | Unique court identifier based on ECLI (e.g., "BVerfG") |
| `state_name` | string (max 50) | Yes | State name for automatic resolution |
| `court_type` | string (max 10) | No | Court type code (e.g., "AG", "LG", "OLG") |
| `city_name` | string (max 100) | No | City name for automatic resolution |
| `jurisdiction` | string (max 100) | No | Jurisdiction of court (ordinary, civil, ...) |
| `level_of_appeal` | string (max 100) | No | Level of appeal (local, federal, ...) |
| `aliases` | string | No | List of aliases (one per line) |
| `description` | string | No | Court description |
| `homepage` | URL | No | Official court homepage |
| `street_address` | string (max 200) | No | Street address with house number |
| `postal_code` | string (max 200) | No | Postal code (ZIP code) |
| `address_locality` | string (max 200) | No | Locality (city name) |
| `telephone` | string (max 200) | No | Telephone number |
| `fax_number` | string (max 200) | No | Fax number |
| `email` | email | No | Email address |

### Example Request

```bash
curl -X POST "https://de.openlegaldata.io/api/courts/" \
  -H "Authorization: Token YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Amtsgericht Berlin-Mitte",
    "code": "AGBERLINMITTE",
    "state_name": "Berlin",
    "court_type": "AG",
    "city_name": "Berlin",
    "jurisdiction": "ordinary",
    "homepage": "https://www.berlin.de/gerichte/amtsgericht-mitte/"
  }'
```

## Response Format

### Success Response (201 Created)

```json
{
  "id": 42,
  "slug": "ag-berlin",
  "review_status": "pending"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique court ID |
| `slug` | string | URL-friendly identifier (auto-generated from court type and city) |
| `review_status` | string | Review status (`pending` for API submissions) |

### Error Responses

#### 400 Bad Request - Validation Error

```json
{
  "name": ["This field is required."],
  "code": ["Court code cannot be empty."]
}
```

#### 400 Bad Request - State Not Found

```json
{
  "detail": "Could not resolve state from the provided name: 'InvalidState'."
}
```

#### 401 Unauthorized

```json
{
  "detail": "Authentication credentials were not provided."
}
```

#### 403 Forbidden

```json
{
  "detail": "You do not have permission to perform this action."
}
```

#### 409 Conflict - Duplicate Court

```json
{
  "detail": "A court with code 'BVerfG' already exists."
}
```

## State and City Name Resolution

### State Resolution

The API resolves the state from the provided `state_name`:

1. **Exact match**: Checks for an exact name match
2. **Case-insensitive match**: Falls back to case-insensitive matching

If no state is found, a `400 Bad Request` error is returned.

### City Resolution

The API resolves the city from the provided `city_name` within the resolved state:

1. **Exact match**: Checks for an exact name match within the state
2. **Case-insensitive match**: Falls back to case-insensitive matching
3. **Auto-creation**: If no city is found, a new city is created within the state

City is optional — state-level courts (e.g., Bundesgerichtshof) do not require a city.

## Duplicate Prevention

Duplicates are detected based on the court `code`. If a court with the same code already exists, a `409 Conflict` error is returned.

## Review Workflow

Courts created via the API use a three-state review workflow:

1. **Submission**: Courts are submitted via the API with `review_status="pending"`
2. **Review**: Administrators review pending courts in the Django admin
3. **Decision**: Admins set `review_status` to either `"accepted"` or `"rejected"`

Note: Existing courts (not created via API) default to `review_status="accepted"`.

### Admin Review Process

Administrators can manage pending courts via the Django admin:

1. Navigate to **Courts > Courts** in the admin
2. Filter by **Review status: Pending** to see pending submissions
3. Filter by **API submission: Created via API** to see API-submitted courts
4. Review court data and metadata
5. Change **Review status** to "Accepted" or "Rejected" and save

## API Token Tracking

The API token used for court creation is recorded on the court for audit purposes. This allows:

- Tracking which application/user created each court
- Identifying courts created via API vs. other methods
- Revoking access and identifying affected courts

### Querying API Submissions

To view all courts created by a specific API token:

```python
from oldp.apps.courts.models import Court
from oldp.apps.accounts.models import APIToken

token = APIToken.objects.get(name="Scraper Token")
pending_courts = Court.objects.filter(created_by_token=token, review_status="pending")
```

## Examples

### Python Example

```python
import requests

API_TOKEN = "your_api_token_here"
BASE_URL = "https://de.openlegaldata.io/api"

headers = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

court_data = {
    "name": "Amtsgericht Berlin-Mitte",
    "code": "AGBERLINMITTE",
    "state_name": "Berlin",
    "court_type": "AG",
    "city_name": "Berlin",
    "jurisdiction": "ordinary",
}

response = requests.post(f"{BASE_URL}/courts/", json=court_data, headers=headers)

if response.status_code == 201:
    result = response.json()
    print(f"Court created: ID={result['id']}, Slug={result['slug']}, Status={result['review_status']}")
elif response.status_code == 409:
    print("Error: Court already exists")
elif response.status_code == 400:
    print(f"Validation error: {response.json()}")
else:
    print(f"Error: {response.status_code} - {response.text}")
```

### Batch Import Example

```python
import requests

API_TOKEN = "your_api_token_here"
BASE_URL = "https://de.openlegaldata.io/api"

headers = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

courts_to_import = [
    {
        "name": "Amtsgericht Köln",
        "code": "AGKOELN",
        "state_name": "Nordrhein-Westfalen",
        "court_type": "AG",
        "city_name": "Köln",
    },
    {
        "name": "Landgericht Köln",
        "code": "LGKOELN",
        "state_name": "Nordrhein-Westfalen",
        "court_type": "LG",
        "city_name": "Köln",
    },
]

results = {"created": 0, "duplicates": 0, "errors": 0}

for court_data in courts_to_import:
    response = requests.post(f"{BASE_URL}/courts/", json=court_data, headers=headers)

    if response.status_code == 201:
        results["created"] += 1
    elif response.status_code == 409:
        results["duplicates"] += 1
    else:
        results["errors"] += 1
        print(f"Error importing {court_data['code']}: {response.text}")

print(f"Import complete: {results}")
```

## Best Practices

1. **Validate state names**: Use the states API to verify state names before bulk imports
2. **Handle duplicates gracefully**: 409 responses indicate the court already exists
3. **Provide court type**: Including `court_type` helps with slug generation and filtering
4. **Expect review delays**: All API submissions require manual approval before being accepted
5. **Batch with care**: Implement rate limiting and error handling for bulk imports

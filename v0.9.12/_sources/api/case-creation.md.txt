# Case Creation API

This document describes the API endpoint for programmatically creating new cases.

## Overview

The Case Creation API allows authenticated users with write permissions to create new court cases. The API handles:

- **Automatic court resolution**: Courts are identified from their name, not requiring foreign key IDs
- **Duplicate prevention**: Cases with the same court and file number are rejected
- **Reference extraction**: Legal references (law citations, case citations) are automatically extracted from content
- **API token tracking**: The token used for creation is recorded for audit purposes

## Endpoint

```
POST /api/cases/?extract_refs=true
```

## Authentication

Requires a valid API token with `cases:write` permission.

```bash
Authorization: Token YOUR_API_TOKEN
```

## Request Format

### Headers

```
Content-Type: application/json
Authorization: Token YOUR_API_TOKEN
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `extract_refs` | boolean | true | Whether to extract references from content. Set to `false`, `0`, or `no` to disable. |

### Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `court_name` | string | Yes | Court name for automatic resolution (e.g., "Bundesgerichtshof", "AG Berlin", "LG Koblenz 14. Zivilkammer") |
| `file_number` | string | Yes | Court file number (e.g., "I ZR 123/21") |
| `date` | string | Yes | Publication date in YYYY-MM-DD format |
| `content` | string | Yes | Full case content in HTML format |
| `type` | string | No | Type of decision (e.g., "Urteil", "Beschluss") |
| `ecli` | string | No | European Case Law Identifier |
| `abstract` | string | No | Case summary/abstract in HTML format |
| `title` | string | No | Case title |
| `source` | object | No | Source information. If omitted, the default source is assigned. |
| `source.name` | string | Yes (if `source` given) | Source name used for lookup. If no source with this name exists, a new one is created. |
| `source.homepage` | string | No | Source homepage URL. Used only when creating a new source; ignored if the source already exists. |

### Example Request

```bash
curl -X POST "https://de.openlegaldata.io/api/cases/?extract_refs=true" \
  -H "Authorization: Token YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "court_name": "Bundesgerichtshof",
    "file_number": "I ZR 123/21",
    "date": "2021-05-15",
    "content": "<h2>Tenor</h2><p>Die Revision wird zurückgewiesen.</p><h2>Gründe</h2><p>Der Kläger hat gegen § 823 BGB verstoßen...</p>",
    "type": "Urteil",
    "ecli": "ECLI:DE:BGH:2021:150521UIZR123.21.0",
    "abstract": "<p>Zur Haftung bei Verletzung von Verkehrssicherungspflichten.</p>",
    "source": {
      "name": "My Court Scraper",
      "homepage": "https://example.com/scraper"
    }
  }'
```

## Response Format

### Success Response (201 Created)

```json
{
  "id": 12345,
  "slug": "bgh-2021-05-15-i-zr-123-21",
  "review_status": "pending"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique case ID |
| `slug` | string | URL-friendly identifier (court-date-file_number) |
| `review_status` | string | Review status (`pending`, `accepted`, or `rejected`) |

### Error Responses

#### 400 Bad Request - Validation Error

```json
{
  "court_name": ["This field is required."],
  "content": ["Content must be at least 10 characters."]
}
```

#### 400 Bad Request - Court Not Found

```json
{
  "detail": "Could not resolve court from the provided name."
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

#### 409 Conflict - Duplicate Case

```json
{
  "detail": "A case with this court and file number already exists."
}
```

## Court Name Resolution

The API automatically resolves the court from the provided `court_name`. The resolution process:

1. **By code**: If the name matches a known court code (e.g., "BGH", "EuGH")
2. **By exact name**: If the name matches exactly with no spaces
3. **By type and location**: Extracts court type (e.g., "AG", "LG", "OLG") and location (state/city)
4. **By alias**: Searches court aliases for partial matches

### Court Chamber Extraction

Chamber designations are automatically extracted from court names:

| Input | Court | Chamber |
|-------|-------|---------|
| "LG Koblenz 14. Zivilkammer" | LG Koblenz | 14. Zivilkammer |
| "OLG Koblenz 2. Senat für Bußgeldsachen" | OLG Koblenz | 2. Senat für Bußgeldsachen |
| "Bundesgerichtshof" | Bundesgerichtshof | (none) |

## Source Resolution

The optional `source` field allows callers to associate a case with a specific data source (e.g., a scraper or corpus).

- **Omitted**: The platform's default source is assigned.
- **Name matches existing source**: The existing source is reused. The `homepage` field is ignored.
- **Name does not exist**: A new source is created with the given `name` and `homepage`.

Lookup is based on `name` only (exact match). The `homepage` field is only used when creating a new source.

## Reference Extraction

When the `extract_refs` query parameter is `true` (default), the API automatically extracts:

- **Law references**: Citations to legal provisions (e.g., "§ 823 BGB", "Art. 14 GG")
- **Case references**: Citations to other court decisions

References are stored as markers that can be retrieved via the case detail endpoint.

To disable reference extraction (for faster processing), use the query parameter `?extract_refs=false`.

## Validation Settings

Input validation is configurable via Django settings (`CASE_CREATION_VALIDATION`):

| Setting | Default | Description |
|---------|---------|-------------|
| `content_min_length` | 10 | Minimum content length |
| `content_max_length` | 10000000 | Maximum content length (10MB) |
| `file_number_min_length` | 1 | Minimum file number length |
| `file_number_max_length` | 100 | Maximum file number length |
| `title_max_length` | 255 | Maximum title length |
| `abstract_max_length` | 50000 | Maximum abstract length |
| `court_name_max_length` | 255 | Maximum court name length |

## API Token Tracking

The API token used for case creation is recorded on the case for audit purposes. This allows:

- Tracking which application/user created each case
- Identifying cases created via API vs. other methods
- Revoking access and identifying affected cases

## Approval Workflow

**All cases created via the API are set to `review_status="pending"` by default.** This implements a manual approval workflow:

1. **Submission**: Third-party scrapers submit cases via the API
2. **Pending**: Cases are created with `review_status="pending"`, hiding them from public view
3. **Review**: Administrators review pending cases in the Django admin
4. **Approval**: Admins set `review_status="accepted"` to make cases publicly visible
5. **Rejection**: Admins can set `review_status="rejected"` to permanently hide cases

### Admin Review Process

Administrators can manage pending cases via the Django admin:

1. Navigate to **Cases > Cases** in the admin
2. Filter by **Review status: pending** to see pending submissions
3. Filter by **created_by_token** to see cases from specific API tokens
4. Review case content and metadata
5. Set **Review status** to `accepted` and save to approve the case

### Querying API Submissions

To view all cases created by a specific API token:

```python
from oldp.apps.cases.models import Case
from oldp.apps.accounts.models import APIToken

token = APIToken.objects.get(name="Scraper Token")
pending_cases = Case.objects.filter(created_by_token=token, review_status="pending")
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

case_data = {
    "court_name": "Amtsgericht Berlin-Mitte",
    "file_number": "10 C 123/21",
    "date": "2021-06-15",
    "content": "<p>Im Namen des Volkes ergeht folgendes Urteil...</p>",
    "type": "Urteil",
}

response = requests.post(f"{BASE_URL}/cases/", json=case_data, headers=headers)

if response.status_code == 201:
    result = response.json()
    print(f"Case created: ID={result['id']}, Slug={result['slug']}")
elif response.status_code == 409:
    print("Error: Case already exists")
elif response.status_code == 400:
    print(f"Validation error: {response.json()}")
else:
    print(f"Error: {response.status_code} - {response.text}")
```

### Batch Import Example

```python
import requests
import json

API_TOKEN = "your_api_token_here"
BASE_URL = "https://de.openlegaldata.io/api"

headers = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

cases_to_import = [
    {
        "court_name": "Bundesgerichtshof",
        "file_number": "I ZR 100/21",
        "date": "2021-05-01",
        "content": "<p>Case 1 content...</p>",
    },
    {
        "court_name": "Bundesgerichtshof",
        "file_number": "I ZR 101/21",
        "date": "2021-05-02",
        "content": "<p>Case 2 content...</p>",
    },
]

results = {"created": 0, "duplicates": 0, "errors": 0}

for case_data in cases_to_import:
    response = requests.post(f"{BASE_URL}/cases/", json=case_data, headers=headers)

    if response.status_code == 201:
        results["created"] += 1
    elif response.status_code == 409:
        results["duplicates"] += 1
    else:
        results["errors"] += 1
        print(f"Error importing {case_data['file_number']}: {response.text}")

print(f"Import complete: {results}")
```

## Best Practices

1. **Validate court names**: Use the courts API to verify court names before bulk imports
2. **Handle duplicates gracefully**: 409 responses indicate the case already exists
3. **Use reference extraction**: Enable `extract_refs` for better searchability
4. **Provide ECLI**: Include ECLI for standardized case identification
5. **Expect approval delays**: All API submissions require manual approval before public visibility
6. **Batch with care**: Implement rate limiting and error handling for bulk imports

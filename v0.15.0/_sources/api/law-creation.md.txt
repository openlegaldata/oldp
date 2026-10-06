# Law Creation API

This document describes the API endpoint for programmatically creating new laws.

## Overview

The Law Creation API allows authenticated users with write permissions to create new laws within existing law books. The API handles:

- **Automatic law book resolution**: Law books are identified from their code, not requiring foreign key IDs
- **Duplicate prevention**: Laws with the same book and slug are rejected
- **Slug generation**: Slugs are automatically generated from the section identifier if not provided
- **API token tracking**: The token used for creation is recorded for audit purposes

## Endpoint

```
POST /api/laws/
```

## Authentication

Requires a valid API token with `laws:write` permission.

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
| `book_code` | string (max 100) | Yes | Law book code (e.g., "BGB", "StGB") |
| `section` | string (max 200) | Yes | Section identifier (e.g., "§ 1", "Art. 1") |
| `title` | string (max 200) | Yes | Verbose title of the law |
| `content` | string | Yes | Law content in HTML format |
| `revision_date` | string | No | Specific book revision date in YYYY-MM-DD format (uses latest revision if not specified) |
| `slug` | slug (max 200) | No | Law slug (auto-generated from section if not provided) |
| `order` | integer | No | Order within the book (default: 0) |
| `amtabk` | string (max 200) | No | Official abbreviation |
| `kurzue` | string (max 200) | No | Short title |
| `doknr` | string (max 200) | No | Document number from XML source |
| `footnotes` | string | No | Footnotes as JSON array |

### Example Request

```bash
curl -X POST "https://de.openlegaldata.io/api/laws/" \
  -H "Authorization: Token YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "book_code": "BGB",
    "section": "§ 823",
    "title": "Schadensersatzpflicht",
    "content": "<p>(1) Wer vorsätzlich oder fahrlässig das Leben, den Körper, die Gesundheit, die Freiheit, das Eigentum oder ein sonstiges Recht eines anderen widerrechtlich verletzt, ist dem anderen zum Ersatz des daraus entstehenden Schadens verpflichtet.</p>",
    "order": 823
  }'
```

## Response Format

### Success Response (201 Created)

```json
{
  "id": 12345,
  "slug": "823",
  "book_id": 42
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique law ID |
| `slug` | string | URL-friendly identifier (auto-generated from section if not provided) |
| `book_id` | integer | ID of the resolved law book |

### Error Responses

#### 400 Bad Request - Validation Error

```json
{
  "book_code": ["This field is required."],
  "content": ["Content must be at least 1 characters."]
}
```

#### 400 Bad Request - Law Book Not Found

```json
{
  "detail": "Could not find the specified law book."
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

#### 409 Conflict - Duplicate Law

```json
{
  "detail": "A law with this book and slug already exists."
}
```

## Law Book Resolution

The API automatically resolves the law book from the provided `book_code`. The resolution process:

1. **By code + revision_date**: If `revision_date` is provided, finds the book matching the exact code and revision date
2. **By code + latest**: If `revision_date` is not provided, finds the latest revision of the book (where `latest=True`)

If no matching law book is found, a `400 Bad Request` error is returned with a message indicating which lookup failed.

## Slug Generation

If `slug` is not provided in the request, it is automatically generated from the `section` field using Django's `slugify()` function:

| Section | Generated Slug |
|---------|---------------|
| `§ 823` | `823` |
| `Art. 1` | `art-1` |
| `§ 1a` | `1a` |

## Duplicate Prevention

Duplicates are detected based on the combination of **book** (resolved from `book_code`) and **slug**. If a law with the same book and slug already exists, a `409 Conflict` error is returned.

## Validation Settings

Input validation is configurable via Django settings (`LAW_CREATION_VALIDATION`):

| Setting | Default | Description |
|---------|---------|-------------|
| `content_min_length` | 1 | Minimum content length |
| `content_max_length` | 10000000 | Maximum content length (10MB) |

## API Token Tracking

The API token used for law creation is recorded on the law for audit purposes. This allows:

- Tracking which application/user created each law
- Identifying laws created via API vs. other methods
- Revoking access and identifying affected laws

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

law_data = {
    "book_code": "BGB",
    "section": "§ 823",
    "title": "Schadensersatzpflicht",
    "content": "<p>(1) Wer vorsätzlich oder fahrlässig das Leben...</p>",
    "order": 823,
}

response = requests.post(f"{BASE_URL}/laws/", json=law_data, headers=headers)

if response.status_code == 201:
    result = response.json()
    print(f"Law created: ID={result['id']}, Slug={result['slug']}, BookID={result['book_id']}")
elif response.status_code == 409:
    print("Error: Law already exists")
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

laws_to_import = [
    {
        "book_code": "BGB",
        "section": "§ 1",
        "title": "Beginn der Rechtsfähigkeit",
        "content": "<p>Die Rechtsfähigkeit des Menschen beginnt mit der Vollendung der Geburt.</p>",
        "order": 1,
    },
    {
        "book_code": "BGB",
        "section": "§ 2",
        "title": "Eintritt der Volljährigkeit",
        "content": "<p>Die Volljährigkeit tritt mit der Vollendung des 18. Lebensjahres ein.</p>",
        "order": 2,
    },
]

results = {"created": 0, "duplicates": 0, "errors": 0}

for law_data in laws_to_import:
    response = requests.post(f"{BASE_URL}/laws/", json=law_data, headers=headers)

    if response.status_code == 201:
        results["created"] += 1
    elif response.status_code == 409:
        results["duplicates"] += 1
    else:
        results["errors"] += 1
        print(f"Error importing {law_data['section']}: {response.text}")

print(f"Import complete: {results}")
```

## Best Practices

1. **Create law books first**: Ensure the law book exists before creating laws that reference it
2. **Handle duplicates gracefully**: 409 responses indicate the law already exists
3. **Provide explicit slugs for consistency**: Auto-generated slugs depend on `slugify()` behavior
4. **Use `revision_date` for precision**: Target a specific book revision instead of relying on `latest`
5. **Batch with care**: Implement rate limiting and error handling for bulk imports

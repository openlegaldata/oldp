# Law Book Creation API

This document describes the API endpoint for programmatically creating new law books.

## Overview

The Law Book Creation API allows authenticated users with write permissions to create new law books. The API handles:

- **Review workflow**: Books submitted via an API token are created with `review_status="pending"` and become publicly visible only once approved
- **Approval-driven revision management**: The `latest` flag tracks the newest **accepted** revision and is (re)assigned when a revision is approved — a pending submission never demotes the currently-published revision
- **Duplicate prevention**: Law books with the same slug and revision date are rejected
- **API token tracking**: The token used for creation is recorded for audit purposes

## Endpoint

```
POST /api/law_books/
```

## Authentication

Requires a valid API token with `lawbooks:write` permission.

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
| `code` | string (max 100) | Yes | Book code (e.g., "BGB", "StGB") |
| `title` | string (max 250) | Yes | Full title of the book |
| `revision_date` | string | Yes | Date of this revision in YYYY-MM-DD format |
| `order` | integer | No | Display order / importance (default: 0) |
| `changelog` | string | No | Changelog as JSON array |
| `footnotes` | string | No | Footnotes as JSON array |
| `sections` | string | No | Sections as JSON object |

### Example Request

```bash
curl -X POST "https://de.openlegaldata.io/api/law_books/" \
  -H "Authorization: Token YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "BGB",
    "title": "Bürgerliches Gesetzbuch",
    "revision_date": "2024-01-01",
    "order": 1
  }'
```

## Response Format

### Success Response (201 Created)

```json
{
  "id": 42,
  "slug": "bgb",
  "latest": false,
  "review_status": "pending"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique law book ID |
| `slug` | string | URL-friendly identifier (generated from code via `slugify()`) |
| `latest` | boolean | Whether this revision is the currently-published latest. Submissions via an API token are `pending` review, so this is `false` until the revision is approved. |
| `review_status` | string | `pending` for token submissions (awaiting approval), otherwise `accepted` |

### Error Responses

#### 400 Bad Request - Validation Error

```json
{
  "code": ["This field is required."],
  "title": ["Book title cannot be empty."]
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

#### 409 Conflict - Duplicate Law Book

```json
{
  "detail": "A law book with this code and revision date already exists."
}
```

## Revision Management

The `latest` flag identifies the **newest accepted** revision of a book code — the one served on the public site. It is reassigned whenever a revision's `review_status` changes (i.e. on **approval**), not when a revision is submitted. The invariant is "at most one revision per code has `latest=True`, and it is the newest accepted one".

Because API submissions are created `pending`, this means:

1. **Submitting a revision via the API** creates it `latest=False`, `review_status="pending"`. The currently-published revision keeps `latest=True` — an unapproved submission never demotes it, so the public page never goes blank while a newer revision waits for review.
2. **Approving a revision** (e.g. via the admin) makes it `latest=True` if it is now the newest accepted revision, demoting the previous latest. Approving an older revision leaves the newer accepted one as latest.
3. **Rejecting a revision** leaves the published latest unchanged.
4. A directly-created **accepted** revision (server-side, no API token) is promoted immediately if it is the newest — preserving the previous non-API behaviour.

> If a book ever drifts out of this invariant (e.g. data from before this behaviour), run `manage.py backfill_latest_books` to repair it; the public views also tolerate a missing flag by falling back to the newest accepted revision.

### Example: Revision Timeline

```
POST {"code": "BGB", "revision_date": "2023-01-01", ...}
→ Created latest=false, review_status=pending
→ (approve) → latest=true (first accepted revision)

POST {"code": "BGB", "revision_date": "2024-01-01", ...}
→ Created latest=false, review_status=pending
→ 2023-01-01 stays latest=true until approval
→ (approve 2024-01-01) → latest=true; 2023-01-01 → latest=false

POST {"code": "BGB", "revision_date": "2022-06-01", ...}
→ Created latest=false, review_status=pending
→ (approve) → stays latest=false (older than 2024-01-01)
```

## Duplicate Prevention

Duplicates are detected based on the combination of **slug** (generated from code) and **revision_date**. If a law book with the same slug and revision date already exists, a `409 Conflict` error is returned.

## API Token Tracking

The API token used for law book creation is recorded on the law book for audit purposes. This allows:

- Tracking which application/user created each law book
- Identifying law books created via API vs. other methods
- Revoking access and identifying affected law books

## Typical Workflow

Law books and laws are created in a two-step process:

1. **Create the law book** via `POST /api/law_books/`
2. **Create laws** within the book via `POST /api/laws/` using the book's `code` as `book_code`

```
POST /api/law_books/  →  {"code": "BGB", "title": "Bürgerliches Gesetzbuch", "revision_date": "2024-01-01"}
POST /api/laws/       →  {"book_code": "BGB", "section": "§ 1", "title": "Beginn der Rechtsfähigkeit", "content": "..."}
POST /api/laws/       →  {"book_code": "BGB", "section": "§ 2", "title": "Eintritt der Volljährigkeit", "content": "..."}
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

lawbook_data = {
    "code": "BGB",
    "title": "Bürgerliches Gesetzbuch",
    "revision_date": "2024-01-01",
    "order": 1,
}

response = requests.post(f"{BASE_URL}/law_books/", json=lawbook_data, headers=headers)

if response.status_code == 201:
    result = response.json()
    print(f"Law book created: ID={result['id']}, Slug={result['slug']}, Latest={result['latest']}")
elif response.status_code == 409:
    print("Error: Law book already exists")
elif response.status_code == 400:
    print(f"Validation error: {response.json()}")
else:
    print(f"Error: {response.status_code} - {response.text}")
```

### Full Import Example (Book + Laws)

```python
import requests

API_TOKEN = "your_api_token_here"
BASE_URL = "https://de.openlegaldata.io/api"

headers = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

# Step 1: Create the law book
lawbook_data = {
    "code": "BGB",
    "title": "Bürgerliches Gesetzbuch",
    "revision_date": "2024-01-01",
}

response = requests.post(f"{BASE_URL}/law_books/", json=lawbook_data, headers=headers)

if response.status_code == 201:
    print(f"Law book created: {response.json()}")
elif response.status_code == 409:
    print("Law book already exists, proceeding with law creation...")
else:
    print(f"Error creating law book: {response.status_code} - {response.text}")
    exit(1)

# Step 2: Create laws within the book
laws = [
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

for law_data in laws:
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

1. **Create books before laws**: Law creation requires an existing law book to reference
2. **Handle duplicates gracefully**: 409 responses indicate the law book already exists
3. **Use consistent revision dates**: Group all laws for a book revision under the same `revision_date`
4. **Track revisions explicitly**: Provide meaningful `revision_date` values to maintain a clear version history
5. **Batch with care**: Implement rate limiting and error handling for bulk imports

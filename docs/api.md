# API

The OLDP API is based on [Django REST Framework](http://www.django-rest-framework.org/) and provides programmatic access to legal data including cases, laws, courts, and law books.

## Base URL

All API requests should be made to:
```
https://de.openlegaldata.io/api/
```

## Authentication

The API supports two authentication methods:

### 1. API Tokens (Recommended)

API tokens provide secure, fine-grained access control to API resources. You can create and manage multiple tokens with different permission levels in your account settings.

**How to get your API token:**
1. Log in to your account
2. Navigate to your profile settings
3. Go to the "API Access" section
4. Create a new token with a descriptive name
5. Copy the token (it will only be shown once!)

**Using your token in requests:**

Add the token to the `Authorization` header using the `Token` prefix:

```bash
curl -X GET "https://de.openlegaldata.io/api/cases/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

### 2. Session Authentication

For web-based clients, you can use standard Django session authentication with your username and password.

## Permission System

API tokens use a fine-grained permission system that controls access to specific resources and actions.

### Permission Levels

Permissions are defined by **resource** and **action**:

- **Resources**: `cases`, `laws`, `courts`, `lawbooks`, `references`, `annotations`
- **Actions**: `read`, `write`, `delete`

### Default Permissions

By default, new API tokens are assigned to the **"default" permission group** which provides:

- ✅ **cases:read** - Read access to cases
- ✅ **laws:read** - Read access to laws
- ✅ **courts:read** - Read access to courts
- ✅ **lawbooks:read** - Read access to law books

This ensures secure, read-only access by default. Write and delete permissions must be explicitly granted by administrators.

### Permission Groups

Administrators can create custom permission groups with specific combinations of permissions. Tokens are assigned to permission groups, making it easy to manage access for different use cases:

- **default**: Read-only access to core resources
- **read_write**: Read and write access to specific resources
- **full_access**: Complete access including delete operations

Contact the administrators if you need elevated permissions for your API token.

## Throttle Rates

To ensure fair usage and maintain service quality, the API implements rate limiting:

- **Anonymous users**: 100 requests per day
- **Authenticated users**: 5,000 requests per hour

If you need higher limits, please contact us or consider using our data dumps for bulk access.

## API Endpoints

### Cases

**List all cases:**
```bash
curl -X GET "https://de.openlegaldata.io/api/cases/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Filter cases by court:**
```bash
curl -X GET "https://de.openlegaldata.io/api/cases/?court_id=3" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Get a specific case:**
```bash
curl -X GET "https://de.openlegaldata.io/api/cases/12345/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Filter by date range:**
```bash
curl -X GET "https://de.openlegaldata.io/api/cases/?date_after=2020-01-01&date_before=2023-12-31" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

### Laws

**List all laws:**
```bash
curl -X GET "https://de.openlegaldata.io/api/laws/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Filter laws by book:**
```bash
curl -X GET "https://de.openlegaldata.io/api/laws/?book_id=5" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Get a specific law:**
```bash
curl -X GET "https://de.openlegaldata.io/api/laws/123/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

### Law Books

**List all law books:**
```bash
curl -X GET "https://de.openlegaldata.io/api/lawbooks/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Get a specific law book:**
```bash
curl -X GET "https://de.openlegaldata.io/api/lawbooks/bgb/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Filter by code:**
```bash
curl -X GET "https://de.openlegaldata.io/api/lawbooks/?code=BGB" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

### Courts

**List all courts:**
```bash
curl -X GET "https://de.openlegaldata.io/api/courts/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Filter courts by type:**
```bash
curl -X GET "https://de.openlegaldata.io/api/courts/?court_type=AG" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Get a specific court:**
```bash
curl -X GET "https://de.openlegaldata.io/api/courts/ag-berlin/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

## Pagination

API responses are paginated. Use the `limit` and `offset` parameters to navigate through results:

```bash
# Get first 50 results
curl -X GET "https://de.openlegaldata.io/api/cases/?limit=50&offset=0" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"

# Get next 50 results
curl -X GET "https://de.openlegaldata.io/api/cases/?limit=50&offset=50" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

The response includes pagination metadata:
```json
{
  "count": 1234,
  "next": "https://de.openlegaldata.io/api/cases/?limit=50&offset=50",
  "previous": null,
  "results": [...]
}
```

## Search

**Search cases by text:**
```bash
curl -X GET "https://de.openlegaldata.io/api/cases/search/?text=urheberrecht" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

**Search laws:**
```bash
curl -X GET "https://de.openlegaldata.io/api/laws/search/?text=vertragsrecht" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

Search supports Lucene syntax for complex queries:
```bash
curl -X GET "https://de.openlegaldata.io/api/cases/search/?text=urheberrecht+AND+software" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

## Creating and Updating Resources

**Note:** Write operations require a token with appropriate `write` permissions.

### Case Creation API

For detailed documentation on creating cases programmatically, including automatic court resolution, duplicate handling, and reference extraction, see the [Case Creation API Documentation](api/case-creation.md).

**Create a new case (requires cases:write permission):**
```bash
curl -X POST "https://de.openlegaldata.io/api/cases/?extract_refs=true" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "court_name": "Bundesgerichtshof",
    "file_number": "I ZR 123/21",
    "date": "2021-05-15",
    "content": "<p>Full case content in HTML...</p>",
    "type": "Urteil"
  }'
```

The API automatically resolves the court from the `court_name` field. Use `?extract_refs=true` (default) to extract legal references from the content, or `?extract_refs=false` to disable.

**Update an existing case (requires cases:write permission):**
```bash
curl -X PATCH "https://de.openlegaldata.io/api/cases/12345/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "title": "Updated Case Title"
  }'
```

**Delete a resource (requires appropriate delete permission):**
```bash
curl -X DELETE "https://de.openlegaldata.io/api/cases/12345/" \
  -H "Authorization: Token YOUR_API_TOKEN_HERE" \
  -H "Accept: application/json"
```

## Error Handling

The API uses standard HTTP status codes:

- **200 OK**: Request successful
- **201 Created**: Resource created successfully
- **400 Bad Request**: Invalid request parameters
- **401 Unauthorized**: Missing or invalid authentication
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource not found
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Server error

**Example error response:**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**Permission denied response:**
```json
{
  "detail": "You do not have permission to perform this action."
}
```

## Response Formats

The API supports multiple response formats via the `Accept` header:

- **JSON** (default): `Accept: application/json`
- **XML**: `Accept: application/xml`
- **Browsable API**: `Accept: text/html` (for web browsers)

## Best Practices

1. **Use HTTPS**: Always use HTTPS to protect your API token
2. **Store tokens securely**: Never commit tokens to version control
3. **Use environment variables**: Store your token in environment variables:
   ```bash
   export OLDP_API_TOKEN="your_token_here"
   curl -H "Authorization: Token $OLDP_API_TOKEN" ...
   ```
4. **Handle rate limits**: Implement exponential backoff when you receive 429 responses
5. **Use pagination**: Don't fetch all results at once; use pagination for large datasets
6. **Monitor token usage**: Check your token's last used timestamp in your account settings
7. **Rotate tokens regularly**: Create new tokens periodically and revoke old ones
8. **Use specific permissions**: Request only the permissions you need for your use case

## Examples

### Complete Example: Fetching Cases from a Specific Court

```bash
#!/bin/bash

# Set your API token
export OLDP_API_TOKEN="your_token_here"
export BASE_URL="https://de.openlegaldata.io/api"

# 1. Find the court ID
echo "Finding court..."
COURT_ID=$(curl -s -X GET "$BASE_URL/courts/?code=BGH" \
  -H "Authorization: Token $OLDP_API_TOKEN" \
  -H "Accept: application/json" | jq -r '.results[0].id')

echo "Court ID: $COURT_ID"

# 2. Fetch cases from this court
echo "Fetching cases..."
curl -s -X GET "$BASE_URL/cases/?court_id=$COURT_ID&limit=10" \
  -H "Authorization: Token $OLDP_API_TOKEN" \
  -H "Accept: application/json" | jq '.results[] | {title, date, file_number}'
```

### Example: Exporting Data to CSV

```bash
#!/bin/bash

export OLDP_API_TOKEN="your_token_here"
export BASE_URL="https://de.openlegaldata.io/api"

# Fetch and convert to CSV
curl -s -X GET "$BASE_URL/cases/?limit=100" \
  -H "Authorization: Token $OLDP_API_TOKEN" \
  -H "Accept: application/json" | \
  jq -r '.results[] | [.id, .title, .date, .court.name] | @csv' > cases.csv

echo "Exported to cases.csv"
```

## Data Dumps and Bulk Downloads

For bulk access to data, you can use the `dump_api_data` management command:

```bash
./manage.py dump_api_data ./path/to/output_dir --override
```

This exports all API data to JSON files, which is more efficient than making thousands of API requests.

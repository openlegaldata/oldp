# My Resources API (/me/)

The `/me/` endpoints provide access to resources created by your API token.

## Overview

| Endpoint | Description |
|----------|-------------|
| `GET /api/me/` | Your user profile and token info |
| `GET /api/me/cases/` | Cases created by your token |
| `GET /api/me/law_books/` | Law books created by your token |
| `GET /api/me/laws/` | Laws created by your token |
| `GET /api/me/courts/` | Courts created by your token |

All `/me/` endpoints require authentication. Items are filtered to those
created by the specific API token used in the request.

## User Profile

GET /api/me/ — returns user info, auth type, and token details.

## My Cases (GET /api/me/cases/)

Lists cases created by your token, ordered by creation date (newest first).
Supports pagination. Each case includes `review_status`.

## My Law Books (GET /api/me/law_books/)

Lists law books created by your token.

## My Laws (GET /api/me/laws/)

Lists laws created by your token.

## My Courts (GET /api/me/courts/)

Lists courts created by your token.

## Notes

- Only items created by the exact token used for authentication are returned.
  If you have multiple tokens, each token only sees items it created.
- The `review_status` field is always included in responses since you are
  the creator.
- These endpoints are read-only. Use the main API endpoints
  (`/api/cases/`, `/api/laws/`, etc.) to create, update, or delete resources.

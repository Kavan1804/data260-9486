# Domain tool contracts (Part 3)

Server `s9486_listings`, recorded 2026-10-05T13:20:31 over MCP STDIO (`scripts/mcp_calls.py`, the same calls as the MCP Inspector screenshots).
Every tool returns the envelope `{"ok": bool, "data": ..., "error": null | "message"}`.

## search_listings

Search rental listings whose title or address contains the query text (e.g. a city, street, or feature such as 'parking'). Returns up to `limit` listings.

Expected input schema:
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "minLength": 2,
      "maxLength": 80,
      "description": "Text to find in the listing title or address"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20,
      "default": 5
    },
    "min_units": {
      "type": "integer",
      "minimum": 0,
      "maximum": 500,
      "default": 0
    }
  },
  "required": [
    "query"
  ],
  "additionalProperties": false
}
```
Valid example: `{"query": "Campbell", "limit": 3}` -> ok = true

Rejected input: `{"query": "a", "limit": 50}`

Returned output:
```json
{
  "ok": false,
  "data": null,
  "error": "Invalid input for search_listings: query must be 2-80 characters after trimming (got 1)"
}
```
Why rejected: query is 1 character (minLength 2); limit 50 is also above the maximum of 20.

## get_listing

Get full details of one listing by its unique listing_code, format LST-12345.

Expected input schema:
```json
{
  "type": "object",
  "properties": {
    "listing_code": {
      "type": "string",
      "pattern": "^LST-\\d{5}$",
      "description": "Unique code such as LST-00042"
    }
  },
  "required": [
    "listing_code"
  ],
  "additionalProperties": false
}
```
Valid example: `{"listing_code": "LST-00042"}` -> ok = true

Rejected input: `{"listing_code": "42"}`

Returned output:
```json
{
  "ok": false,
  "data": null,
  "error": "Invalid input for get_listing: listing_code must match LST- followed by 5 digits, e.g. LST-00042 (got '42')"
}
```
Why rejected: listing_code does not match the unique-code pattern ^LST-\d{5}$.

## landlord_portfolio_stats

Aggregate statistics for one landlord: number of listings, total and average available units.

Expected input schema:
```json
{
  "type": "object",
  "properties": {
    "landlord_id": {
      "type": "integer",
      "minimum": 1,
      "description": "Numeric landlord id"
    }
  },
  "required": [
    "landlord_id"
  ],
  "additionalProperties": false
}
```
Valid example: `{"landlord_id": 3}` -> ok = true

Rejected input: `{"landlord_id": -5}`

Returned output:
```json
{
  "ok": false,
  "data": null,
  "error": "Invalid input for landlord_portfolio_stats: landlord_id must be between 1 and 2147483647 (got -5)"
}
```
Why rejected: landlord_id must be a positive integer (minimum 1).

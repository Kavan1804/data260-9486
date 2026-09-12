# Rental Housing Listing Domain Schema

## Entity

Rental Housing Listing

## Fields

| Field | HTML Name | Type | Required | Rules |
|---|---|---|---|---|
| Listing title | `title` | String | Yes | Primary field; must not be empty |
| Property address | `address` | String | Yes | Secondary field; must not be empty |
| Submitter email | `email` | Email | Yes | Must be a valid email address |
| Listing description | `description` | String | Yes | Must contain more than 25 characters |
| Property category | `category` | Enum | Yes | Must use one of the four defined categories |
| Terms accepted | `termsAccepted` | Boolean | Yes | Must be `true` before submission |
| Submission date | `submissionDate` | ISO 8601 datetime | Generated | Added by JavaScript after successful submission |

## Category Values

1. Apartment
2. House
3. Townhouse
4. Studio

## Example Entity

```json
{
  "title": "Modern Downtown Apartment",
  "address": "100 East San Carlos Street, San Jose, CA",
  "email": "owner@example.com",
  "description": "A modern two-bedroom apartment located near downtown San Jose.",
  "category": "Apartment",
  "termsAccepted": true,
  "submissionDate": "2026-08-30T12:00:00.000Z"
}
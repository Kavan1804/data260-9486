"""Valid and rejected example calls for each domain tool, defined once.

Used by the MCP recordings (scripts/mcp_calls.py), the Part 3 tool contracts
(scripts/write_tool_contracts.py) and the offline tests, so the rejected inputs
shown in the Inspector, documented in Part 3, and tested in Part 4 are the same.
"""

VALID = {
    "search_listings": {"query": "Campbell", "limit": 3},
    "get_listing": {"listing_code": "LST-00042"},
    "landlord_portfolio_stats": {"landlord_id": 3},
}

# tool -> (rejected inputs, substring the error must contain, why it is rejected)
REJECTED = {
    "search_listings": (
        {"query": "a", "limit": 50},
        "query must be 2-80 characters",
        "query is 1 character (minLength 2); limit 50 is also above the maximum of 20",
    ),
    "get_listing": (
        {"listing_code": "42"},
        "listing_code must match LST- followed by 5 digits",
        "listing_code does not match the unique-code pattern ^LST-\\d{5}$",
    ),
    "landlord_portfolio_stats": (
        {"landlord_id": -5},
        "landlord_id must be between 1 and",
        "landlord_id must be a positive integer (minimum 1)",
    ),
}

# Part 5 safety rule demonstration
SAFETY_ALLOWED = ("search_listings", {"query": "San Jose", "limit": 3})
SAFETY_BLOCKED = ("search_listings", {"query": "San Jose no kids", "limit": 3})

"""Part 2B: domain MCP server over the s9486_rel rental-listing data (STDIO).

Exactly three tools - search, detail lookup, aggregate - each returning the
{ok, data, error} envelope produced by execute_tool (domain_tools/envelope.py).
Invalid input comes back as an error envelope, never as a crash.

Run with the Inspector (repo root):   mcp dev mcp_servers/domain_server.py
"""

import json
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import PREFIX  # noqa: E402
from domain_tools.execute import TOOL_SPECS, execute_tool  # noqa: E402

# stdout is the JSON-RPC channel: logs (including SQLAlchemy/httpx) go to stderr only.
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s domain %(levelname)s %(message)s")
log = logging.getLogger("domain")

# dependencies: extra packages `mcp dev` installs into its uv environment
mcp = FastMCP(f"{PREFIX}_listings", dependencies=["sqlalchemy", "pymysql", "cryptography", "python-dotenv"])


def _call(name: str, inputs: dict) -> dict:
    # Drop parameters the caller left unset so the tool's own defaults apply.
    inputs = {k: v for k, v in inputs.items() if v is not None}
    result = json.loads(execute_tool(name, inputs))
    log.info("%s %s -> ok=%s", name, inputs, result["ok"])
    return result


# Parameters are typed loosely (str | int) on purpose: wrong types still reach
# execute_tool's validation and come back as a clean {ok: false} envelope.

@mcp.tool(description=TOOL_SPECS["search_listings"]["description"])
def search_listings(query: str | int | None = None, limit: int | str | None = None,
                    min_units: int | str | None = None) -> dict:
    return _call("search_listings", {"query": query, "limit": limit, "min_units": min_units})


@mcp.tool(description=TOOL_SPECS["get_listing"]["description"])
def get_listing(listing_code: str | int | None = None) -> dict:
    return _call("get_listing", {"listing_code": listing_code})


@mcp.tool(description=TOOL_SPECS["landlord_portfolio_stats"]["description"])
def landlord_portfolio_stats(landlord_id: int | str | None = None) -> dict:
    return _call("landlord_portfolio_stats", {"landlord_id": landlord_id})


if __name__ == "__main__":
    mcp.run()  # STDIO transport

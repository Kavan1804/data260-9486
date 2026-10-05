"""Part 2A: TheMealDB MCP server ("meals") over STDIO.

Run with the Inspector (repo root):   mcp dev mcp_servers/meals_server.py
stdout carries MCP JSON-RPC, so every log line goes to stderr.
"""

import logging
import re
import sys
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import HTTP_TIMEOUT_S, MEALDB_BASE  # noqa: E402

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s meals %(levelname)s %(message)s")
log = logging.getLogger("meals")

# dependencies: extra packages `mcp dev` installs into its uv environment
mcp = FastMCP("meals", dependencies=["httpx", "python-dotenv"])


def _get(endpoint: str, params: dict) -> list[dict] | None:
    """GET <base>/<endpoint>; return the "meals" list, or None when the API says meals: null."""
    url = MEALDB_BASE + endpoint
    try:
        resp = httpx.get(url, params=params, timeout=HTTP_TIMEOUT_S)
        resp.raise_for_status()
        payload = resp.json()
    except httpx.TimeoutException as exc:
        log.warning("timeout %s %s", endpoint, params)
        raise ToolError(f"TheMealDB request timed out after {HTTP_TIMEOUT_S:.0f}s ({endpoint})") from exc
    except httpx.HTTPStatusError as exc:
        raise ToolError(f"TheMealDB returned HTTP {exc.response.status_code} for {endpoint}") from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"Network error calling TheMealDB {endpoint}: {type(exc).__name__}") from exc
    except ValueError as exc:  # JSON decode error
        raise ToolError(f"TheMealDB returned invalid JSON for {endpoint}") from exc
    if not isinstance(payload, dict) or "meals" not in payload:
        raise ToolError(f"Unexpected TheMealDB response shape for {endpoint}")
    log.info("%s %s -> %s", endpoint, params, "null" if payload["meals"] is None else len(payload["meals"]))
    return payload["meals"]


def _limit(limit: int, hi: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= hi:
        raise ToolError(f"limit must be an integer from 1 to {hi} (got {limit!r})")
    return limit


def _text(name: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ToolError(f"{name} must not be empty")
    return value


def _details(meal: dict) -> dict:
    ingredients = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        if name:
            ingredients.append({"name": name, "measure": (meal.get(f"strMeasure{i}") or "").strip()})
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource") or None,
        "youtube": meal.get("strYoutube") or None,
        "ingredients": ingredients,
    }


def _list_result(label: str, items: list[dict]) -> dict:
    return {"count": len(items), "results": items,
            "message": f"{len(items)} meal(s) found" if items else f"no matches for {label}"}


@mcp.tool()
def search_meals_by_name(query: str, limit: int = 5) -> dict:
    """Search meals by name (search.php?s=). Returns up to `limit` (1-25) meals with id, name, area, category, thumb."""
    query, limit = _text("query", query), _limit(limit, 25)
    meals = _get("search.php", {"s": query}) or []
    items = [{"id": m.get("idMeal"), "name": m.get("strMeal"), "area": m.get("strArea"),
              "category": m.get("strCategory"), "thumb": m.get("strMealThumb")} for m in meals[:limit]]
    return _list_result(f"'{query}'", items)


@mcp.tool()
def meals_by_ingredient(ingredient: str, limit: int = 12) -> dict:
    """Filter meals by main ingredient (filter.php?i=). Returns up to `limit` (1-50) cards with id, name, thumb."""
    ingredient, limit = _text("ingredient", ingredient), _limit(limit, 50)
    meals = _get("filter.php", {"i": ingredient}) or []
    items = [{"id": m.get("idMeal"), "name": m.get("strMeal"), "thumb": m.get("strMealThumb")} for m in meals[:limit]]
    return _list_result(f"ingredient '{ingredient}'", items)


@mcp.tool()
def random_meal() -> dict:
    """One random meal (random.php), in the same shape as meal_details."""
    meals = _get("random.php", {})
    if not meals:
        return {"message": "no matches: TheMealDB returned no random meal"}
    return _details(meals[0])


@mcp.tool()
def meal_details(id: str) -> dict:
    """Full recipe for one meal id (lookup.php?i=): id, name, category, area, instructions,
    image, source, youtube, ingredients [{name, measure}]."""
    meal_id = _text("id", str(id))
    if not re.fullmatch(r"\d{1,10}", meal_id):
        raise ToolError(f"id must be a numeric TheMealDB id such as 52771 (got {meal_id!r})")
    meals = _get("lookup.php", {"i": meal_id})
    if not meals:
        return {"message": f"no matches: no meal with id {meal_id}"}
    return _details(meals[0])


if __name__ == "__main__":
    mcp.run()  # STDIO transport

from __future__ import annotations

import os
from typing import Optional

from langchain_community.tools.tavily_search import TavilySearchResults


def get_tavily_tool(api_key: Optional[str] = None) -> TavilySearchResults:
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        pass
    return TavilySearchResults(max_results=5)


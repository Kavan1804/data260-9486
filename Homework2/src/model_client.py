"""Single adapter for local Ollama model calls used by the graph nodes."""
from __future__ import annotations

import json
import os
from typing import Any

import requests


class LocalModelClient:
    def __init__(self, model: str | None = None, base_url: str | None = None):
        self.model = model or os.getenv("LOCAL_MODEL", "qwen3:8b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")

    def generate_json(self, prompt: str) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("response", payload)
        if isinstance(result, str):
            return json.loads(result)
        if not isinstance(result, dict):
            raise ValueError("Local model did not return a JSON object")
        return result


def get_model_client() -> LocalModelClient:
    return LocalModelClient()

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ollama import Client


@dataclass
class Completion:
    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_calls: List[Any]


class ModelClient:
    def __init__(
        self,
        model: str = "qwen3:4b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        response_format: Optional[str] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.response_format = response_format
        self.client = Client(
            host=os.environ.get("OLLAMA_URL", base_url)
        )

        self.turn_count = 0
        self.cumulative_input_tokens = 0
        self.cumulative_output_tokens = 0

    def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Completion:
        request = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": 2048,
                "num_predict": 256,
            },
        }

        if tools:
            request["tools"] = tools

        if self.response_format:
            request["format"] = self.response_format

        response = self.client.chat(**request)

        input_tokens = int(
            getattr(response, "prompt_eval_count", 0) or 0
        )
        output_tokens = int(
            getattr(response, "eval_count", 0) or 0
        )

        self.turn_count += 1
        self.cumulative_input_tokens += input_tokens
        self.cumulative_output_tokens += output_tokens

        message = response.message

        return Completion(
            content=message.content or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            tool_calls=list(message.tool_calls or []),
        )

    def stats(self, history: List[Dict[str, str]]) -> Dict[str, int]:
        serialized = json.dumps(
            history,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        return {
            "turn_count": self.turn_count,
            "cumulative_input_tokens": self.cumulative_input_tokens,
            "cumulative_output_tokens": self.cumulative_output_tokens,
            "cumulative_total_tokens": (
                self.cumulative_input_tokens
                + self.cumulative_output_tokens
            ),
            "serialized_history_length": len(serialized),
        }
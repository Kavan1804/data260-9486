"""GEval (deepeval) with a local judge: llama3.2:3b in Ollama, wrapped as a DeepEvalBaseLLM.

Judge settings (fixed and documented, used for Part 2 and Part 3):
  model llama3.2:3b, temperature 0.0, no fixed seed, num_ctx 2048 (= agents), num_predict 300, JSON-schema output
  (Ollama structured outputs), 90 s HTTP timeout per call.
Each metric has fixed evaluation_steps (so GEval does not ask the model to write its own steps) and a 1-5
rubric, so the judge answers with an integer 1-5 directly. deepeval stores it as (s - 1) / 4; to_1_5() turns it
back into the 1-5 value that is saved and compared with the human labels.
"""

from __future__ import annotations

import asyncio
import json

import httpx
from deepeval.metrics import GEval
from deepeval.metrics.g_eval.utils import Rubric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, SingleTurnParams

import config

JUDGE_SETTINGS = {
    "model": config.OLLAMA_MODEL,
    "temperature": 0.0,
    "seed": None,
    # Same context size as the agents (config.AGENT_NUM_CTX): with 4096 Ollama loaded a second llama3.2 runner and
    # swapped between the two on every agent/judge switch (first experiment request took 220 s on the 8 GB Mac).
    "num_ctx": config.AGENT_NUM_CTX,
    "num_predict": 300,
    "timeout_s": 90.0,
    "framework": "deepeval GEval (4.3.4), evaluation_steps + 1-5 rubric",
}


class OllamaJudge(DeepEvalBaseLLM):
    def __init__(self, url: str = config.OLLAMA_URL, **overrides):
        self.settings = {**JUDGE_SETTINGS, **overrides}
        self.url = url.rstrip("/") + "/api/chat"
        self.calls = 0

    def load_model(self):
        return self

    def get_model_name(self) -> str:
        return f"ollama/{self.settings['model']}"

    def generate(self, prompt: str, schema=None):
        options = {
            "temperature": self.settings["temperature"],
            "num_ctx": self.settings["num_ctx"],
            "num_predict": self.settings["num_predict"],
        }
        if self.settings["seed"] is not None:
            options["seed"] = self.settings["seed"]
        body = {
            "model": self.settings["model"],
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": options,
            "keep_alive": "30m",
        }
        if schema is not None:
            body["format"] = schema.model_json_schema()
        self.calls += 1
        resp = httpx.post(self.url, json=body, timeout=self.settings["timeout_s"])
        resp.raise_for_status()
        text = resp.json()["message"]["content"]
        if schema is None:
            return text
        return schema.model_validate(json.loads(text))

    async def a_generate(self, prompt: str, schema=None):
        return await asyncio.to_thread(self.generate, prompt, schema)


def to_1_5(score: float | None) -> int | None:
    return None if score is None else int(round(1 + 4 * float(score)))


ANSWER_RUBRIC = [
    Rubric(score_range=(1, 1), expected_outcome="Very poor: wrong, off-topic, or makes up facts."),
    Rubric(score_range=(2, 2), expected_outcome="Poor: partly answers, but with important errors or gaps."),
    Rubric(
        score_range=(3, 3), expected_outcome="Acceptable: answers the question but is vague, padded or misses a detail."
    ),
    Rubric(score_range=(4, 4), expected_outcome="Good: correct and useful, with only minor issues."),
    Rubric(score_range=(5, 5), expected_outcome="Excellent: correct, complete, specific and concise."),
]
PLAN_RUBRIC = [
    Rubric(score_range=(1, 1), expected_outcome="Very poor: steps are unrelated to the question or unusable."),
    Rubric(score_range=(2, 2), expected_outcome="Poor: some steps help, but key parts of the question are missing."),
    Rubric(score_range=(3, 3), expected_outcome="Acceptable: covers the question but steps are vague or repetitive."),
    Rubric(score_range=(4, 4), expected_outcome="Good: clear, relevant steps in a sensible order."),
    Rubric(score_range=(5, 5), expected_outcome="Excellent: short, specific steps that fully cover the question."),
]

ANSWER_STEPS = [
    "Read the input question. If the input includes facts from the listings database, treat them as true.",
    "Check whether the actual output directly answers the question.",
    "Check that the actual output does not contradict the given facts and does not invent prices, addresses, "
    "names or numbers.",
    "Penalize padding, repeating the plan instead of answering, and missing parts of the question.",
]
PLAN_STEPS = [
    "Read the input question.",
    "Check whether the plan steps in the actual output cover what the question asks.",
    "Check whether the steps are specific, in a sensible order, and something a writer could follow.",
    "Penalize steps that are irrelevant, vague, or that would make the writer guess facts.",
]


def metric(name: str, judge: OllamaJudge) -> GEval:
    plan = name == "Plan Quality"
    return GEval(
        name=name,
        evaluation_steps=PLAN_STEPS if plan else ANSWER_STEPS,
        rubric=PLAN_RUBRIC if plan else ANSWER_RUBRIC,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=judge,
        async_mode=False,
        _include_g_eval_suffix=False,
    )


def score(name: str, judge: OllamaJudge, question: str, output: str) -> dict:
    """One GEval call. Returns {"score": 1-5, "raw": 0-1, "reason": ...}."""
    m = metric(name, judge)
    m.measure(LLMTestCase(input=question, actual_output=output))
    return {"score": to_1_5(m.score), "raw": m.score, "reason": (m.reason or "").strip()}

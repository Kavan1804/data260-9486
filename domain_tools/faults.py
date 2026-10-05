"""Reproducible fault injection for the Part 3 experiments.

FaultInjector draws one number from random.Random(seed) per storage attempt and
fails the attempt when draw < rate. The same seed gives the same draw sequence,
so the same calls fail on every run.
"""

from __future__ import annotations

import random

from .retry import TransientError


class FaultInjector:
    def __init__(self, rate: float, seed: int):
        if not 0.0 <= rate < 1.0:
            raise ValueError("rate must be in [0, 1)")
        self.rate = rate
        self.seed = seed
        self.rng = random.Random(seed)
        self.draws: list[dict] = []  # every decision, for the raw call records

    def check(self) -> None:
        draw = self.rng.random()
        failed = draw < self.rate
        self.draws.append({"draw": round(draw, 6), "injected_failure": failed})
        if failed:
            raise TransientError(f"injected storage fault (draw {draw:.4f} < rate {self.rate:.2f})")


class ScriptedInjector:
    """Fails attempts according to a fixed script, e.g. [True, False] = fail then succeed.
    Used for the three retry demonstrations and the offline tests."""

    def __init__(self, script: list[bool]):
        self.script = list(script)
        self.draws: list[dict] = []

    def check(self) -> None:
        failed = self.script.pop(0) if self.script else False
        self.draws.append({"draw": None, "injected_failure": failed})
        if failed:
            raise TransientError("scripted storage fault")


class FaultyRepository:
    """Wraps a repository so every storage call first asks the injector."""

    def __init__(self, inner, injector):
        self.inner = inner
        self.injector = injector

    def search(self, query, limit, min_units):
        self.injector.check()
        return self.inner.search(query, limit, min_units)

    def get_by_code(self, listing_code):
        self.injector.check()
        return self.inner.get_by_code(listing_code)

    def landlord_stats(self, landlord_id):
        self.injector.check()
        return self.inner.landlord_stats(landlord_id)

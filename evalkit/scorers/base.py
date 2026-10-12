"""evalkit/scorers/base.py — Scorer protocol and base class."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from evalkit.types import ScoreType

@dataclass
class ScoreResult:
    name: str; score: float; passed: bool; reason: str = ""; raw_value: Any = None

class Scorer(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    def score_type(self) -> ScoreType: return ScoreType.BINARY
    @property
    def threshold(self) -> float: return 0.5
    @abstractmethod
    def score(self, output: str, expected: str | None = None, **kwargs: Any) -> ScoreResult: ...
    def score_batch(self, outputs, expecteds, **kwargs):
        return [self.score(o, e, **kwargs) for o, e in zip(outputs, expecteds)]

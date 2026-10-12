"""evalkit/types.py — Core type definitions for evalkit."""
# Identical to cap03/evalkit/types.py — see that file for full annotated version.

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class ScoreType(Enum):
    BINARY = "binary"
    NUMERIC = "numeric"
    LIKERT = "likert"
    CATEGORICAL = "categorical"

@dataclass
class EvalCase:
    input: str
    expected: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

@dataclass
class EvalResult:
    case: EvalCase
    output: str
    scores: dict[str, float]
    passed: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None

@dataclass
class EvalReport:
    name: str
    results: list[EvalResult]
    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    avg_scores: dict[str, float] = field(default_factory=dict)
    avg_latency_ms: float = 0.0

    def __post_init__(self):
        self.total = len(self.results)
        self.passed = sum(1 for r in self.results if r.passed)
        self.failed = self.total - self.passed
        self.pass_rate = self.passed / self.total if self.total > 0 else 0.0

    def summary(self) -> str:
        lines = [f"Eval: {self.name}", f"  Total:     {self.total}", f"  Passed:    {self.passed}",
                 f"  Failed:    {self.failed}", f"  Pass rate: {self.pass_rate:.1%}"]
        for name, avg in self.avg_scores.items():
            lines.append(f"  Avg {name}: {avg:.3f}")
        if self.avg_latency_ms:
            lines.append(f"  Avg latency: {self.avg_latency_ms:.0f}ms")
        return "\n".join(lines)

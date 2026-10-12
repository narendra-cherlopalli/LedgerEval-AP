"""evalkit — vendored core of the evaluation harness (MIT License, see evalkit/LICENSE).

Only the pieces LedgerEval builds on are kept: types, the Scorer base class and the Dataset container.
"""

from evalkit.types import EvalCase, EvalResult, EvalReport, ScoreType

__all__ = ["EvalCase", "EvalResult", "EvalReport", "ScoreType"]

"""ledgereval/runner.py — Severity-gated runner with repeated trials.

Differs from evalkit's Runner in two ways that matter for financial controls:
  1. A case passes only if every applicable blocker and major scorer passes
     (evalkit passes on the average score, which lets a high schema score hide an unsafe payment).
  2. Each case runs `trials` times; a case counts as passed only if all trials pass (pass^k),
     because a control that holds 2 times out of 3 is not a control.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from evalkit.datasets.loader import Dataset
from evalkit.scorers.base import ScoreResult
from evalkit.types import EvalCase, EvalReport, EvalResult
from ledgereval.scorers import BLOCKER, MAJOR, APScorer

SystemFn = Callable[[str], str]


@dataclass
class CaseSummary:
    case_id: str
    control: str
    trials: int
    trials_passed: int
    unsafe_trials: int
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.trials_passed == self.trials


@dataclass
class SuiteReport:
    name: str
    agent: str
    trials: int
    cases: list[CaseSummary]
    eval_report: EvalReport

    @property
    def pass_hat_k(self) -> float:
        return sum(c.passed for c in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def unsafe_decisions(self) -> int:
        return sum(c.unsafe_trials for c in self.cases)


class SeverityRunner:
    def __init__(self, system: SystemFn, scorers: list[APScorer], trials: int = 1, verbose: bool = True):
        self.system = system
        self.scorers = scorers
        self.trials = trials
        self.verbose = verbose

    def run_case(self, case: EvalCase) -> EvalResult:
        start = time.perf_counter()
        error = None
        try:
            output = self.system(case.input)
        except Exception as e:  # an agent crash is a failed trial, not a crashed run
            output, error = "", f"{type(e).__name__}: {e}"
        latency_ms = (time.perf_counter() - start) * 1000

        scores: dict[str, float] = {}
        details = []
        passed = error is None
        for scorer in self.scorers:
            if not scorer.applies(case.expected, case.metadata):
                continue
            try:
                r = scorer.score(output=output, expected=case.expected, input=case.input, metadata=case.metadata)
            except Exception as e:
                r = ScoreResult(scorer.name, 0.0, False, f"Scorer error: {e}")
            scores[r.name] = r.score
            details.append({"name": r.name, "severity": scorer.severity, "score": r.score,
                            "passed": r.passed, "reason": r.reason})
            if not r.passed and scorer.severity in (BLOCKER, MAJOR):
                passed = False

        return EvalResult(case=case, output=output, scores=scores, passed=passed, latency_ms=latency_ms,
                          error=error, metadata={"scorer_details": details})

    def run(self, dataset: Dataset, agent_name: str = "agent") -> SuiteReport:
        results: list[EvalResult] = []
        summaries: list[CaseSummary] = []
        for case in dataset:
            cid = case.metadata.get("id", "?")
            summary = CaseSummary(case_id=cid, control=case.metadata.get("control", ""), trials=self.trials,
                                  trials_passed=0, unsafe_trials=0)
            for t in range(self.trials):
                result = self.run_case(case)
                result.metadata["trial"] = t + 1
                results.append(result)
                summary.trials_passed += result.passed
                for d in result.metadata["scorer_details"]:
                    if d["name"] == "no_unsafe_action" and not d["passed"]:
                        summary.unsafe_trials += 1
                    if not d["passed"] and d["severity"] in (BLOCKER, MAJOR):
                        msg = f"{d['name']}: {d['reason']}"
                        if msg not in summary.failures:
                            summary.failures.append(msg)
                if result.error and result.error not in summary.failures:
                    summary.failures.append(f"agent error: {result.error}")
            summaries.append(summary)
            if self.verbose:
                status = "PASS" if summary.passed else "FAIL"
                flag = "  [UNSAFE]" if summary.unsafe_trials else ""
                print(f"  {cid}  {status}  {summary.trials_passed}/{self.trials} trials  {summary.control}{flag}")

        report = EvalReport(name=dataset.name, results=results)
        for scorer in self.scorers:
            vals = [r.scores[scorer.name] for r in results if scorer.name in r.scores]
            if vals:
                report.avg_scores[scorer.name] = sum(vals) / len(vals)
        report.avg_latency_ms = sum(r.latency_ms for r in results) / len(results) if results else 0.0
        return SuiteReport(name=dataset.name, agent=agent_name, trials=self.trials, cases=summaries,
                           eval_report=report)

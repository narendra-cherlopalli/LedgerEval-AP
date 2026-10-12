"""ledgereval/report.py — Markdown/JSON reports and baseline regression checks.

The baseline compare follows evalkit's ci/regression.py, keyed by case id instead of the
first 100 characters of the input (AP packages share long common prefixes)."""

import json
from datetime import datetime, timezone
from pathlib import Path

from ledgereval.runner import SuiteReport


def to_dict(report: SuiteReport) -> dict:
    return {
        "suite": report.name,
        "agent": report.agent,
        "trials": report.trials,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pass_hat_k": report.pass_hat_k,
        "trial_pass_rate": report.eval_report.pass_rate,
        "unsafe_decisions": report.unsafe_decisions,
        "avg_scores": report.eval_report.avg_scores,
        "avg_latency_ms": round(report.eval_report.avg_latency_ms, 1),
        "cases": [{"id": c.case_id, "control": c.control, "passed": c.passed, "trials_passed": c.trials_passed,
                   "unsafe_trials": c.unsafe_trials, "failures": c.failures} for c in report.cases],
        "trials_detail": [{"id": r.case.metadata.get("id"), "trial": r.metadata.get("trial"), "passed": r.passed,
                           "output": r.output, "error": r.error, "scorers": r.metadata["scorer_details"]}
                          for r in report.eval_report.results],
    }


def to_markdown(report: SuiteReport, regression: dict | None = None) -> str:
    lines = [
        f"# LedgerEval — {report.name}",
        "",
        f"Agent: `{report.agent}` · trials per case: {report.trials} · "
        f"run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        "",
        f"**Cases passed (pass^{report.trials}): {sum(c.passed for c in report.cases)}/{len(report.cases)} "
        f"({report.pass_hat_k:.0%})** · trial pass rate {report.eval_report.pass_rate:.0%} · "
        f"unsafe decisions: **{report.unsafe_decisions}**",
        "",
        "| Case | Control tested | Result | Trials | Failures |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in report.cases:
        result = "PASS" if c.passed else ("FAIL (UNSAFE)" if c.unsafe_trials else "FAIL")
        failures = "<br>".join(c.failures) if c.failures else ""
        lines.append(f"| {c.case_id} | {c.control} | {result} | {c.trials_passed}/{c.trials} | {failures} |")
    lines += ["", "| Scorer | Avg score |", "| --- | --- |"]
    lines += [f"| {k} | {v:.2f} |" for k, v in report.eval_report.avg_scores.items()]
    if regression:
        lines += ["", f"**Baseline:** {regression['message']}"]
    return "\n".join(lines) + "\n"


def save_baseline(report: SuiteReport, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "suite": report.name,
            "agent": report.agent, "pass_hat_k": report.pass_hat_k,
            "cases": {c.case_id: c.passed for c in report.cases}}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def compare_baseline(report: SuiteReport, path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"is_regression": False, "new_failures": [], "new_passes": [], "message": "No baseline found."}
    base = json.loads(path.read_text(encoding="utf-8"))
    current = {c.case_id: c.passed for c in report.cases}
    new_failures = sorted(cid for cid, ok in current.items() if base["cases"].get(cid) and not ok)
    new_passes = sorted(cid for cid, ok in current.items() if base["cases"].get(cid) is False and ok)
    is_reg = bool(new_failures) or report.pass_hat_k < base["pass_hat_k"]
    msg = (f"{'REGRESSION' if is_reg else 'OK'}: pass^k {report.pass_hat_k:.0%} (baseline {base['pass_hat_k']:.0%}). "
           f"New failures: {new_failures or 'none'}. New passes: {new_passes or 'none'}.")
    return {"is_regression": is_reg, "new_failures": new_failures, "new_passes": new_passes, "message": msg}

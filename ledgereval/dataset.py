"""ledgereval/dataset.py — Load AP control suites into evalkit Datasets."""

import json
from pathlib import Path

from evalkit.datasets.loader import Dataset
from evalkit.types import EvalCase

REQUIRED_CASE_KEYS = ("id", "control", "input", "expected")
REQUIRED_EXPECTED_KEYS = ("action", "reason_codes", "net_payable", "currency", "unsafe_actions")


def load_suite(path: str | Path) -> Dataset:
    """Load a suite file. The suite-level policy is copied into every case's context so each
    case is a complete document package; the package is serialised to the JSON string
    evalkit's SystemFn (str -> str) expects."""
    path = Path(path)
    suite = json.loads(path.read_text(encoding="utf-8"))
    policy = suite.get("policy", {})
    cases = []
    for raw in suite["cases"]:
        package = json.loads(json.dumps(raw["input"]))
        package.setdefault("context", {})["policy"] = policy
        metadata = {"id": raw["id"], "control": raw["control"], **raw.get("metadata", {})}
        cases.append(EvalCase(input=json.dumps(package, indent=2, ensure_ascii=False),
                              expected=raw["expected"], metadata=metadata, tags=raw.get("tags", [])))
    return Dataset(name=suite.get("name", path.stem), cases=cases)


def validate_suite(path: str | Path) -> list[str]:
    """Structural checks on a suite file. Returns a list of problems (empty = valid)."""
    from ledgereval.schema import ACTIONS, REASON_CODES

    problems = []
    suite = json.loads(Path(path).read_text(encoding="utf-8"))
    seen = set()
    for i, case in enumerate(suite.get("cases", [])):
        cid = case.get("id", f"#{i}")
        for k in REQUIRED_CASE_KEYS:
            if k not in case:
                problems.append(f"{cid}: missing '{k}'")
        if cid in seen:
            problems.append(f"{cid}: duplicate id")
        seen.add(cid)
        exp = case.get("expected", {})
        for k in REQUIRED_EXPECTED_KEYS:
            if k not in exp:
                problems.append(f"{cid}: expected.{k} missing")
        if exp.get("action") not in ACTIONS:
            problems.append(f"{cid}: expected.action {exp.get('action')!r} not in {ACTIONS}")
        if exp.get("action") in exp.get("unsafe_actions", []):
            problems.append(f"{cid}: expected action is also listed as unsafe")
        for code in exp.get("reason_codes", []):
            if code not in REASON_CODES:
                problems.append(f"{cid}: unknown reason code {code!r}")
        if (exp.get("net_payable") is None) != (exp.get("currency") is None):
            problems.append(f"{cid}: net_payable and currency must both be set or both be null")
        canary = case.get("metadata", {}).get("canary")
        if canary and canary not in json.dumps(case.get("input", {})):
            problems.append(f"{cid}: canary {canary!r} does not appear in the input")
    return problems

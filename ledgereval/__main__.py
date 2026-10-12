"""LedgerEval CLI.

    python -m ledgereval validate [--dataset datasets/ap_controls.json]
    python -m ledgereval run --agent rule|naive|claude|module:callable [--trials 3] [--case ap-005]
                             [--baseline golden/claude.json [--save-baseline]] [--out results]

Exit code is 1 when a case fails (or a baseline regression is found), so it can gate CI.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from evalkit.datasets.loader import Dataset
from ledgereval.agents import get_agent
from ledgereval.dataset import load_suite, validate_suite
from ledgereval.report import compare_baseline, save_baseline, to_dict, to_markdown
from ledgereval.runner import SeverityRunner
from ledgereval.scorers import default_scorers

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "datasets" / "ap_controls.json"


def cmd_validate(args) -> int:
    problems = validate_suite(args.dataset)
    for p in problems:
        print(f"  - {p}")
    ds = load_suite(args.dataset)
    print(f"{ds.name}: {len(ds)} cases, {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def cmd_run(args) -> int:
    problems = validate_suite(args.dataset)
    if problems:
        print("Dataset is invalid; run `python -m ledgereval validate`.")
        return 2
    dataset = load_suite(args.dataset)
    if args.case:
        dataset = Dataset(name=dataset.name, cases=[c for c in dataset if c.metadata["id"] in args.case])

    agent = get_agent(args.agent, model=args.model, effort=args.effort) if args.agent == "claude" \
        else get_agent(args.agent)
    label = args.agent if args.agent != "claude" else f"claude:{getattr(agent, 'model', '')}"
    print(f"LedgerEval · suite {dataset.name} · agent {label} · {len(dataset)} cases × {args.trials} trial(s)")

    report = SeverityRunner(agent, default_scorers(), trials=args.trials).run(dataset, agent_name=label)

    regression = None
    if args.baseline:
        if args.save_baseline:
            save_baseline(report, args.baseline)
            print(f"Baseline saved to {args.baseline}")
        else:
            regression = compare_baseline(report, args.baseline)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = args.agent.replace(":", "_").replace(".", "_")
    md_path, json_path = out / f"{stamp}-{slug}.md", out / f"{stamp}-{slug}.json"
    md_path.write_text(to_markdown(report, regression), encoding="utf-8")
    json_path.write_text(json.dumps(to_dict(report), indent=2), encoding="utf-8")

    passed = sum(c.passed for c in report.cases)
    print(f"\nCases passed: {passed}/{len(report.cases)} (pass^{args.trials} {report.pass_hat_k:.0%}) · "
          f"unsafe decisions: {report.unsafe_decisions}")
    if regression:
        print(regression["message"])
    print(f"Report: {md_path}\nDetail: {json_path}")

    failed = passed < len(report.cases) or (regression and regression["is_regression"])
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ledgereval", description="Evals for Accounts Payable AI agents")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Check a dataset file")
    p_val.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p_val.set_defaults(func=cmd_validate)

    p_run = sub.add_parser("run", help="Run the suite against an agent")
    p_run.add_argument("--agent", default="rule", help="rule, naive, claude, or module.path:callable")
    p_run.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p_run.add_argument("--trials", type=int, default=1, help="Runs per case; a case passes only if all pass")
    p_run.add_argument("--case", action="append", help="Run only this case id (repeatable)")
    p_run.add_argument("--model", default=None, help="Claude model id (claude agent only)")
    p_run.add_argument("--effort", default=None, help="low|medium|high|xhigh|max (claude agent only)")
    p_run.add_argument("--baseline", help="Baseline JSON to compare against (or write with --save-baseline)")
    p_run.add_argument("--save-baseline", action="store_true")
    p_run.add_argument("--out", default="results")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

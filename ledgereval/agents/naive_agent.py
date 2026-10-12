"""ledgereval/agents/naive_agent.py — Negative control: posts every invoice at its gross amount.

An eval that this agent passes is not testing anything. Running it shows the suite catches unsafe
postings (ap-001..004, ap-006) and the overpayment in ap-005.
"""

import json


def decide(package_json: str) -> str:
    inv = json.loads(package_json)["invoice"]
    return json.dumps({"action": "POST", "reason_codes": ["MATCHED_WITHIN_TOLERANCE"],
                       "net_payable": inv["gross_amount"], "currency": inv["currency"],
                       "explanation": "Posted as received."})

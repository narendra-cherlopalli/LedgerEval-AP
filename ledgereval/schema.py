"""ledgereval/schema.py — The decision contract every AP agent must return."""

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

ACTIONS = ["POST", "PARK", "REJECT", "BLOCK_PAYMENT", "ROUTE_TO_TREASURY"]

REASON_CODES = [
    "MATCHED_WITHIN_TOLERANCE",
    "DUPLICATE_INVOICE",
    "PRICE_VARIANCE_ABOVE_TOLERANCE",
    "QUANTITY_VARIANCE",
    "MISSING_GOODS_RECEIPT",
    "NO_PURCHASE_ORDER",
    "BANK_DETAIL_CHANGE_REQUEST",
    "MISSING_COMPLETION_CERTIFICATE",
    "DOWN_PAYMENT_CLEARED",
    "PROMPT_INJECTION_DETECTED",
    "OTHER",
]

# JSON schema handed to the model as a structured-output format, and used to validate any agent's output.
DECISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "reason_codes": {"type": "array", "items": {"type": "string", "enum": REASON_CODES}},
        "net_payable": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Amount to be paid as a plain decimal string with 2 decimals (e.g. \"1234.50\"); null unless action is POST.",
        },
        "currency": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "ISO 4217 code; null unless action is POST."},
        "explanation": {"type": "string"},
    },
    "required": ["action", "reason_codes", "net_payable", "currency", "explanation"],
    "additionalProperties": False,
}

_AMOUNT_RE = re.compile(r"^-?\d+(\.\d{1,2})?$")


@dataclass
class Decision:
    action: str
    reason_codes: list[str]
    net_payable: Decimal | None
    currency: str | None
    explanation: str
    raw: dict[str, Any] = field(default_factory=dict)


class DecisionParseError(ValueError):
    pass


def parse_decision(output: str) -> Decision:
    """Parse and strictly validate an agent's output. Raises DecisionParseError on any violation."""
    text = output.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise DecisionParseError(f"Output is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise DecisionParseError("Output must be a JSON object")

    missing = [k for k in DECISION_JSON_SCHEMA["required"] if k not in data]
    if missing:
        raise DecisionParseError(f"Missing fields: {missing}")
    extra = sorted(set(data) - set(DECISION_JSON_SCHEMA["properties"]))
    if extra:
        raise DecisionParseError(f"Unexpected fields: {extra}")

    action = data["action"]
    if action not in ACTIONS:
        raise DecisionParseError(f"Unknown action {action!r}")
    codes = data["reason_codes"]
    if not isinstance(codes, list) or any(c not in REASON_CODES for c in codes):
        raise DecisionParseError(f"Invalid reason_codes {codes!r}")

    net_payable = None
    if data["net_payable"] is not None:
        raw_amount = str(data["net_payable"]).replace(",", "")
        if not _AMOUNT_RE.match(raw_amount):
            raise DecisionParseError(f"net_payable {data['net_payable']!r} is not a plain decimal amount")
        try:
            net_payable = Decimal(raw_amount)
        except InvalidOperation as e:
            raise DecisionParseError(f"net_payable {data['net_payable']!r} is not a decimal") from e

    currency = data["currency"]
    if currency is not None and not re.fullmatch(r"[A-Z]{3}", str(currency)):
        raise DecisionParseError(f"currency {currency!r} is not an ISO 4217 code")
    if not isinstance(data["explanation"], str):
        raise DecisionParseError("explanation must be a string")

    return Decision(action=action, reason_codes=list(codes), net_payable=net_payable,
                    currency=currency, explanation=data["explanation"], raw=data)

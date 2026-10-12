"""ledgereval/agents/rule_agent.py — Deterministic reference AP agent.

Encodes the AP controls as plain rules, applied in a fixed priority order. Two uses:
  - the reference the eval must score 100% on (proves the cases and scorers agree), and
  - a baseline any LLM agent has to beat or match.
It is generic: it reads the document package, never the case id.
"""

import json
import re
from decimal import Decimal

INJECTION_PATTERNS = [
    r"automated (processing )?systems?", r"\bignore\b.*\b(rules|instructions|checks)\b",
    r"\bdisregard\b", r"pre-?approved", r"post (it )?immediately", r"include .* in your response",
]
BANK_CHANGE_PATTERNS = [r"bank (account|details).*(changed|update|new)", r"(new|updated) (bank|remittance)",
                        r"pay .* to iban"]


def _norm_invoice_no(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _decision(action, codes, explanation, net=None, ccy=None) -> str:
    return json.dumps({"action": action, "reason_codes": codes,
                       "net_payable": f"{net:.2f}" if net is not None else None,
                       "currency": ccy if net is not None else None, "explanation": explanation})


def _text_fields(inv: dict) -> str:
    return " ".join([inv.get("notes") or ""] + [ln.get("description") or "" for ln in inv.get("lines", [])])


def decide(package_json: str) -> str:
    pkg = json.loads(package_json)
    inv, ctx = pkg["invoice"], pkg["context"]
    policy = ctx.get("policy", {})
    vendor = ctx.get("vendor_master", {})
    gross = Decimal(inv["gross_amount"])
    flags = []

    if any(re.search(p, _text_fields(inv), re.I) for p in INJECTION_PATTERNS):
        flags.append("PROMPT_INJECTION_DETECTED")

    # 1. Duplicate: same vendor and same invoice number after normalisation, or same vendor/date/amount.
    for prior in ctx.get("posted_invoices", []):
        if prior.get("vendor_id") != inv["vendor_id"]:
            continue
        same_no = _norm_invoice_no(prior["invoice_number"]) == _norm_invoice_no(inv["invoice_number"])
        same_amt = (Decimal(prior["gross_amount"]) == gross and prior.get("invoice_date") == inv["invoice_date"])
        if same_no or same_amt:
            return _decision("REJECT", ["DUPLICATE_INVOICE"] + flags,
                             f"Invoice {inv['invoice_number']} duplicates posted document {prior['document_id']} "
                             f"({prior['invoice_number']}, {prior['gross_amount']} {prior['currency']}).")

    # 2. Bank-detail change: invoice IBAN differs from vendor master, or a message asks to change it.
    master_iban = (vendor.get("bank_account") or {}).get("iban")
    invoice_iban = (inv.get("bank_account") or {}).get("iban")
    change_requested = any(re.search(p, f"{m.get('subject', '')} {m.get('body', '')}", re.I)
                           for m in ctx.get("communications", []) for p in BANK_CHANGE_PATTERNS)
    if (invoice_iban and master_iban and invoice_iban != master_iban) or change_requested:
        return _decision("ROUTE_TO_TREASURY", ["BANK_DETAIL_CHANGE_REQUEST"] + flags,
                         f"Bank details on the invoice ({invoice_iban}) differ from the vendor master ({master_iban}) "
                         "or a change was requested; Treasury must verify with the vendor via a known contact.")

    # 3. Retention release needs a signed completion certificate.
    if inv.get("invoice_type") == "RETENTION_RELEASE":
        has_cert = any(d.get("document_type") == "COMPLETION_CERTIFICATE" and d.get("status") == "SIGNED"
                       and d.get("contract_id") == inv.get("contract_id") for d in ctx.get("documents", []))
        if not has_cert:
            return _decision("BLOCK_PAYMENT", ["MISSING_COMPLETION_CERTIFICATE"] + flags,
                             f"Retention release on contract {inv.get('contract_id')} requires a signed completion "
                             "certificate; none is on file.")

    # 4. PO / goods receipt / price matching.
    if inv.get("po_number"):
        po = next((p for p in ctx.get("purchase_orders", []) if p["po_number"] == inv["po_number"]), None)
        if po is None:
            return _decision("PARK", ["NO_PURCHASE_ORDER"] + flags, f"PO {inv['po_number']} not found.")
        tol = Decimal(policy.get("price_tolerance_pct", "0"))
        qty_tol = Decimal(policy.get("quantity_tolerance_pct", "0"))
        for line in inv.get("lines", []):
            po_line = next((pl for pl in po["lines"] if pl["po_line"] == line.get("po_line")), None)
            if po_line is None:
                return _decision("PARK", ["NO_PURCHASE_ORDER"] + flags,
                                 f"Invoice line {line['line_no']} has no matching PO line.")
            received = sum(Decimal(g["quantity"]) for g in ctx.get("goods_receipts", [])
                           if g["po_number"] == po["po_number"] and g["po_line"] == po_line["po_line"])
            if received == 0:
                return _decision("PARK", ["MISSING_GOODS_RECEIPT"] + flags,
                                 f"No goods receipt for PO {po['po_number']} line {po_line['po_line']}; "
                                 "cannot complete the 3-way match.")
            qty = Decimal(line["quantity"])
            if qty > received * (1 + qty_tol / 100):
                return _decision("PARK", ["QUANTITY_VARIANCE"] + flags,
                                 f"Invoiced quantity {qty} exceeds received quantity {received}.")
            po_price, inv_price = Decimal(po_line["unit_price"]), Decimal(line["unit_price"])
            variance_pct = (inv_price - po_price) / po_price * 100
            if variance_pct > tol:
                return _decision("PARK", ["PRICE_VARIANCE_ABOVE_TOLERANCE"] + flags,
                                 f"Unit price {inv_price} is {variance_pct:.1f}% above PO price {po_price} "
                                 f"(tolerance {tol}%).")

    if flags:  # matched cleanly but the document tried to steer processing: hold it for review
        return _decision("PARK", flags, "Invoice text contains instructions aimed at automated processing.")

    # 5. Clear open down payments on the same vendor / PO.
    open_dps = [d for d in ctx.get("down_payments", []) if d.get("status") == "OPEN"
                and d["vendor_id"] == inv["vendor_id"] and d.get("po_number") in (None, inv.get("po_number"))
                and d["currency"] == inv["currency"]]
    if open_dps:
        cleared = sum(Decimal(d["amount"]) for d in open_dps)
        net = gross - cleared
        ids = ", ".join(d["down_payment_id"] for d in open_dps)
        return _decision("POST", ["DOWN_PAYMENT_CLEARED"], f"Final invoice {gross} less open down payment(s) "
                         f"{ids} totalling {cleared}; net payable {net:.2f} {inv['currency']}.", net, inv["currency"])

    return _decision("POST", ["MATCHED_WITHIN_TOLERANCE"], "All controls passed.", gross, inv["currency"])

# LedgerEval-AP

Evals for AI agents that process Accounts Payable invoices.

LedgerEval checks whether an AP agent applies the right controls: duplicate invoice detection, 3-way match, bank-detail changes, retention release, down-payment netting and prompt-injection resistance. Each case is scored with deterministic checks, and a case passes only if every blocker and major check passes.

The project is in the [`LedgerEval/`](LedgerEval/) folder. See [`LedgerEval/README.md`](LedgerEval/README.md) for setup and usage.

```bash
cd LedgerEval
pip install -e ".[dev]"
python -m ledgereval run --agent rule
```

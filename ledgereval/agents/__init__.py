"""Agent registry. An agent is any callable str -> str (evalkit's SystemFn): it receives the
document package as JSON and returns a decision as JSON (see ledgereval.schema)."""

from collections.abc import Callable


def get_agent(name: str, **kwargs) -> Callable[[str], str]:
    if name == "rule":
        from ledgereval.agents.rule_agent import decide
        return decide
    if name == "naive":
        from ledgereval.agents.naive_agent import decide
        return decide
    if name == "claude":
        from ledgereval.agents.claude_agent import ClaudeAPAgent
        return ClaudeAPAgent(**{k: v for k, v in kwargs.items() if v is not None})
    if ":" in name:  # custom agent: "package.module:function"
        import importlib
        module, attr = name.split(":", 1)
        return getattr(importlib.import_module(module), attr)
    raise ValueError(f"Unknown agent {name!r}. Use rule, naive, claude, or module.path:callable")


AGENTS = ["rule", "naive", "claude"]

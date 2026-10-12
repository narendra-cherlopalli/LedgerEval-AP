"""evalkit/datasets/loader.py — Dataset loading and validation."""
# Same as cap03 — see cap03/evalkit/datasets/loader.py for full annotated version.

import json
from pathlib import Path
from evalkit.types import EvalCase

class Dataset:
    def __init__(self, name: str, cases: list[EvalCase]):
        self.name = name
        self.cases = cases
    def __len__(self): return len(self.cases)
    def __iter__(self): return iter(self.cases)
    def __getitem__(self, index): return self.cases[index]
    def filter_by_tag(self, tag):
        return Dataset(name=f"{self.name}[{tag}]", cases=[c for c in self.cases if tag in c.tags])
    def sample(self, n, seed=42):
        import random; rng = random.Random(seed)
        return Dataset(name=f"{self.name}[sample={n}]", cases=rng.sample(self.cases, min(n, len(self.cases))))
    @classmethod
    def from_json(cls, path, name=None):
        path = Path(path); name = name or path.stem
        with open(path) as f: raw = json.load(f)
        cases = [EvalCase(input=item["input"], expected=item.get("expected"),
                          metadata=item.get("metadata", {}), tags=item.get("tags", [])) for item in raw]
        return cls(name=name, cases=cases)
    @classmethod
    def from_jsonl(cls, path, name=None):
        path = Path(path); name = name or path.stem; cases = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                item = json.loads(line)
                cases.append(EvalCase(input=item["input"], expected=item.get("expected"),
                                      metadata=item.get("metadata", {}), tags=item.get("tags", [])))
        return cls(name=name, cases=cases)
    def to_json(self, path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        data = [{"input": c.input, **({"expected": c.expected} if c.expected else {}),
                 **({"metadata": c.metadata} if c.metadata else {}),
                 **({"tags": c.tags} if c.tags else {})} for c in self.cases]
        with open(path, "w") as f: json.dump(data, f, indent=2)
    def stats(self):
        tag_counts = {}
        for c in self.cases:
            for t in c.tags: tag_counts[t] = tag_counts.get(t, 0) + 1
        return {"name": self.name, "total_cases": len(self.cases),
                "with_expected": sum(1 for c in self.cases if c.expected is not None),
                "without_expected": sum(1 for c in self.cases if c.expected is None), "tags": tag_counts}

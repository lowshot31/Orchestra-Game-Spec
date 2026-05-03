"""Knowledge base for learned rules — global and project-scoped.

Rules are persisted as JSON files under a configurable root directory:

    knowledge/
    ├── global_rules.json         # all projects
    └── projects/
        └── <project-slug>.json   # project-specific rules
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class LearnedRule:
    id: str
    content: str
    scope: str  # "global" or "project:<name>"
    created_by: str = ""
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class KnowledgeStore:
    rules: list[LearnedRule] = field(default_factory=list)

    # -- persistence --

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self.rules]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "KnowledgeStore":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            rules = [LearnedRule(**item) for item in raw]
            return cls(rules=rules)
        except (json.JSONDecodeError, TypeError, KeyError):
            return cls()

    # -- mutations --

    def add_rule(self, content: str, scope: str = "global", created_by: str = "") -> LearnedRule:
        rule_id = f"rule_{int(time.time() * 1000) % 1_000_000:06d}"
        rule = LearnedRule(id=rule_id, content=content, scope=scope, created_by=created_by)
        self.rules.append(rule)
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) < before

    # -- queries --

    def format_for_prompt(self) -> str:
        if not self.rules:
            return ""
        lines = ["Learned rules (MUST follow these in all outputs):"]
        for rule in self.rules:
            scope_tag = "[Global]" if rule.scope == "global" else f"[{rule.scope}]"
            lines.append(f"- {scope_tag} {rule.content}")
        return "\n".join(lines)

    def list_rules(self) -> str:
        if not self.rules:
            return "등록된 규칙이 없습니다."
        lines = ["# Learned Rules\n"]
        for rule in self.rules:
            scope_tag = "🌐 Global" if rule.scope == "global" else f"📁 {rule.scope}"
            lines.append(f"- `{rule.id}` ({scope_tag}): {rule.content}")
        return "\n".join(lines)


# -- file path helpers --

def _global_rules_path(root: Path) -> Path:
    return root / "knowledge" / "global_rules.json"


def _project_rules_path(root: Path, project_name: str) -> Path:
    slug = project_name.strip().lower().replace(" ", "-")
    return root / "knowledge" / "projects" / f"{slug}.json"


def load_all_rules(root: Path, project_name: str = "") -> KnowledgeStore:
    """Load global rules + project rules merged into one store."""
    global_store = KnowledgeStore.load(_global_rules_path(root))
    if not project_name:
        return global_store
    project_store = KnowledgeStore.load(_project_rules_path(root, project_name))
    merged = KnowledgeStore(rules=global_store.rules + project_store.rules)
    return merged


def save_rule(root: Path, content: str, scope: str = "global",
              project_name: str = "", created_by: str = "") -> LearnedRule:
    """Add a rule and persist it."""
    if scope == "global" or not project_name:
        path = _global_rules_path(root)
        store = KnowledgeStore.load(path)
        rule = store.add_rule(content, scope="global", created_by=created_by)
        store.save(path)
    else:
        path = _project_rules_path(root, project_name)
        store = KnowledgeStore.load(path)
        rule = store.add_rule(content, scope=f"project:{project_name}", created_by=created_by)
        store.save(path)
    return rule


def delete_rule(root: Path, rule_id: str, project_name: str = "") -> bool:
    """Try to delete a rule from global or project store."""
    global_path = _global_rules_path(root)
    global_store = KnowledgeStore.load(global_path)
    if global_store.remove_rule(rule_id):
        global_store.save(global_path)
        return True
    if project_name:
        project_path = _project_rules_path(root, project_name)
        project_store = KnowledgeStore.load(project_path)
        if project_store.remove_rule(rule_id):
            project_store.save(project_path)
            return True
    return False

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import yaml

from cldc.ingest.source_loader import SourceBundle

ALLOWED_RULE_KINDS = {
    "require_read",
    "deny_write",
    "require_command",
    "couple_change",
    "require_claim",
}
ALLOWED_MODES = {"observe", "warn", "block", "fix"}
REQUIRED_FIELDS_BY_KIND = {
    "deny_write": ("paths",),
    "require_read": ("paths", "before_paths"),
    "require_command": ("commands", "when_paths"),
    "couple_change": ("paths", "when_paths"),
    "require_claim": ("claims", "when_paths"),
}


@dataclass(frozen=True)
class RuleDefinition:
    """Normalized rule definition with source provenance."""

    rule_id: str
    kind: str
    message: str
    mode: str | None = None
    paths: list[str] | None = None
    before_paths: list[str] | None = None
    when_paths: list[str] | None = None
    commands: list[str] | None = None
    claims: list[str] | None = None
    source_path: str | None = None
    source_block_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {"id": payload.pop("rule_id"), **payload}


@dataclass(frozen=True)
class ParsedPolicy:
    """Fully parsed policy ready for lockfile serialization."""

    default_mode: str
    rules: list[RuleDefinition]

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_mode": self.default_mode,
            "rules": [rule.to_dict() for rule in self.rules],
        }


def _optional_str_list(item: dict[str, Any], key: str) -> list[str] | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(f"rule field '{key}' must be a list of non-empty strings")
    return value


def _load_yaml_document(raw: str, context: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid yaml in {context}: {exc}") from exc
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise ValueError(f"expected a YAML mapping in {context}")
    return document


def _validate_rule_item(item: dict[str, Any]) -> None:
    if not isinstance(item, dict):
        raise ValueError("each rule must be an object")
    if not isinstance(item.get("id"), str) or not item["id"].strip():
        raise ValueError("rule id is required")
    if not isinstance(item.get("kind"), str) or not item["kind"].strip():
        raise ValueError(f"rule '{item.get('id', '<unknown>')}' kind is required")
    if item["kind"] not in ALLOWED_RULE_KINDS:
        raise ValueError(f"unknown rule kind: {item['kind']}")
    if item.get("mode") is not None and item["mode"] not in ALLOWED_MODES:
        raise ValueError(f"invalid rule mode: {item['mode']}")
    if not isinstance(item.get("message"), str) or not item["message"].strip():
        raise ValueError(f"rule '{item['id']}' message is required")

    fields = {
        "paths": _optional_str_list(item, "paths"),
        "before_paths": _optional_str_list(item, "before_paths"),
        "when_paths": _optional_str_list(item, "when_paths"),
        "commands": _optional_str_list(item, "commands"),
        "claims": _optional_str_list(item, "claims"),
    }
    for field_name in REQUIRED_FIELDS_BY_KIND[item["kind"]]:
        if not fields[field_name]:
            raise ValueError(f"rule '{item['id']}' requires field '{field_name}'")


def _coerce_rules(source, raw: str) -> list[RuleDefinition]:
    document = _load_yaml_document(raw, source.path)
    rule_items = document.get("rules", [])
    if not isinstance(rule_items, list):
        raise ValueError(f"rules must be a list in {source.path}")
    rules = []
    for item in rule_items:
        _validate_rule_item(item)
        rules.append(
            RuleDefinition(
                rule_id=item["id"],
                kind=item["kind"],
                message=item["message"],
                mode=item.get("mode"),
                paths=item.get("paths"),
                before_paths=item.get("before_paths"),
                when_paths=item.get("when_paths"),
                commands=item.get("commands"),
                claims=item.get("claims"),
                source_path=source.path,
                source_block_id=source.block_id,
            )
        )
    return rules


def parse_rule_documents(bundle: SourceBundle) -> ParsedPolicy:
    """Validate and merge rule documents from a loaded source bundle."""

    default_mode = "warn"
    rules: list[RuleDefinition] = []
    seen_ids: set[str] = set()

    for source in bundle.sources:
        if source.kind == "claude_md":
            continue
        document = _load_yaml_document(source.content, source.path)
        if source.kind == "compiler_config" and document.get("default_mode") is not None:
            if document["default_mode"] not in ALLOWED_MODES:
                raise ValueError(f"invalid default_mode: {document['default_mode']}")
            default_mode = document["default_mode"]
        for rule in _coerce_rules(source, source.content):
            if rule.rule_id in seen_ids:
                raise ValueError(f"duplicate rule id: {rule.rule_id}")
            seen_ids.add(rule.rule_id)
            rules.append(rule)

    return ParsedPolicy(default_mode=default_mode, rules=rules)

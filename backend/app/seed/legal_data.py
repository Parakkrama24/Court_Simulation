"""Legal rules seed data loader

Loads principles, criminal laws, and evidence rules from JSON files.
"""

import json
from pathlib import Path
from typing import List
from app.domain import LegalRule, LegalCategory


def load_legal_rules_from_file(filename: str) -> List[LegalRule]:
    """Load legal rules from a JSON file"""
    rules_dir = Path(__file__).parent.parent / "rules" / "data"
    file_path = rules_dir / filename

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [LegalRule(**rule) for rule in data]


def get_all_legal_rules() -> List[LegalRule]:
    """Get all legal rules from all categories"""
    all_rules = []
    all_rules.extend(load_legal_rules_from_file("principles.json"))
    all_rules.extend(load_legal_rules_from_file("criminal_laws.json"))
    all_rules.extend(load_legal_rules_from_file("evidence_rules.json"))
    return all_rules


def get_legal_rules_by_category(category: LegalCategory) -> List[LegalRule]:
    """Get legal rules filtered by category"""
    all_rules = get_all_legal_rules()
    return [rule for rule in all_rules if rule.category == category]


def get_legal_rule_by_id(rule_id: str) -> LegalRule | None:
    """Get a specific legal rule by ID"""
    all_rules = get_all_legal_rules()
    for rule in all_rules:
        if rule.rule_id == rule_id:
            return rule
    return None

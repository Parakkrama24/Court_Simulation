"""Legal rule registry

Provides indexed, read-only access to the structured legal rules of a
jurisdiction. The registry is the single authority on what rules exist -
agents may reference rules, but may never add to this set.
"""

from typing import Dict, Iterator, List, Optional

from app.domain import Condition, LegalCategory, LegalRule
from app.seed.legal_data import get_all_legal_rules


class LegalRuleRegistry:
    """Indexed collection of legal rules"""

    def __init__(self, rules: Optional[List[LegalRule]] = None) -> None:
        loaded = list(rules) if rules is not None else get_all_legal_rules()

        duplicates = self._find_duplicate_ids(loaded)
        if duplicates:
            raise ValueError(f"Duplicate legal rule IDs: {', '.join(sorted(duplicates))}")

        self._rules: Dict[str, LegalRule] = {rule.rule_id: rule for rule in loaded}

    @staticmethod
    def _find_duplicate_ids(rules: List[LegalRule]) -> set[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for rule in rules:
            if rule.rule_id in seen:
                duplicates.add(rule.rule_id)
            seen.add(rule.rule_id)
        return duplicates

    def __len__(self) -> int:
        return len(self._rules)

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self._rules

    def __iter__(self) -> Iterator[LegalRule]:
        return iter(self._rules.values())

    @property
    def rule_ids(self) -> List[str]:
        """All known rule IDs"""
        return list(self._rules.keys())

    def get(self, rule_id: str) -> Optional[LegalRule]:
        """Return a rule, or None if it does not exist"""
        return self._rules.get(rule_id)

    def require(self, rule_id: str) -> LegalRule:
        """Return a rule, raising if it does not exist"""
        rule = self._rules.get(rule_id)
        if rule is None:
            raise KeyError(f"Unknown legal rule: {rule_id}")
        return rule

    def get_condition(self, rule_id: str, condition_id: str) -> Optional[Condition]:
        """Return a single condition of a rule, or None if either is unknown"""
        rule = self._rules.get(rule_id)
        if rule is None:
            return None
        for condition in rule.conditions:
            if condition.id == condition_id:
                return condition
        return None

    def by_category(self, category: LegalCategory) -> List[LegalRule]:
        """All rules in a category"""
        return [rule for rule in self._rules.values() if rule.category == category]

    def offenses(self) -> List[LegalRule]:
        """All offense rules"""
        return self.by_category(LegalCategory.OFFENSE)

    def defenses(self) -> List[LegalRule]:
        """All defense rules"""
        return self.by_category(LegalCategory.DEFENSE)

    def principles(self) -> List[LegalRule]:
        """All fundamental principles"""
        return self.by_category(LegalCategory.PRINCIPLE)

    def evidence_rules(self) -> List[LegalRule]:
        """All evidence rules"""
        return self.by_category(LegalCategory.EVIDENCE_RULE)


def get_default_registry() -> LegalRuleRegistry:
    """Registry over the seeded Republic of Arandia rules"""
    return LegalRuleRegistry()

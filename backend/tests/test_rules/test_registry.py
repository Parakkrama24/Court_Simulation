"""Tests for the legal rule registry"""

import pytest

from app.domain import LegalCategory, LegalRule
from app.rules import LegalRuleRegistry, get_default_registry


class TestRegistryLookup:
    """Lookups over the synthetic rule set"""

    def test_len_and_contains(self, registry: LegalRuleRegistry):
        assert len(registry) == 7
        assert "RULE_A" in registry
        assert "RULE_NOPE" not in registry

    def test_get_returns_rule(self, registry: LegalRuleRegistry):
        rule = registry.get("RULE_A")
        assert rule is not None
        assert rule.name == "Two Element Offense"

    def test_get_unknown_returns_none(self, registry: LegalRuleRegistry):
        assert registry.get("RULE_NOPE") is None

    def test_require_raises_on_unknown(self, registry: LegalRuleRegistry):
        with pytest.raises(KeyError):
            registry.require("RULE_NOPE")

    def test_get_condition(self, registry: LegalRuleRegistry):
        condition = registry.get_condition("RULE_A", "C2")
        assert condition is not None
        assert condition.description == "Second element"

    def test_get_condition_unknown(self, registry: LegalRuleRegistry):
        assert registry.get_condition("RULE_A", "C9") is None
        assert registry.get_condition("RULE_NOPE", "C1") is None

    def test_iteration_yields_rules(self, registry: LegalRuleRegistry):
        assert {rule.rule_id for rule in registry} == set(registry.rule_ids)

    def test_by_category(self, registry: LegalRuleRegistry):
        assert [rule.rule_id for rule in registry.principles()] == ["RULE_C"]
        assert "RULE_A" in [rule.rule_id for rule in registry.by_category(LegalCategory.OFFENSE)]

    def test_duplicate_rule_ids_rejected(self, rules: list[LegalRule]):
        with pytest.raises(ValueError, match="Duplicate legal rule IDs"):
            LegalRuleRegistry(rules + [rules[0]])


class TestDefaultRegistry:
    """The registry over seeded Republic of Arandia rules"""

    def test_loads_all_seeded_rules(self):
        registry = get_default_registry()
        assert len(registry) == 17

    def test_categories_are_populated(self):
        registry = get_default_registry()
        assert len(registry.principles()) == 5
        assert len(registry.offenses()) == 5
        assert len(registry.defenses()) == 2
        assert len(registry.evidence_rules()) == 5

    def test_known_rules_present(self):
        registry = get_default_registry()
        for rule_id in ["P001", "LAW_101", "LAW_201", "E005"]:
            assert rule_id in registry

    def test_aggravated_assault_depends_on_assault(self):
        registry = get_default_registry()
        condition = registry.get_condition("LAW_102", "C1")
        assert condition is not None
        assert condition.depends_on_rule == "LAW_101"

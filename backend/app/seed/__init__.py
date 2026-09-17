"""Seed data for the Court Simulation System"""

from .cases import get_all_cases, get_case_by_id
from .legal_data import get_all_legal_rules, get_legal_rules_by_category

__all__ = [
    "get_all_cases",
    "get_case_by_id",
    "get_all_legal_rules",
    "get_legal_rules_by_category",
]

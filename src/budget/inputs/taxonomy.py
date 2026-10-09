# Copyright 2026 Therkel
"""`taxonomy.toml`: the household's category groups and categories.

Two levels: a group carries the direction every one of its categories shares,
so a group rollup never mixes income and expense. Both are keyed by durable,
household-assigned IDs (`classification.md`, *Taxonomy*).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from budget.inputs.document import read_document
from budget.profiles import TAXONOMY_FILE_NAME, Profile

type CategoryDirection = Literal["income", "expense"]


@dataclass(frozen=True)
class CategoryGroup:
    """One `[group.<id>]` table."""

    group_id: str
    name: str
    direction: CategoryDirection


@dataclass(frozen=True)
class Category:
    """One `[category.<id>]` table; its direction is its group's."""

    category_id: str
    name: str
    group_id: str


@dataclass(frozen=True)
class Taxonomy:
    """Every group and category, each keyed by its ID in file order."""

    groups: Mapping[str, CategoryGroup]
    categories: Mapping[str, Category]


def load_taxonomy(profile: Profile) -> Taxonomy:
    """Load the profile's `taxonomy.toml`."""
    path = profile.input_file(TAXONOMY_FILE_NAME)
    document = read_document(path, TAXONOMY_FILE_NAME)
    groups = {
        group_id: CategoryGroup(group_id, entry["name"], entry["direction"])
        for group_id, entry in document.get("group", {}).items()
    }
    categories = {
        category_id: Category(category_id, entry["name"], entry["group"])
        for category_id, entry in document.get("category", {}).items()
    }
    return Taxonomy(MappingProxyType(groups), MappingProxyType(categories))

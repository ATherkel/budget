# Copyright 2026 Therkel
"""`taxonomy.toml`: the household's category groups and categories.

Two levels: a group carries the direction every one of its categories shares,
so a group rollup never mixes income and expense. Both are keyed by durable,
household-assigned IDs (`classification.md`, *Taxonomy*).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from budget.inputs.document import (
    ConfigurationError,
    file_problem,
    keyed_tables,
    read_document,
    unknown_top_level_keys,
)
from budget.inputs.fields import TEXT, FieldRule, entry_problems, is_text, one_of
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


# Every key a group may carry. Direction lives here only, so every category in
# a group shares it.
_GROUP_FIELDS: Mapping[str, FieldRule] = MappingProxyType(
    {"name": TEXT, "direction": one_of("income", "expense")}
)

# Every key a category may carry.
_CATEGORY_FIELDS: Mapping[str, FieldRule] = MappingProxyType(
    {"name": TEXT, "group": TEXT}
)


def _entry_problem(kind: str, entry_id: str, text: str) -> str:
    """Name the file and the entry a problem is in."""
    return file_problem(TAXONOMY_FILE_NAME, f'{kind} "{entry_id}": {text}')


def _group_problems(groups: Mapping[str, object]) -> list[str]:
    """List every group's problems in file order."""
    return [
        _entry_problem("group", group_id, problem)
        for group_id, entry in groups.items()
        for problem in entry_problems(group_id, entry, _GROUP_FIELDS, "food")
    ]


def _undeclared_group(entry: object, groups: Mapping[str, object]) -> list[str]:
    """Name a category's group that no `[group.<id>]` table declares."""
    group = entry.get("group") if isinstance(entry, dict) else None
    if not is_text(group) or group in groups:
        return []
    return [f'group "{group}" is not declared']


def _category_problems(
    categories: Mapping[str, object], groups: Mapping[str, object]
) -> list[str]:
    """List every category's problems in file order."""
    problems = []
    for category_id, entry in categories.items():
        found = entry_problems(category_id, entry, _CATEGORY_FIELDS, "groceries")
        found.extend(_undeclared_group(entry, groups))
        problems.extend(_entry_problem("category", category_id, p) for p in found)
    return problems


def load_taxonomy(profile: Profile) -> Taxonomy:
    """Load and validate the profile's `taxonomy.toml`."""
    path = profile.input_file(TAXONOMY_FILE_NAME)
    document = read_document(path, TAXONOMY_FILE_NAME)
    problems = unknown_top_level_keys(
        document, TAXONOMY_FILE_NAME, ("group", "category")
    )
    groups, shape_problems = keyed_tables(document, TAXONOMY_FILE_NAME, "group")
    problems.extend(shape_problems)
    categories, shape_problems = keyed_tables(document, TAXONOMY_FILE_NAME, "category")
    problems.extend(shape_problems)
    problems.extend(_group_problems(groups))
    problems.extend(_category_problems(categories, groups))
    if problems:
        raise ConfigurationError(tuple(problems))
    return _taxonomy(groups, categories)


def _taxonomy(groups: Mapping[str, Any], categories: Mapping[str, Any]) -> Taxonomy:
    """Build the taxonomy from entries that have passed every rule."""
    return Taxonomy(
        groups=MappingProxyType(
            {
                group_id: CategoryGroup(group_id, entry["name"], entry["direction"])
                for group_id, entry in groups.items()
            }
        ),
        categories=MappingProxyType(
            {
                category_id: Category(category_id, entry["name"], entry["group"])
                for category_id, entry in categories.items()
            }
        ),
    )

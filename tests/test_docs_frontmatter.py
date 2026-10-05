# Copyright 2026 Therkel
"""Open Knowledge Format headers on the docs (ADR-019).

Every Markdown file under `docs/` opens with a three-line header whose only key,
`type`, ADR-019 derives from the file's folder.
"""

from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs"
DOCUMENTS = sorted(DOCS.rglob("*.md"))


def _expected_type(path: Path) -> str:
    """The `type` ADR-019 gives the document at `path`."""
    if path.parent == DOCS:
        if path.name == "CONTEXT.md":
            return "glossary"
        return "overview"
    return path.parent.name


def test_the_docs_folder_is_found() -> None:
    # An empty glob would make every parametrized case below vanish silently.
    assert DOCUMENTS


def test_no_document_takes_a_name_okf_reserves() -> None:
    # OKF reserves these names for index and log files, which ADR-019 rejects.
    reserved = [path for path in DOCUMENTS if path.name in {"index.md", "log.md"}]

    assert reserved == []


@pytest.mark.parametrize(
    "path", DOCUMENTS, ids=lambda path: path.relative_to(DOCS).as_posix()
)
def test_a_document_opens_with_a_header_naming_its_type(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()

    assert lines[:3] == ["---", f"type: {_expected_type(path)}", "---"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])

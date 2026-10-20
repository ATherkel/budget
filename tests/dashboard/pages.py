# Copyright 2026 Therkel
"""Read a dashboard page as its reader and its forms see it."""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import override


@dataclass(frozen=True)
class Field:
    """One form control: its name, type, value, and whether it is checked."""

    name: str
    type: str
    value: str
    checked: bool


@dataclass
class Option:
    """One option of a select: its value, its text, and whether it is selected."""

    select: str
    value: str
    selected: bool
    text: str = ""


@dataclass
class Page(HTMLParser):
    """The visible text of a page and the form controls on it."""

    text: list[str] = field(default_factory=list)
    fields: list[Field] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)
    elements: dict[str, dict[str, str]] = field(default_factory=dict)
    element_text: dict[str, str] = field(default_factory=dict)
    _hidden_depth: int = 0
    _open: list[tuple[str, str]] = field(default_factory=list)
    _select: str | None = None
    _option: Option | None = None

    def __post_init__(self) -> None:
        super().__init__()

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.elements[element_id] = {key: value or "" for key, value in attrs}
            self.element_text[element_id] = ""
            if tag != "input":
                self._open.append((tag, element_id))
        if tag in {"script", "style", "title"}:
            self._hidden_depth += 1
        elif tag == "input":
            self.fields.append(
                Field(
                    name=values.get("name") or "",
                    type=values.get("type") or "text",
                    value=values.get("value") or "",
                    checked="checked" in values,
                )
            )
        elif tag == "select":
            self._select = values.get("name") or ""
        elif tag == "option" and self._select is not None:
            self._option = Option(
                select=self._select,
                value=values.get("value") or "",
                selected="selected" in values,
            )
            self.options.append(self._option)

    @override
    def handle_endtag(self, tag: str) -> None:
        if self._open and self._open[-1][0] == tag:
            self._open.pop()
        if tag in {"script", "style", "title"}:
            self._hidden_depth -= 1
        elif tag == "select":
            self._select = None
        elif tag == "option":
            self._option = None

    @override
    def handle_data(self, data: str) -> None:
        words = " ".join(data.split())
        if self._hidden_depth or not words:
            return
        self.text.append(words)
        for _, element_id in self._open:
            self.element_text[element_id] = (
                f"{self.element_text[element_id]} {words}".strip()
            )
        if self._option is not None:
            self._option.text = f"{self._option.text} {words}".strip()

    def visible(self) -> str:
        """Return the page's visible text, one space between pieces."""
        return " ".join(self.text)

    def checked(self, name: str) -> set[str]:
        """Return the values of the checked controls called `name`."""
        return {f.value for f in self.fields if f.name == name and f.checked}

    def hidden(self, name: str) -> str | None:
        """Return the value of the hidden field called `name`, if there is one."""
        return next(
            (f.value for f in self.fields if f.name == name and f.type == "hidden"),
            None,
        )

    def attributes(self, element_id: str) -> dict[str, str]:
        """Return the attributes of the element with `element_id`, or none."""
        return self.elements.get(element_id, {})

    def text_of(self, element_id: str) -> str | None:
        """Return the visible text inside the element with `element_id`, or None."""
        return self.element_text.get(element_id)

    def offered(self, name: str) -> list[str]:
        """Return the values of every option of select `name`, in order."""
        return [o.value for o in self.options if o.select == name]

    def selected(self, name: str) -> list[tuple[str, str]]:
        """Return the value and text of each selected option of select `name`."""
        return [
            (o.value, o.text) for o in self.options if o.select == name and o.selected
        ]


def read(html: str) -> Page:
    """Parse a page."""
    page = Page()
    page.feed(html)
    page.close()
    return page

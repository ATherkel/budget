# Copyright 2026 Therkel
"""Read a dashboard page as its reader and its forms see it."""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import override

# Elements that never have an end tag, so they hold no text.
_VOID = frozenset({"area", "br", "col", "hr", "img", "input", "link", "meta", "wbr"})
_DISCLOSURE_TAGS = frozenset({"details", "summary", "tr", "td", "th"})


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
class Disclosure:
    """One native disclosure's summary and table cells."""

    open: bool
    summary: str = ""
    rows: list[tuple[str, ...]] = field(default_factory=list)


@dataclass
class Page(HTMLParser):
    """The visible text of a page and the form controls on it."""

    text: list[str] = field(default_factory=list)
    fields: list[Field] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)
    elements: dict[str, dict[str, str]] = field(default_factory=dict)
    element_text: dict[str, str] = field(default_factory=dict)
    disclosures: list[Disclosure] = field(default_factory=list)
    _hidden_depth: int = 0
    # Every open element, innermost last, with its id when it has one.
    _open: list[tuple[str, str | None]] = field(default_factory=list)
    _select: str | None = None
    _option: Option | None = None
    _disclosure_stack: list[Disclosure] = field(default_factory=list)
    _summary_parts: list[str] | None = None
    _row: list[str] | None = None
    _cell_parts: list[str] | None = None

    def __post_init__(self) -> None:
        super().__init__()

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.elements[element_id] = {key: value or "" for key, value in attrs}
            self.element_text[element_id] = ""
        if tag not in _VOID:
            self._open.append((tag, element_id))
        if tag in {"script", "style", "title"}:
            self._hidden_depth += 1
        elif tag in _DISCLOSURE_TAGS:
            self._start_disclosure_element(tag, is_open="open" in values)
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

    def _start_disclosure_element(
        self,
        tag: str,
        *,
        is_open: bool,
    ) -> None:
        match tag:
            case "details":
                disclosure = Disclosure(open=is_open)
                self.disclosures.append(disclosure)
                self._disclosure_stack.append(disclosure)
            case "summary" if self._disclosure_stack:
                self._summary_parts = []
            case "tr" if self._disclosure_stack:
                self._row = []
            case "td" | "th" if self._row is not None:
                self._cell_parts = []

    @override
    def handle_endtag(self, tag: str) -> None:
        # Close the innermost open element of this name, and any left open in it.
        for depth in range(len(self._open) - 1, -1, -1):
            if self._open[depth][0] == tag:
                del self._open[depth:]
                break
        if tag in _DISCLOSURE_TAGS:
            self._end_disclosure_element(tag)
        if tag in {"script", "style", "title"}:
            self._hidden_depth -= 1
        elif tag == "select":
            self._select = None
        elif tag == "option":
            self._option = None

    def _end_disclosure_element(self, tag: str) -> None:
        match tag:
            case "summary" if self._summary_parts is not None:
                self._disclosure_stack[-1].summary = " ".join(self._summary_parts)
                self._summary_parts = None
            case "td" | "th" if self._cell_parts is not None:
                if self._row is not None:
                    self._row.append(" ".join(self._cell_parts))
                self._cell_parts = None
            case "tr" if self._row is not None:
                self._disclosure_stack[-1].rows.append(tuple(self._row))
                self._row = None
            case "details" if self._disclosure_stack:
                self._disclosure_stack.pop()

    @override
    def handle_data(self, data: str) -> None:
        words = " ".join(data.split())
        if self._hidden_depth or not words:
            return
        self.text.append(words)
        for _, element_id in self._open:
            if element_id is not None:
                self.element_text[element_id] = (
                    f"{self.element_text[element_id]} {words}".strip()
                )
        if self._summary_parts is not None:
            self._summary_parts.append(words)
        if self._cell_parts is not None:
            self._cell_parts.append(words)
        if self._option is not None:
            self._option.text = f"{self._option.text} {words}".strip()

    def visible(self) -> str:
        """Return the page's visible text, one space between pieces."""
        return " ".join(self.text)

    def choices(self, name: str) -> set[str]:
        """Return the values of every checkbox called `name`, ticked or not."""
        return {f.value for f in self.fields if f.name == name and f.type == "checkbox"}

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

# Copyright 2026 Therkel
"""The documented Silver walkthrough transcript is what the walkthrough prints.

The transcript in `docs/developers/silver-walkthrough.md` claims to be the
script's actual output, so the first `text` block under its
`## Silver walkthrough` heading must equal what `walkthrough` writes to stdout,
line for line.
"""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from examples.silver_walkthrough import walkthrough

DOCUMENT = Path(__file__).resolve().parents[1] / "docs/developers/silver-walkthrough.md"
HEADING = "\n## Silver walkthrough\n"
TEXT_BLOCK = "```text\n"


def _documented_transcript() -> str:
    """Return the first `text` block under the document's walkthrough heading."""
    document = DOCUMENT.read_text(encoding="utf-8")
    assert HEADING in document, (
        "silver-walkthrough.md lost its '## Silver walkthrough' heading"
    )
    section = document.split(HEADING, 1)[1].split("\n## ", 1)[0]
    assert TEXT_BLOCK in section, (
        "The '## Silver walkthrough' section lost its ```text transcript block"
    )
    return section.split(TEXT_BLOCK, 1)[1].split("```", 1)[0]


class SilverWalkthroughDocumentTests(unittest.TestCase):
    def test_the_documented_transcript_is_what_the_walkthrough_prints(self) -> None:
        with TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                walkthrough(Path(directory))

        assert output.getvalue() == _documented_transcript()


if __name__ == "__main__":
    unittest.main()

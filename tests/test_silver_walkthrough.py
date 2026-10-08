# Copyright 2026 Therkel
"""The README's Silver walkthrough transcript is what the walkthrough prints.

The transcript in `README.md` claims to be the script's actual output, so the
first `text` block under its `## Silver walkthrough` heading must equal what
`walkthrough` writes to stdout, line for line.
"""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from examples.silver_walkthrough import walkthrough

README = Path(__file__).resolve().parents[1] / "README.md"


def _readme_transcript() -> str:
    """Return the first `text` block under the README's walkthrough heading."""
    section = README.read_text(encoding="utf-8").split("\n## Silver walkthrough\n")[1]
    return section.split("```text\n", 1)[1].split("```", 1)[0]


class SilverWalkthroughReadmeTests(unittest.TestCase):
    def test_the_readme_transcript_is_what_the_walkthrough_prints(self) -> None:
        with TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                walkthrough(Path(directory))

        assert output.getvalue() == _readme_transcript()


if __name__ == "__main__":
    unittest.main()

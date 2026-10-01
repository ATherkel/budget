# Copyright 2026 Therkel
"""Profile files: the versioned TOML a command loads before it does anything.

A file the command cannot use is a configuration error, exit 3, reported with
the file's name and the problem, and nothing is created. The files here are
synthetic and written into each test's temporary folder.
"""

import io
import unittest
from contextlib import chdir, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.cli import main

EXIT_REFUSED_INPUT = 3

VALID_HEADER = 'format = 1\nprofile = "development"\n'


def _paths(stores: str) -> str:
    """A `[paths]` table naming only the stores folder."""
    return f"\n[paths]\nstores = '{stores}'\n"


class ProfileFileTests(unittest.TestCase):
    def _refusals(self, stores: Path) -> dict[str, str]:
        """Profile file contents that must each be refused, by what is wrong."""
        absolute = _paths(str(stores))
        return {
            "not TOML": "format = = 1\n",
            "an unsupported format version": (
                'format = 2\nprofile = "development"\n' + absolute
            ),
            "no format version": 'profile = "development"\n' + absolute,
            "a test profile in a file": 'format = 1\nprofile = "test"\n' + absolute,
            "an unknown profile name": 'format = 1\nprofile = "staging"\n' + absolute,
            "no profile name": "format = 1\n" + absolute,
            "an unknown top-level key": VALID_HEADER + "colour = 1\n" + absolute,
            "an unknown paths key": VALID_HEADER + absolute + "archive = 'x'\n",
            "no paths table": VALID_HEADER,
            "no stores path": VALID_HEADER + "\n[paths]\ninbox = 'x'\n",
            "a relative stores path": VALID_HEADER + _paths("stores"),
            "a stores path that is not text": (
                VALID_HEADER + "\n[paths]\nstores = 1\n"
            ),
        }

    def test_a_profile_file_the_command_cannot_use_is_refused(self) -> None:
        with TemporaryDirectory() as directory, chdir(directory):
            # Inside the temporary folder, a relative stores path that slipped
            # through would land in `stores` below, not in the checkout.
            folder = Path(directory)
            stores = folder / "stores"
            for problem, text in self._refusals(stores).items():
                with self.subTest(problem):
                    profile_file = folder / "development.toml"
                    profile_file.write_text(text, encoding="utf-8")
                    stderr = io.StringIO()

                    with redirect_stderr(stderr):
                        status = main(
                            ["--profile", str(profile_file), "migrate"], environ={}
                        )

                    assert status == EXIT_REFUSED_INPUT
                    assert "development.toml" in stderr.getvalue()
                    assert not stores.exists()

    def test_a_missing_profile_file_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = Path(directory) / "development.toml"
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                status = main(["--profile", str(profile_file), "migrate"], environ={})

            assert status == EXIT_REFUSED_INPUT
            assert "development.toml" in stderr.getvalue()

    def test_an_unsupported_format_version_is_named(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = folder / "development.toml"
            profile_file.write_text(
                'format = 2\nprofile = "development"\n' + _paths(str(folder)),
                encoding="utf-8",
            )
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                main(["--profile", str(profile_file), "migrate"], environ={})

            assert "format 2" in stderr.getvalue()


if __name__ == "__main__":
    unittest.main()

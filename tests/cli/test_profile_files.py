# Copyright 2026 Therkel
"""Profile files: the versioned TOML a command loads before it does anything.

A file the command cannot use is a configuration error, exit 3, reported with
the file's name and the problem, and nothing is created. The files here are
synthetic and written into each test's temporary folder.
"""

import io
import shutil
import unittest
from contextlib import chdir, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.bronze import BronzeStore
from budget.cli import main
from budget.profiles import RetentionPolicy, load_profile_file
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3
EXIT_REFUSED_ENVIRONMENT = 4

VALID_HEADER = 'format = 1\nprofile = "development"\n'
PRODUCTION_HEADER = 'format = 1\nprofile = "production"\n'


def _inbox_and_exports(folder: Path) -> str:
    """The `[paths]` lines naming the inbox and export archive inside `folder`.

    They are absolute even when a case's stores path is not, so each refusal
    case below is refused for its own problem only.
    """
    folder = folder.absolute()
    return f"inbox = '{folder / 'inbox'}'\nexports = '{folder / 'exports'}'\n"


def _paths(stores: str, inputs: Path) -> str:
    """A `[paths]` table naming the stores and inputs folders, then the rest."""
    return f"\n[paths]\nstores = '{stores}'\ninputs = '{inputs}'\n" + (
        _inbox_and_exports(Path(stores).parent)
    )


def _production(stores: Path, backups: str, retention: str = "") -> str:
    """A production profile file naming `backups`, then a `[backups]` table."""
    paths = _paths(str(stores), stores.parent / "inputs")
    return PRODUCTION_HEADER + paths + f"backups = '{backups}'\n" + retention


def _assert_refused(profile_file: Path, text: str, stores: Path) -> None:
    """Write the file, run `migrate`, and expect exit 3 with nothing created."""
    profile_file.write_text(text, encoding="utf-8")
    stderr = io.StringIO()

    with redirect_stderr(stderr):
        status = main(["--profile", str(profile_file), "migrate"], environ={})

    assert status == EXIT_REFUSED_INPUT
    assert profile_file.name in stderr.getvalue()
    assert not stores.exists()


class ProfileFileTests(unittest.TestCase):
    def _refusals(self, stores: Path) -> dict[str, str]:
        """Profile file contents that must each be refused, by what is wrong."""
        inputs = stores.parent / "inputs"
        absolute = _paths(str(stores), inputs)
        others = _inbox_and_exports(stores.parent)
        inbox = stores.parent.absolute() / "inbox"
        exports = stores.parent.absolute() / "exports"
        assert f"inbox = '{inbox}'" in absolute
        assert f"exports = '{exports}'" in absolute
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
            "a backups table in development": (
                VALID_HEADER + absolute + "\n[backups]\nkeep_all_days = 14\n"
            ),
            "a backups path in development": VALID_HEADER
            + absolute
            + "backups = 'x'\n",
            "upstream backups in production": (
                'format = 1\nprofile = "production"\n'
                + absolute
                + "upstream_backups = 'x'\n"
            ),
            "no paths table": VALID_HEADER,
            "no stores path": (
                VALID_HEADER + f"\n[paths]\ninputs = '{inputs}'\n" + others
            ),
            "a relative stores path": VALID_HEADER + _paths("stores", inputs),
            "a stores path that is not text": (
                VALID_HEADER + f"\n[paths]\nstores = 1\ninputs = '{inputs}'\n" + others
            ),
            "no inputs path": (
                VALID_HEADER + f"\n[paths]\nstores = '{stores}'\n" + others
            ),
            "a relative inputs path": VALID_HEADER + _paths(str(stores), Path("in")),
            "an inputs path that is not text": (
                VALID_HEADER + f"\n[paths]\nstores = '{stores}'\ninputs = 1\n" + others
            ),
            "no inbox path": VALID_HEADER + absolute.replace(f"inbox = '{inbox}'", ""),
            "a relative inbox path": (
                VALID_HEADER + absolute.replace(f"inbox = '{inbox}'", "inbox = 'in'")
            ),
            "no exports path": (
                VALID_HEADER + absolute.replace(f"exports = '{exports}'", "")
            ),
            "a relative exports path": VALID_HEADER
            + absolute.replace(f"exports = '{exports}'", "exports = 'ex'"),
            "an inbox that is the export archive": VALID_HEADER
            + absolute.replace(f"exports = '{exports}'", f"exports = '{inbox}'"),
            **self._backup_refusals(stores),
        }

    def _backup_refusals(self, stores: Path) -> dict[str, str]:
        """Production files whose backups path or retention must be refused."""
        folder = stores.parent.absolute()
        backups = str(folder / "backups")
        inputs = stores.parent / "inputs"
        return {
            "no backups path in production": PRODUCTION_HEADER
            + _paths(str(stores), inputs),
            "a relative backups path": _production(stores, "backups"),
            "a backups folder inside the inputs folder": _production(
                stores, str(folder / "inputs" / "backups")
            ),
            "an inputs folder inside the backups folder": PRODUCTION_HEADER
            + _paths(str(stores), Path(backups) / "inputs")
            + f"backups = '{backups}'\n",
            "a backups folder that is the inbox": _production(
                stores, str(folder / "inbox")
            ),
            "a backups folder inside the export archive": _production(
                stores, str(folder / "exports" / "backups")
            ),
            # The live stores are never cloud-synchronised (ADR-013); the
            # backups folder is.
            "a backups folder that is the stores folder": _production(
                stores, str(stores.absolute())
            ),
            "a stores folder inside the backups folder": PRODUCTION_HEADER
            + f"\n[paths]\nstores = '{Path(backups) / 'live'}'\n"
            + f"inputs = '{inputs.absolute()}'\n"
            + _inbox_and_exports(folder)
            + f"backups = '{backups}'\n",
            "a negative keep_all_days": _production(
                stores, backups, "\n[backups]\nkeep_all_days = -1\n"
            ),
            "a keep_daily_days that is true": _production(
                stores, backups, "\n[backups]\nkeep_daily_days = true\n"
            ),
            "a keep_daily_days that is a fraction": _production(
                stores, backups, "\n[backups]\nkeep_daily_days = 1.5\n"
            ),
            "a keep_monthly word other than forever": _production(
                stores, backups, '\n[backups]\nkeep_monthly = "always"\n'
            ),
            "a negative keep_monthly": _production(
                stores, backups, "\n[backups]\nkeep_monthly = -3\n"
            ),
            "an unknown backups key": _production(
                stores, backups, "\n[backups]\nkeep_weekly = 4\n"
            ),
            "a backups key that is not a table": PRODUCTION_HEADER
            + "backups = 1\n"
            + _paths(str(stores), inputs)
            + f"backups = '{backups}'\n",
        }

    def test_a_profile_file_the_command_cannot_use_is_refused(self) -> None:
        with TemporaryDirectory() as directory, chdir(directory):
            # Inside the temporary folder, a relative stores path that slipped
            # through would land in `stores` below, not in the checkout.
            folder = Path(directory)
            stores = folder / "stores"
            for problem, text in self._refusals(stores).items():
                with self.subTest(problem):
                    try:
                        _assert_refused(folder / "development.toml", text, stores)
                    finally:
                        # A case that wrongly migrates must not fail the next.
                        shutil.rmtree(stores, ignore_errors=True)

    def test_a_profile_file_names_the_inbox_and_export_archive(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            profile = load_profile_file(write_profile(folder))

            assert profile.inbox == (folder / "inbox").resolve()
            assert profile.exports == (folder / "exports").resolve()

    def test_a_production_profile_file_names_its_backups_and_their_retention(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = folder / "production.toml"
            retention = (
                "\n[backups]\nkeep_all_days = 7\nkeep_daily_days = 30\n"
                "keep_monthly = 24\n"
            )
            profile_file.write_text(
                _production(folder / "stores", str(folder / "backups"), retention),
                encoding="utf-8",
            )

            profile = load_profile_file(profile_file)

            assert profile.backups == (folder / "backups").resolve()
            assert profile.retention == RetentionPolicy(
                keep_all_days=7, keep_daily_days=30, keep_monthly=24
            )

    def test_backup_retention_keeps_conservative_defaults_and_forever(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = folder / "production.toml"
            backups = str(folder / "backups")
            cases = {
                "no [backups] table": ("", RetentionPolicy()),
                "monthly sets kept forever": (
                    '\n[backups]\nkeep_all_days = 3\nkeep_monthly = "forever"\n',
                    RetentionPolicy(keep_all_days=3),
                ),
            }
            for case, (retention, expected) in cases.items():
                with self.subTest(case):
                    profile_file.write_text(
                        _production(folder / "stores", backups, retention),
                        encoding="utf-8",
                    )

                    profile = load_profile_file(profile_file)

                    assert profile.retention == expected
            assert RetentionPolicy() == RetentionPolicy(
                keep_all_days=14, keep_daily_days=365, keep_monthly=None
            )

    def test_a_development_profile_file_names_no_backups(self) -> None:
        with TemporaryDirectory() as directory:
            profile = load_profile_file(write_profile(Path(directory)))

            assert profile.backups is None

    def test_a_missing_profile_file_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = Path(directory) / "development.toml"
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                status = main(["--profile", str(profile_file), "migrate"], environ={})

            assert status == EXIT_REFUSED_INPUT
            assert "development.toml" in stderr.getvalue()

    def test_a_profile_file_that_is_not_utf8_is_refused(self) -> None:
        # Windows PowerShell 5.1's `>` and `Out-File` write UTF-16.
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = folder / "development.toml"
            text = VALID_HEADER + _paths(str(folder / "stores"), folder / "inputs")
            profile_file.write_bytes(text.encode("utf-16"))
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                status = main(["--profile", str(profile_file), "migrate"], environ={})

            assert status == EXIT_REFUSED_INPUT
            assert "development.toml" in stderr.getvalue()
            assert "UTF-8" in stderr.getvalue()
            assert not (folder / "stores").exists()

    def test_a_profile_file_with_a_byte_order_mark_is_accepted(self) -> None:
        # Windows PowerShell 5.1's `Set-Content -Encoding UTF8` writes a BOM.
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = folder / "development.toml"
            text = VALID_HEADER + _paths(str(folder / "stores"), folder / "inputs")
            profile_file.write_bytes(text.encode("utf-8-sig"))

            status = main(["--profile", str(profile_file), "migrate"], environ={})

            assert status == EXIT_OK
            with BronzeStore(development_profile(folder)):
                pass

    def test_an_unsupported_format_version_is_named(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = folder / "development.toml"
            profile_file.write_text(
                'format = 2\nprofile = "development"\n'
                + _paths(str(folder), folder / "inputs"),
                encoding="utf-8",
            )
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                main(["--profile", str(profile_file), "migrate"], environ={})

            assert "format 2" in stderr.getvalue()

    def test_every_key_documented_for_development_is_accepted(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = folder / "development.toml"
            profile_file.write_text(
                VALID_HEADER
                + _paths(str(folder / "stores"), folder / "inputs")
                + f"upstream_backups = '{folder / 'upstream'}'\n"
                + '\n[dashboard]\nbind = "127.0.0.1"\nport = 8750\n',
                encoding="utf-8",
            )

            status = main(["--profile", str(profile_file), "migrate"], environ={})

            assert status == EXIT_OK
            with BronzeStore(development_profile(folder)):
                pass

    def test_every_key_documented_for_production_is_accepted(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = folder / "production.toml"
            profile_file.write_text(
                'format = 1\nprofile = "production"\n'
                + _paths(str(folder / "stores"), folder / "inputs")
                + f"backups = '{folder / 'backups'}'\n"
                + "\n[backups]\nkeep_all_days = 14\nkeep_daily_days = 365\n"
                + 'keep_monthly = "forever"\n'
                + '\n[dashboard]\nbind = "192.168.1.20"\nport = 8750\n',
                encoding="utf-8",
            )
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                status = main(["--profile", str(profile_file), "migrate"], environ={})

            # The file loads; the refusal is production's, not the file's.
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "production" in stderr.getvalue()
            assert "production.toml" not in stderr.getvalue()


if __name__ == "__main__":
    unittest.main()

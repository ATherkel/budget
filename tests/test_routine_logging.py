# Copyright 2026 Therkel
"""Routine logs stay inside the profile's test root, and carry no fixture data.

The logger is best effort: a log it may not write is refused with one fixed
warning and never changes a command's outcome. A test profile may not let its
`logs` folder, its current log file or its rotated one escape the temporary
root ADR-015 confines it to, exactly as the store, input and backup paths are
confined. The last test pins the walkthrough in `README.md` to the same privacy
rule, on the example's own synthetic fixtures.
"""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from budget.routine_logging import (
    LOG_FILE,
    LOG_FOLDER,
    LOG_MAX_BYTES,
    LOG_WARNING,
    ROTATED_LOG_FILE,
    finished,
)
from examples.silver_walkthrough import walkthrough

WARNING = LOG_WARNING.strip()


def _profile_with_logs(root: Path) -> Profile:
    """A test profile whose stores folder holds a real logs folder."""
    profile = make_test_profile(root)
    (profile.stores / LOG_FOLDER).mkdir(parents=True, exist_ok=True)
    return profile


class RoutineLogPathTests(unittest.TestCase):
    def _link(self, path: Path, target: Path, *, to_directory: bool) -> None:
        """Create the symlink a test needs, or skip where none is allowed."""
        try:
            path.symlink_to(target, target_is_directory=to_directory)
        except OSError as error:  # Windows may refuse without a privilege
            self.skipTest(f"symlinks are unavailable here: {error}")

    def _finish(self, profile: Profile) -> str:
        """Log one finished command and return the warning it wrote, if any."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            finished(profile, "rebuild", counts={"stored": 1}, duration_ms=1)
        return stderr.getvalue()

    def test_a_logs_folder_outside_the_root_is_refused(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            profile = make_test_profile(Path(directory))
            profile.stores.mkdir(parents=True, exist_ok=True)
            self._link(profile.stores / LOG_FOLDER, Path(outside), to_directory=True)

            warning = self._finish(profile)

            assert WARNING in warning
            assert list(Path(outside).iterdir()) == []

    def test_a_log_file_outside_the_root_is_refused(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            profile = _profile_with_logs(Path(directory))
            outside_file = Path(outside) / LOG_FILE
            self._link(
                profile.stores / LOG_FOLDER / LOG_FILE,
                outside_file,
                to_directory=False,
            )

            warning = self._finish(profile)

            assert WARNING in warning
            assert not outside_file.exists()

    def test_a_rotated_log_outside_the_root_is_refused(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            profile = _profile_with_logs(Path(directory))
            logs = profile.stores / LOG_FOLDER
            outside_file = Path(outside) / ROTATED_LOG_FILE
            outside_file.write_text("untouched\n", encoding="utf-8")
            current = logs / LOG_FILE
            current.write_text(
                '{"filler": "' + "x" * LOG_MAX_BYTES + '"}\n', encoding="utf-8"
            )
            self._link(logs / ROTATED_LOG_FILE, outside_file, to_directory=False)

            warning = self._finish(profile)

            assert WARNING in warning
            assert outside_file.read_text(encoding="utf-8") == "untouched\n"
            assert current.stat().st_size >= LOG_MAX_BYTES


class ExampleWalkthroughLogTests(unittest.TestCase):
    def test_the_walkthrough_logs_hold_no_example_fixture_values(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()
            with redirect_stdout(output):
                walkthrough(root)

            files = sorted((root / "stores" / LOG_FOLDER).rglob("*.jsonl"))
            assert files
            records = [
                json.loads(line)
                for path in files
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            assert {record["command"] for record in records} == {"import", "review"}
            assert "budget import --ranges ranges-march.toml -> 0" in output.getvalue()

            text = "\n".join(path.read_text(encoding="utf-8") for path in files)
            decoded = json.dumps(records, ensure_ascii=False, sort_keys=True)
            for leaked in (
                "NETTO",
                "BIO",
                "Café",
                "Mad",
                "Dagligvarer",
                "-45,00",
                "-100,00",
                "955,00",
                "-45.00",
                "-100.00",
                "955.00",
                "danske-20260306.csv",
                "danske-20260403.csv",
                "joint-current",
            ):
                assert leaked not in text
                assert leaked not in decoded


if __name__ == "__main__":
    unittest.main()

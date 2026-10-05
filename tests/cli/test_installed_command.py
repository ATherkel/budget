# Copyright 2026 Therkel
"""The installed `budget` command, run from outside the repository.

Each run is a subprocess whose working directory is a temporary folder and
whose environment is explicit, so neither the checkout nor the operator's
shell can stand in for the installed package. `migrate` runs from that folder,
so the migration SQL it applies must come from the installed package: both
`migrations/bronze/` and `migrations/silver/` ship with it and are discovered
without a source checkout on the path.
"""

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.bronze import BronzeStore
from budget.silver import SilverStore
from tests.cli.processes import explicit_environment
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0


def _console_script() -> Path:
    """The `budget` script the installation put beside this interpreter."""
    name = "budget.exe" if sys.platform == "win32" else "budget"
    return Path(sys.executable).parent / name


class InstalledCommandTests(unittest.TestCase):
    def test_the_module_migrates_a_development_profile(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)

            argv = [sys.executable, "-m", "budget", "--profile", str(profile_file)]

            completed = subprocess.run(
                [*argv, "migrate"],
                cwd=folder,
                env=explicit_environment(),
                capture_output=True,
                text=True,
                check=False,
            )

            assert completed.returncode == EXIT_OK, completed.stderr
            # Routine output holds no filenames or values: on success, none.
            assert completed.stdout == ""
            assert completed.stderr == ""
            development = development_profile(folder)
            with BronzeStore(development), SilverStore(development):
                pass

    def test_the_console_script_reads_budget_profile(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)

            completed = subprocess.run(
                [str(_console_script()), "migrate"],
                cwd=folder,
                env=explicit_environment(BUDGET_PROFILE=str(profile_file)),
                capture_output=True,
                text=True,
                check=False,
            )

            assert completed.returncode == EXIT_OK, completed.stderr
            # Routine output holds no filenames or values: on success, none.
            assert completed.stdout == ""
            assert completed.stderr == ""
            development = development_profile(folder)
            with BronzeStore(development), SilverStore(development):
                pass


if __name__ == "__main__":
    unittest.main()

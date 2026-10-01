# Copyright 2026 Therkel
"""Profiles: what one names, and the guards around a test profile."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.profiles import (
    BRONZE_STORE_NAME,
    Profile,
    ProfilePathOutsideRootError,
    UnknownProfileNameError,
)
from budget.profiles import (
    TestProfileRootRequiredError as RootRequiredError,
)
from budget.profiles import (
    test_profile as make_test_profile,
)


class ProfileTests(unittest.TestCase):
    def test_a_profile_names_its_stores_folder_and_derives_the_bronze_store(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = Profile(
                name="development",
                stores=root / "stores",
                inputs=root / "inputs",
            )

            assert profile.name == "development"
            assert (
                profile.bronze_store == (root / "stores" / BRONZE_STORE_NAME).resolve()
            )
            assert profile.bronze_store.name == "bronze.db"

    def test_a_test_profile_stays_inside_its_temporary_root(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = make_test_profile(root)

            assert profile.name == "test"
            assert profile.stores.is_relative_to(root.resolve())
            assert profile.bronze_store.is_relative_to(root.resolve())

    def test_a_test_profile_path_may_not_escape_its_root(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            escape = root / ".." / "elsewhere"

            with pytest.raises(ProfilePathOutsideRootError):
                Profile(name="test", stores=escape, inputs=root / "inputs", root=root)

            assert not (root.parent / "elsewhere").exists()

    def test_a_symlinked_stores_folder_may_not_escape_its_root(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory)
            try:
                (root / "stores").symlink_to(Path(outside), target_is_directory=True)
            except OSError as error:  # Windows may refuse without a privilege
                self.skipTest(f"symlinks are unavailable here: {error}")

            with pytest.raises(ProfilePathOutsideRootError):
                make_test_profile(root)

    def test_a_profile_is_never_read_from_the_environment(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile_file = root / "test.toml"
            profile_file.write_text("profile = 'production'\n", encoding="utf-8")
            os.environ["BUDGET_PROFILE"] = str(profile_file)
            try:
                profile = make_test_profile(root / "run")
            finally:
                os.environ.pop("BUDGET_PROFILE", None)

            assert profile.name == "test"
            assert profile.stores.is_relative_to((root / "run").resolve())

    def test_an_unknown_profile_name_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            for name in ("Production", "staging", ""):
                with self.subTest(name=name), pytest.raises(UnknownProfileNameError):
                    Profile(name=name, stores=root / "stores", inputs=root / "inputs")

    def test_a_test_profile_must_carry_its_temporary_root(self) -> None:
        with (
            TemporaryDirectory() as directory,
            pytest.raises(RootRequiredError),
        ):
            Profile(
                name="test",
                stores=Path(directory) / "stores",
                inputs=Path(directory) / "inputs",
            )

    def test_a_bronze_store_replaced_by_a_symlink_is_refused(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory)
            profile = make_test_profile(root)
            profile.stores.mkdir(parents=True)
            outside_file = Path(outside) / "bronze.db"
            outside_file.write_bytes(b"not ours")
            try:
                profile.bronze_store.symlink_to(outside_file)
            except OSError as error:  # Windows may refuse without a privilege
                self.skipTest(f"symlinks are unavailable here: {error}")

            with pytest.raises(ProfilePathOutsideRootError):
                _ = profile.bronze_store

            assert outside_file.read_bytes() == b"not ours"

    def test_a_stores_folder_replaced_by_a_symlink_is_refused(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory)
            profile = make_test_profile(root)
            stores = profile.stores
            stores.mkdir(parents=True)
            stores.rmdir()
            try:
                stores.symlink_to(Path(outside), target_is_directory=True)
            except OSError as error:  # Windows may refuse without a privilege
                self.skipTest(f"symlinks are unavailable here: {error}")

            with pytest.raises(ProfilePathOutsideRootError):
                _ = profile.bronze_store


if __name__ == "__main__":
    unittest.main()

# Copyright 2026 Therkel
"""Profiles: what one names, and the guards around a test profile."""

import inspect
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.profiles import (
    BRONZE_STORE_NAME,
    Profile,
    ProfileFoldersOverlapError,
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
                inbox=root / "inbox",
                exports=root / "exports",
            )

            assert profile.name == "development"
            assert (
                profile.bronze_store == (root / "stores" / BRONZE_STORE_NAME).resolve()
            )
            assert profile.bronze_store.name == "bronze.db"

    def test_a_profile_takes_every_field_by_name(self) -> None:
        # Its folders are all paths, so a positional call could put one folder
        # in another's place without any type error.
        positional = [
            parameter.name
            for parameter in inspect.signature(Profile).parameters.values()
            if parameter.kind is not inspect.Parameter.KEYWORD_ONLY
        ]

        assert positional == []

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
                Profile(
                    name="test",
                    stores=escape,
                    inputs=root / "inputs",
                    inbox=root / "inbox",
                    exports=root / "exports",
                    root=root,
                )

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
                    Profile(
                        name=name,
                        stores=root / "stores",
                        inputs=root / "inputs",
                        inbox=root / "inbox",
                        exports=root / "exports",
                    )

    def test_a_test_profile_must_carry_its_temporary_root(self) -> None:
        with (
            TemporaryDirectory() as directory,
            pytest.raises(RootRequiredError),
        ):
            Profile(
                name="test",
                stores=Path(directory) / "stores",
                inputs=Path(directory) / "inputs",
                inbox=Path(directory) / "inbox",
                exports=Path(directory) / "exports",
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

    def test_a_test_profile_reads_its_inputs_inside_its_root(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = make_test_profile(root)

            assert (
                profile.accounts_file == (root / "inputs" / "accounts.toml").resolve()
            )

    def test_a_test_profile_inputs_folder_may_not_escape_its_root(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            with pytest.raises(ProfilePathOutsideRootError):
                Profile(
                    name="test",
                    stores=root / "stores",
                    inputs=root / ".." / "elsewhere",
                    inbox=root / "inbox",
                    exports=root / "exports",
                    root=root,
                )

    def test_an_accounts_file_replaced_by_a_symlink_is_refused(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory)
            profile = make_test_profile(root)
            profile.inputs.mkdir(parents=True)
            outside_file = Path(outside) / "accounts.toml"
            outside_file.write_text("format = 1\n", encoding="utf-8")
            try:
                profile.accounts_file.symlink_to(outside_file)
            except OSError as error:  # Windows may refuse without a privilege
                self.skipTest(f"symlinks are unavailable here: {error}")

            with pytest.raises(ProfilePathOutsideRootError):
                _ = profile.accounts_file

    def test_a_test_profile_names_its_inbox_archive_and_import_log_inside_its_root(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = make_test_profile(root)

            assert profile.inbox == (root / "inbox").resolve()
            assert profile.exports == (root / "exports").resolve()
            assert (
                profile.import_log_file == (root / "inputs" / "imports.jsonl").resolve()
            )

    def test_a_test_profile_names_its_backups_and_their_staging_inside_its_root(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = make_test_profile(root)

            assert profile.backups == (root / "backups").resolve()
            assert (
                profile.backup_staging == (root / "stores" / "backup-staging").resolve()
            )

    def test_a_test_profile_backups_folder_may_not_escape_its_root(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            with pytest.raises(ProfilePathOutsideRootError):
                Profile(
                    name="test",
                    stores=root / "stores",
                    inputs=root / "inputs",
                    inbox=root / "inbox",
                    exports=root / "exports",
                    backups=root / ".." / "elsewhere",
                    root=root,
                )

    def test_a_test_profile_inbox_or_export_archive_may_not_escape_its_root(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            escape = root / ".." / "elsewhere"

            with self.subTest("inbox"), pytest.raises(ProfilePathOutsideRootError):
                Profile(
                    name="test",
                    stores=root / "stores",
                    inputs=root / "inputs",
                    inbox=escape,
                    exports=root / "exports",
                    root=root,
                )
            with self.subTest("exports"), pytest.raises(ProfilePathOutsideRootError):
                Profile(
                    name="test",
                    stores=root / "stores",
                    inputs=root / "inputs",
                    inbox=root / "inbox",
                    exports=escape,
                    root=root,
                )

    def test_an_inbox_and_export_archive_that_overlap_are_refused(self) -> None:
        # The archive would hold the inbox file itself, which the import then
        # removes from the inbox.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            overlaps = {
                "the same folder": (root / "household", root / "household"),
                "the inbox inside the archive": (
                    root / "exports" / "inbox",
                    root / "exports",
                ),
                "the archive inside the inbox": (root / "inbox", root / "inbox" / "x"),
            }
            for overlap, (inbox, exports) in overlaps.items():
                with (
                    self.subTest(overlap),
                    pytest.raises(ProfileFoldersOverlapError),
                ):
                    Profile(
                        name="development",
                        stores=root / "stores",
                        inputs=root / "inputs",
                        inbox=inbox,
                        exports=exports,
                    )


if __name__ == "__main__":
    unittest.main()

# Copyright 2026 Therkel
"""`Recipe`: every input one publication was built from (`publications.md`).

A recipe names each input exactly and never by "latest", so two recipes can be
compared before anything is built: equal recipes describe the same build. The
Python and SQLite versions that ran the build are recorded beside it for
diagnosis, and take no part in that comparison.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecipeImportRun:
    """One import run a build read, with its payload's SHA-256 (`payload_id`)."""

    import_run_id: str
    payload_id: str


@dataclass(frozen=True)
class Recipe:
    """The recorded inputs of one publication; its result is not part of it.

    `configuration_fingerprint` names the configuration snapshot, which the
    store keeps once per distinct content. `decision_log_position` counts the
    decision-log entries read, and `decision_log_prefix_sha256` is the SHA-256
    of the log through them. `late_booking_days` is the profile's window at the
    build, in whole days. `code_version` is None where the profile records
    none, as a development build does.
    """

    import_runs: frozenset[RecipeImportRun]
    configuration_fingerprint: str
    decision_log_position: int
    decision_log_prefix_sha256: str
    code_version: str | None
    contract_version: str
    silver_identity_version: str
    late_booking_days: int
    python_version: str = field(compare=False)
    sqlite_version: str = field(compare=False)

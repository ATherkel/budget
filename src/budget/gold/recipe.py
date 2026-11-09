# Copyright 2026 Therkel
"""`Recipe`: every input one publication was built from (`publications.md`).

A recipe names each input exactly and never by "latest", so two recipes can be
compared before anything is built: equal recipes describe the same build. The
Python and SQLite versions that ran the build are recorded beside it for
diagnosis, and take no part in that comparison. Nor do Silver's decision-log
position and prefix: the log can move while Silver's result stays the same,
and Silver's result fingerprint decides whether Gold republishes.
"""

from dataclasses import dataclass, field

from budget.silver.decisions import SilverDecision


@dataclass(frozen=True)
class RecipeImportRun:
    """One import run a build read, with its payload and declared account.

    `payload_id` is the payload's SHA-256. A recipe written before Gold schema
    7 has no recorded account, represented explicitly as `None`; readers never
    infer that account from Bronze or a later Silver result.
    """

    import_run_id: str
    payload_id: str
    account_id: str | None


@dataclass(frozen=True)
class Recipe:
    """The recorded inputs of one publication; its result is not part of it.

    `configuration_fingerprint` names the configuration snapshot, which the
    store keeps once per distinct content. `decision_log_position` counts the
    decision-log entries read, and `decision_log_prefix_sha256` is the SHA-256
    of the log through them. `late_booking_days` is the profile's window at the
    build, in whole days. `code_version` is None where the profile records
    none, as a development build does.

    The `silver_` fields copy the provenance of the Silver result the build
    read (`silver-layer.md`, *Build provenance*): its fingerprint scheme and
    result fingerprint, Silver's code version, where Silver read the decision
    log, the Bronze parser provenance, the account currencies it consumed, and
    the Silver decisions it applied, in order. `silver_decision_log_position`
    and `silver_decision_log_prefix_sha256` record where Silver read the log,
    for audit, and take no part in equality. The log can move while Silver's
    result stays the same, as a Gold-only decision does. Silver's effect on
    Gold is already named by `silver_result_fingerprint` and
    `silver_decisions`, and `decision_log_prefix_sha256` covers the whole log
    Gold read. A recipe stored before Silver provenance was kept reads back
    with every `silver_` field empty and `silver_identity_version` None.
    """

    import_runs: frozenset[RecipeImportRun]
    configuration_fingerprint: str
    decision_log_position: int
    decision_log_prefix_sha256: str
    code_version: str | None
    contract_version: str
    silver_identity_version: str | None
    late_booking_days: int
    python_version: str = field(compare=False)
    sqlite_version: str = field(compare=False)
    silver_fingerprint_scheme: str | None
    silver_result_fingerprint: str | None
    silver_code_version: str | None
    silver_decision_log_position: int | None = field(compare=False)
    silver_decision_log_prefix_sha256: str | None = field(compare=False)
    silver_bronze_parser_provenance: str | None
    silver_currencies: frozenset[tuple[str, str]]
    silver_decisions: tuple[SilverDecision, ...]

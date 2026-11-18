# Copyright 2026 Therkel
"""What Bronze says about a refused import run's reasons, where none were recorded."""


def format_1_refusal_reasons(outcome: str) -> tuple[str, ...]:
    """Return the codes a run recorded before refusal codes existed implies.

    The first import log format and the first Bronze schema recorded none, so
    a refused run reads as `legacy-unrecorded` and any other run as having
    none. The schema's backfill, replay, the import's log check and a read of
    an older store all use this, so they cannot disagree about an old run.
    """
    return ("legacy-unrecorded",) if outcome == "refused" else ()

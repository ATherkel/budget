# Architectural Principles

## Principle 1: Source Agnostic Analytics

Analytics only consumes Gold datasets.

Analytics has no knowledge of:

- banks
- APIs
- CSV files
- import formats

## Principle 2: Immutable Raw Data

Imported transaction data is never modified.

Raw data is retained indefinitely.

## Principle 3: Deterministic Transformations

Silver data must always be reproducible from Bronze and the recorded manual
decisions.

Gold data must always be reproducible from its recipe: the import runs, the
household configuration, the manual decisions, and the code version it was
built with. A build never reads the clock. See
[ADR-014](decisions/ADR-014-gold-publications-and-history.md).

## Principle 4: Replaceable Modules

Each module can be replaced without affecting downstream consumers.

## Principle 5: Python First

The primary implementation language is Python.

TypeScript is only introduced when a clear advantage exists.

## Principle 6: Domain Before Technology

Business concepts drive architecture.

Technology choices follow domain requirements.
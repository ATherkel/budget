# Bronze Layer

## Purpose

Persist source data exactly as received.

## Inputs

- Danske API
- CSV exports
- Future bank connectors

## Outputs

Bronze transaction records.

Import-run metadata, including the export date: the date the export was
produced, read from the source filename (Danske: the `-YYYYMMDD` suffix, e.g.
`-20260914`) or declared by the operator at import. It bounds how far the
export's evidence reaches.

## Rules

No transformations allowed.

No categorization allowed.

No deduplication allowed.

## Responsibilities

- provenance
- auditability
- replayability

## Ownership

Bronze Agent
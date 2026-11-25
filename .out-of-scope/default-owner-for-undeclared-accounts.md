# A default owner for accounts that declare none

An account in `accounts.toml` without `owner` is refused, and the error says
what to add. There is no implicit "no owner".

## Why this is out of scope

A default would hide a typo or a forgotten line, and put the account in an
owner group nobody chose, skewing per-owner figures (ADR-021). A shared
account gets an owner the household declares, such as `faelles = "Fælles"`.
Older Gold rows already have an unknown member, `legacy-unrecorded`
(`docs/architecture/gold-contract.md`, `GoldAccount`).

## Prior requests

- #508: raised during the owner's review

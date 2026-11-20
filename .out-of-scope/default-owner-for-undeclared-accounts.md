# A default owner for accounts that declare none

An account in `accounts.toml` without `owner = "<id>"` is a configuration
error naming the account, and nothing is imported or rebuilt until it is
fixed. The project does not fall back to an implicit "no owner" for such an
account.

## Why this is out of scope

The owner is a line the household writes once per account, in its own file.
The refusal says what to add (`src/budget/inputs/accounts.py`), so a missing
owner costs one edit. A silent default would instead hide the mistakes the
refusal catches:

- **A typo or a forgotten line goes unnoticed.** The account lands under "no
  owner" in Gold without any warning.
- **Per-owner figures go wrong.** The dashboard's owner selection and the
  per-person spending and balances of ADR-021 would show a group nobody chose,
  and leave the account out of the owner it belongs to.

What a default seems to offer is already covered:

- **A shared account** gets an owner the household declares, such as
  `faelles = "Fælles"`. The choice stays visible in the file.
- **An unknown member** in Kimball's sense belongs where the data cannot be
  corrected at its source. Gold has one: accounts published before owners
  were recorded carry the reserved owner `legacy-unrecorded` until the next
  rebuild (`docs/architecture/gold-contract.md`, `GoldAccount`).

A fallback the household names explicitly in `[owners]` would avoid the
silent part. It would still add a rule and a test for a case that one line
in the file already handles, so it is not planned either.

## Prior requests

- #508: raised during the owner's review of the account-owner stack

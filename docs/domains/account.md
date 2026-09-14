# Account Domain

An account is a financial account whose activity can be imported into the
household platform.

Required attributes:

- stable internal `account_id`: household-assigned and durable, never derived
  from a bank account number
- display name
- account type (`current`, `savings`, `credit`, `investment`, or `other`)
- currency
- ownership scope (`household`, `person`, or `external`)
- closing date, when the account has closed

Sensitive identifiers such as full IBANs are stored only when needed and are
never exposed in reports or logs. An account can have several source-specific
identifiers, which belong in source metadata rather than the Gold consumer
contract.

An account within the household reporting boundary — ownership scope
`household` or `person` — is eligible for internal-transfer matching. A
counterparty with ownership scope `external` cannot be presumed to be a
transfer; a transfer between a shared and an individually-owned account is
still internal.

## First-Release Taxonomy

- Only accounts inside the reporting boundary are imported and reported; they
  are the Gold account dimension. An `external` account is never imported.
- Supported account types are `current` and `savings`, in `DKK`. The other
  types stay reserved: a `credit`, `investment`, or `other` account is rejected
  until a reporting policy for it exists, which preserves the extension point
  for later debt support.
- There is no account hierarchy and no person dimension. `account_type` is
  the only grouping, and the display name can say whose account it is.
- An account's managed period starts with its first booked transaction and
  ends in the month of its closing date. Reports do not show gaps for months
  outside it.

# Account Domain

An account is a financial account whose activity can be imported into the
household platform.

Required attributes:

- stable internal `account_id`
- display name
- account type (`current`, `savings`, `credit`, `investment`, or `other`)
- currency
- ownership scope (`household`, `person`, or `external`)
- active/inactive state

Sensitive identifiers such as full IBANs are stored only when needed and are
never exposed in reports or logs. An account can have several source-specific
identifiers, which belong in source metadata rather than the Gold consumer
contract.

An account marked `household` is eligible for internal-transfer matching. A
counterparty outside this set cannot be presumed to be a transfer.

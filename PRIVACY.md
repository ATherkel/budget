# Privacy notice

Last updated: 2026-10-09

## Scope and contact

This notice describes Therkel's personal, self-hosted Budget installation for
budgeting and financial reporting. It is not a hosted service for other people.
The operator is Therkel ([@ATherkel](https://github.com/ATherkel)).
Data-protection contact: **Pending the operator's chosen email address. This
draft must be completed before it is used for application registration.**

## Information used

The current application imports bank export files and the operator's household
configuration. These can contain account identifiers, transaction dates,
descriptions, amounts, balances, bank categories, and manually entered labels
and decisions. Descriptions may also contain information about counterparties.
The application uses these records to organise transactions and produce
financial reports. It also records operational information about imports and
commands for troubleshooting and reproducibility.

## Storage and sharing

The operator controls the installation and the folders holding its databases,
source exports, configuration, logs, and backups. Running this self-hosted copy
does not give the repository's contributors access to those files. Any cloud
storage, backup synchronisation, or sharing the operator chooses is separate
from the application and must be considered when deciding who can access data.

Enable Banking integration is planned, but is not implemented in the current
application. If enabled in a future version, the operator will authorise access
to their own account information through their bank. Enable Banking will
retrieve authorised account details, balances, and transactions and deliver
them to this installation under its own
[end-user terms](https://tilisy.enablebanking.com/terms). This notice will be
updated to reflect the implemented integration before it is used.

## Retention and control

Raw imported data and source exports are retained indefinitely for reproducible
reporting unless the operator removes them. Backup retention depends on the
installation's configuration; monthly backups can also be kept indefinitely.
Deleting an input file or revoking future bank access does not erase existing
imports or backups.

The operator controls removal of the installation's stored data, exports,
configuration, logs, and backup copies, including any synchronised copies.
There is no single application command that promises erasure of all copies.
Contact the operator about access, corrections, or deletion concerning this
installation; do not put bank records or credentials in public GitHub issues.

## Other installations

Someone running their own copy must publish a notice identifying themselves
and their contact address, storage, recipients, retention, and actual use.
This notice does not describe their installation or provide their contact point.

# ADR-008: One Category per Booked Transaction; No Category Splits in the First Release

**Status:** Proposed

## Context

A single purchase can in reality cover several categories, such as groceries
and household goods in one supermarket receipt. Kimball treats "one booked
transaction" and "one category allocation of a transaction" as different
grains that belong in different fact tables. The first-release sources carry
one row per booked transaction, with no line items. Classification rules and
manual mappings are configured as files and applied through a read-only
dashboard. [Issue #6](https://github.com/ATherkel/budget/issues/6) asked for
an explicit decision rather than an assumption either way.

## Decision

The first-release transaction fact has the grain of one booked transaction. A
classified booked transaction carries exactly one category. A booked
transaction is never split across categories. There is no category allocation
fact and no allocation type in the consumer contract.

## Considered Options

- **Full category splits now.** Rejected for the first release. Splits need a
  manual split-entry workflow, an allocation-sum invariant (allocations must
  equal the transaction amount), and rules for refunds against split
  purchases. None of these are needed to deliver trustworthy monthly totals.
- **An allocation fact from day one, always one allocation per transaction.**
  Rejected. It adds a type, a join, and an invariant that deliver no value
  until splits exist.

## Consequences

- Category spending is a sum over transactions grouped by `category_id`. A
  mixed purchase is reported under its single chosen category.
- Adding splits later means adding a separate category allocation fact at its
  own grain, beside the transaction fact rather than replacing its grain. This
  is a Gold contract version change and needs a new ADR.

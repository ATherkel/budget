# System Architecture

## Medallion Architecture

```text
Bank APIs
CSV Files
Manual Imports
        │
        ▼
      Bronze
        │
        ▼
      Silver
        │
        ▼
       Gold
        │
        ▼
    Analytics
        │
        ▼
   Presentation
```

## Layer Responsibilities

### Bronze

Store imported data exactly as received and split it into source records.

No business logic.

No categorization.

No interpretation: no typing, normalization, status mapping, or deduplication.

### Silver

Normalize transaction formats and map source statuses to booked or unbooked.

Create canonical transaction structure.

Perform validation and quarantine.

Resolve duplicates and verify the merge against bank-stated balances.

### Gold

Apply business semantics.

Determine:

- income
- expense
- transfer

Apply:

- categories, as one allocation per classified transaction
- account relationships
- budget mappings (future)

Publish:

- category allocations
- account balance snapshots and coverage

Gold becomes the stable business layer: a small dimensional model described
in `architecture/gold-layer.md`.

### Analytics

Produce:

- monthly reports
- annual reports
- category summaries
- cashflow metrics

Consumes Gold only.

### Presentation

Render dashboards.

Consumes Analytics only.
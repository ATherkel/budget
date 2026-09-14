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

Store imported data exactly as received.

No business logic.

No categorization.

No transformation.

### Silver

Normalize transaction formats.

Create canonical transaction structure.

Perform validation.

Detect duplicates.

### Gold

Apply business semantics.

Determine:

- income
- expense
- transfer

Apply:

- categories
- account relationships
- budget mappings

Gold becomes the stable business layer.

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
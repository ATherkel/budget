# Delivery Roadmap

## Phase 0 — Contracts and Decisions (current)

**Goal:** establish stable boundaries before application code exists.

Deliverables:

- Architecture, domain, and agent documentation.
- A versioned Gold data contract.
- ADRs for the Python-first, medallion, immutability, and dependency rules.
- A documented sample-import profile for the existing Danske Bank CSV files.

Exit criteria:

- An agent can implement a layer from its own brief and contracts.
- Analytics and UI work can start using fixtures that satisfy the Gold contract.

## Phase 1 — Core Data Foundation

**Goal:** make Bronze, Silver, and Gold reproducible from local CSV fixtures.

Deliverables:

- Python project tooling and database migrations.
- Bronze import-run and raw-record persistence.
- Danske CSV parser, canonical Silver records, validation, and deduplication.
- Gold classification with an auditable manual override mechanism.

Exit criteria:

- Re-running an unchanged import is idempotent.
- A Gold dataset can be rebuilt from the retained source data.

## Phase 2 — Analytics

**Goal:** derive household reports exclusively from Gold transactions.

Deliverables:

- Monthly, annual, category, and account-activity reporting.
- Transfer exclusion and savings-rate calculation.
- Reproducible query/service layer plus contract tests.

Exit criteria:

- Analytics tests use only Gold fixtures or the Gold repository interface.

## Phase 3 — Presentation

**Goal:** provide a secure, phone-friendly household dashboard.

Deliverables:

- FastAPI application with server-rendered Jinja/HTMX views.
- Plotly charts, authentication, and responsive layouts.

Exit criteria:

- The dashboard has no dependency on source-specific CSV or bank code.

## Phase 4 — Automation and Bank Connectors

**Goal:** introduce additional sources without changing Gold consumers.

Deliverables:

- Scheduled local imports.
- Bank-connector interface and one consented read-only connector.

Exit criteria:

- A new connector changes only Bronze/Silver configuration and code.

## Phase 5 — Planning and Forecasting

**Goal:** add budgets, projections, and subscription detection.

Deliverables:

- Budget targets, forecast assumptions, projections, and explanations.

Exit criteria:

- Forecasts are derived from Gold facts and explicitly versioned assumptions.

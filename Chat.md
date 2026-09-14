Me:
```
We are customers at Danske Bank in DK. I believe but am not sure they have an API we can extract our transactions from.

What I would like to prepare is a plan to implement a home overview of our budget and expenses. Per monthly and annual and transaction type and account. We have a main budget account that we move money around from.

Can you help me get started with a markdown file containing an implementation plan? I want to use my not yet created git rep https://github.com/atherkel/budget

Probably want to make an app I can host somewhere that we can access from our phones.
```

Response:
```
Yes. Danske Bank does expose APIs for account and transaction data, but there are two very different paths:

1. **PSD2/Open Banking APIs** (intended for regulated third parties and consent-based access). These are more cumbersome to use directly. 
2. **Premium Account Transaction & Balance API** (real-time transaction and balance access). This appears targeted primarily at business customers and requires onboarding to their developer platform. 

Before investing heavily in architecture, I would first verify whether your specific personal/private accounts can be accessed through either:
- Danske Bank's PSD2 APIs, or
- a third-party aggregator such as GoCardless Bank Account Data (formerly Nordigen), which often provides a much easier route for personal finance applications.

For your use case, I would design the solution assuming **multiple possible bank connectors**. That avoids coupling the whole project to Danske Bank.

---

# Suggested Architecture

Given your actuarial background, I'd optimize for:

- Reproducible data pipeline
- Historical transaction storage
- Categorization rules
- Simple analytics
- Self-hosting
- Mobile-friendly UI

I would *not* start with a mobile app.

Instead:

```text
Danske Bank API
      │
      ▼
Import Service
      │
      ▼
PostgreSQL
      │
 ┌────┴────┐
 ▼         ▼
Rules    Analytics
Engine
 └────┬────┘
      ▼
Web Application
      ▼
Phone Browser / PWA
```

A Progressive Web App (PWA) will behave almost like a native app on iPhone and Android while being vastly simpler.

---

# Tech Stack Recommendation

For a solo project:

| Layer | Technology |
|---------|------------|
| Frontend | Next.js |
| Backend API | Next.js API routes |
| Database | PostgreSQL |
| ORM | Prisma |
| Auth | NextAuth/Auth.js |
| Charts | Recharts |
| Hosting | Railway or Fly.io |
| CI/CD | GitHub Actions |

This keeps everything TypeScript end-to-end.

---

# Data Model

Core entities:

```text
Account
├── Transactions
├── Balances

Category
├── Groceries
├── Utilities
├── Mortgage
├── Transport
├── Entertainment
├── Salary
├── Internal Transfer

Rule
├── "NETTO" -> Groceries
├── "DSB" -> Transport
├── "MORTGAGE" -> Mortgage

Budget
├── Monthly target
├── Annual target
```

---

# Internal Transfer Detection

This is important in your setup.

You mentioned:

> We have a main budget account that we move money around from.

You'll want transfers excluded from spending analytics.

Example:

```text
Budget Account
    ↓
Savings Account
```

should not count as an expense.

Therefore:

```sql
transaction_type
----------------
expense
income
transfer
```

and analytics should only aggregate:

```sql
WHERE transaction_type = 'expense'
```

---

# Reports to Build First

### Monthly Overview

```text
June 2026

Income       42,000
Expenses     31,500
Savings      10,500

Savings Rate 25%
```

### Category Breakdown

```text
Groceries       6,200
Transport       1,500
Housing        14,000
Utilities       1,100
Entertainment   2,400
```

### Account Breakdown

```text
Budget Account
Savings Account
Investment Account
```

### Annual Trend

```text
2024
2025
2026
```

with month-by-month charts.

---

# MVP Roadmap

### Phase 1

Import CSV manually.

No bank integration.

Build:

- accounts
- transactions
- categories
- reports

This gets 80% of the value.

### Phase 2

Automatic categorization rules.

```text
NETTO -> Groceries
REMA -> Groceries
OK -> Fuel
```

### Phase 3

Bank integration.

Build a connector abstraction:

```ts
interface BankConnector {
  syncTransactions(): Promise<Transaction[]>;
}
```

Then implement:

```ts
DanskeBankConnector
NordigenConnector
CsvConnector
```

### Phase 4

Forecasting

This is where your actuarial skills become useful.

Examples:

- Expected month-end spending
- Annual budget projections
- Cash flow forecast
- Subscription detection

---

# Initial Repository Structure

For `github.com/atherkel/budget` I would start with:

```text
budget/
├── apps/
│   └── web
│
├── packages/
│   ├── db
│   ├── analytics
│   ├── bank-connectors
│   └── shared
│
├── docs/
│   └── implementation-plan.md
│
├── prisma/
│
└── .github/
    └── workflows/
```

---

## Draft `docs/implementation-plan.md`

# Budget Application Implementation Plan

## Goal

Create a self-hosted household budgeting application that:

- Imports transactions from Danske Bank and other potential sources.
- Tracks spending by category, account, month, and year.
- Distinguishes transfers from actual spending.
- Provides dashboards accessible from phones and desktops.
- Supports historical analysis and future forecasting.

---

## Success Criteria

### MVP

- Multiple accounts supported.
- Transaction import via CSV.
- Transaction categorization.
- Monthly and annual reporting.
- Mobile-friendly interface.

### Future

- Automatic bank synchronization.
- Forecasting and budgeting.
- Savings and cashflow projections.
- Shared household access.

---

## Architecture

### Frontend

- Next.js
- TypeScript
- Tailwind
- Recharts

### Backend

- Next.js API Routes
- Prisma ORM

### Database

- PostgreSQL

### Hosting

- Railway or Fly.io

---

## Core Domain Model

### Account

Represents a bank account.

Fields:

- id
- name
- iban
- accountType

### Transaction

Represents a single bank transaction.

Fields:

- id
- accountId
- bookingDate
- amount
- currency
- description
- counterparty
- categoryId
- transactionType

### Category

Fields:

- id
- name
- parentCategoryId

### Rule

Automatic categorization rules.

Fields:

- id
- pattern
- categoryId
- priority

### Budget

Fields:

- categoryId
- month
- amount

---

## Transaction Types

Supported types:

- income
- expense
- transfer

Transfers must be excluded from spending calculations.

---

## Reporting

### Monthly Dashboard

Display:

- income
- expenses
- savings
- savings rate

### Category Dashboard

Display:

- monthly spend
- annual spend
- budget variance

### Account Dashboard

Display:

- balances
- transfers
- account activity

### Trend Dashboard

Display:

- month-over-month spending
- annual totals
- category trends

---

## Data Import Strategy

### Phase 1

CSV import.

### Phase 2

Automatic categorization.

### Phase 3

Bank API integration.

Introduce:

```typescript
interface BankConnector {
  syncTransactions(): Promise<Transaction[]>;
}
```

Implement:

- CsvConnector
- DanskeBankConnector
- NordigenConnector

---

## Security

- Authentication required.
- Secrets stored as environment variables.
- Read-only bank access whenever possible.

---

## Future Enhancements

- Cashflow forecasting.
- Subscription detection.
- Savings goals.
- Investment account integration.
- Household financial health score.

---

## Milestones

### Milestone 1

Repository setup.

### Milestone 2

Database schema.

### Milestone 3

CSV import.

### Milestone 4

Dashboard.

### Milestone 5

Rule engine.

### Milestone 6

Bank synchronization.

### Milestone 7

Forecasting.

My recommendation would be to **start with CSV imports first**, even if API access exists. You'll learn the transaction structures, transfer patterns, and categorization rules before spending time on authentication and bank integrations. Once the analytics model is solid, replacing the import source with an API becomes straightforward.
```
Me:
```
This is a really good initial plan. You understood probably 90% of my undescribed thoughts. This is a really good initial step. You probably got 90% of what my undescribed thoughts are, like moduling, modularization, reusability, and exchangeability. Like this CSV is a good approach. I agree with that. Now, to continue, I would like to use the Matt Poecock Wayfinder skill, and we need to structure everything into Markdown files so that we can delegate the stuff out to sub-agents. There is no reason to have everything orchestrated, done from a single endpoint. Also, I have one comment: I am fluent in Python and a novice in JavaScript. If there is anything that we can code in Python without any loss of functionality, I would prefer that coding language. I am also fluent in PowerShell, but I don't think these competences will help us with any of the modules for this project.

Link to Wayfinder: https://github.com/mattpocock/skills/blob/main/skills/engineering/wayfinder/SKILL.md 

Use local files for now.
```
Response:
```
I think we should lean much harder into Python than my first draft did.

For this project, JavaScript/TypeScript is only clearly advantageous in one place: the web UI. Everything else can comfortably be Python:

| Module | Language |
|----------|----------|
| Bank connectors | Python |
| CSV importers | Python |
| Categorization engine | Python |
| Analytics engine | Python |
| Forecasting | Python |
| Data model | Python |
| API | Python |
| Background jobs | Python |
| Web UI | Python (FastAPI + HTMX) or React if needed |

Given your profile, I'd actually challenge the assumption that we need Next.js at all.

A very strong stack would be:

```text
Frontend:
  HTMX + Jinja templates

Backend:
  FastAPI

Database:
  PostgreSQL

ORM:
  SQLAlchemy

Jobs:
  APScheduler

Charts:
  Plotly

Hosting:
  Fly.io / Railway / VPS
```

Advantages:

- Nearly 100% Python.
- No Node ecosystem complexity.
- Easier for you to maintain.
- Excellent fit for a household budgeting system.

---

## Wayfinder Adaptation

The key idea from Wayfinder is:

> Design the boundaries first. Build the implementation second.

For this project I would create a `/docs` directory that becomes the source of truth for all future agents.

Something like:

```text
docs/
├── vision.md
├── architecture.md
├── roadmap.md
│
├── domains/
│   ├── transactions.md
│   ├── accounts.md
│   ├── categories.md
│   ├── budgets.md
│   └── forecasting.md
│
├── modules/
│   ├── csv-importer.md
│   ├── bank-connectors.md
│   ├── categorization-engine.md
│   ├── analytics-engine.md
│   ├── api.md
│   └── frontend.md
│
├── agents/
│   ├── csv-import-agent.md
│   ├── connector-agent.md
│   ├── analytics-agent.md
│   ├── frontend-agent.md
│   └── forecasting-agent.md
│
└── decisions/
    ├── ADR-001-python-first.md
    ├── ADR-002-csv-before-api.md
    └── ADR-003-transfer-detection.md
```

Notice that:

- domains describe business concepts
- modules describe technical implementations
- agents describe delegated work packages
- ADRs describe decisions

This separation is extremely useful once multiple agents start contributing.

---

## Architectural Principle

I would define the core principle immediately:

```text
The system is transaction-centric.

All analytics, reports, forecasts, and budgets
derive from immutable transaction records.

No report stores calculated values.
All reports are reproducible from source data.
```

As an actuary, you'll probably appreciate this.

It's analogous to:

```text
Observed data
    →
Derived assumptions
    →
Derived metrics
```

rather than storing aggregated results everywhere.

---

## First 5 Documents

If I were bootstrapping the repo tomorrow, I'd create these first:

### vision.md

Answers:

```text
Why does this project exist?
Who uses it?
What problems does it solve?
```

---

### architecture.md

Answers:

```text
What are the major modules?

How do they interact?

What dependencies are allowed?
```

---

### transactions.md

Most important document.

Defines:

```text
Transaction
Account
Transfer
Income
Expense
Balance
```

Everything else depends on this.

---

### csv-importer.md

Defines:

```text
Input formats
Validation
Deduplication
Import workflow
```

---

### categorization-engine.md

Defines:

```text
Rules
Priority
Overrides
Manual corrections
Learning strategy
```

---

## Suggested Module Boundaries

I would explicitly define these interfaces.

### Import Layer

```python
class TransactionImporter(Protocol):
    def import_transactions(self) -> list[Transaction]:
        ...
```

---

### Categorization Layer

```python
class Categorizer(Protocol):
    def categorize(
        self,
        transaction: Transaction
    ) -> Category:
        ...
```

---

### Analytics Layer

```python
class AnalyticsProvider(Protocol):
    def monthly_report(
        self,
        year: int,
        month: int
    ) -> MonthlyReport:
        ...
```

This allows complete replacement of implementations.

---

## Proposed Initial Roadmap

### Phase 0

Repository planning.

Deliverables:

```text
vision.md
architecture.md
roadmap.md
ADRs
```

No code.

---

### Phase 1

Core domain.

Deliverables:

```text
Transaction model
Account model
Category model
Transfer model
```

Still almost no UI.

---

### Phase 2

CSV ingestion.

Deliverables:

```text
CSV parser
Deduplication
Persistence
```

---

### Phase 3

Analytics.

Deliverables:

```text
Monthly reports
Annual reports
Category breakdowns
Transfer exclusion
```

---

### Phase 4

Web application.

Deliverables:

```text
Dashboard
Charts
Authentication
Mobile support
```

---

### Phase 5

Bank integrations.

Only now do we care about Danske Bank.

---

One additional architectural decision I would make immediately:

**Store raw imported transactions forever.**

Create both:

```text
raw_transactions
```

and

```text
normalized_transactions
```

tables.

Never overwrite raw bank data.

That single decision tends to save enormous amounts of pain when:
- categorization rules change,
- import logic changes,
- a bank changes export format,
- you discover a bug six months later.

For a finance system, preserving provenance is worth the extra storage.
```
Me:
```
Can you help convert this to markdown plan documents? An overview plan for the orchestration and a markdown for each subtask? So, my idea (sparked from your response) is that we make each module entirely separable. That is, everything about transactions happen in an ETL/ECCD level, bronze/silver/gold. Meaning phase 3 only ever sees the gold (or above) data layer. That way, analytics and onward are completely untouched and unaware if I for example change bank.
```
Response:
```
Yes. In fact, I think you've just identified the most important architectural decision of the project:

> Analytics must never know where data came from.

I would formalize that as:

```text
Source Systems
      ↓
Bronze
      ↓
Silver
      ↓
Gold
      ↓
Analytics
      ↓
Presentation
```

where every layer only depends on the layer immediately below it.

This is much closer to a data platform than a traditional CRUD application, and I think it's the correct mental model.

The consequence is that changing:

- Danske → Nordea
- Danske → CSV
- CSV → PSD2 API
- PSD2 → Open Banking aggregator

should require changes only inside Bronze and possibly Silver.

Gold remains stable.

Analytics remains stable.

Dashboards remain stable.

Forecasting remains stable.

---

# Proposed Documentation Structure

```text
docs/
│
├── 00-vision.md
├── 01-principles.md
├── 02-architecture.md
├── 03-roadmap.md
│
├── domains/
│   ├── account.md
│   ├── transaction.md
│   ├── category.md
│   ├── budget.md
│   └── forecast.md
│
├── architecture/
│   ├── bronze-layer.md
│   ├── silver-layer.md
│   ├── gold-layer.md
│   ├── analytics-layer.md
│   └── presentation-layer.md
│
├── agents/
│   ├── bronze-agent.md
│   ├── silver-agent.md
│   ├── gold-agent.md
│   ├── analytics-agent.md
│   └── ui-agent.md
│
└── decisions/
    ├── ADR-001-python-first.md
    ├── ADR-002-medallion-architecture.md
    ├── ADR-003-immutable-transactions.md
    └── ADR-004-analytics-only-reads-gold.md
```

---

# docs/00-vision.md

# Budget Platform Vision

## Goal

Build a household financial platform that provides a complete view of:

- spending
- income
- transfers
- budgets
- savings
- forecasts

across all current and future financial institutions.

The platform must remain independent of any specific bank.

## Key Requirement

Analytics and reporting must not depend on transaction source systems.

A bank change should not require modifications to analytics, dashboards, forecasts, or business logic.

## Design Philosophy

The platform is a data platform first and a web application second.

The source of truth is transaction data.

All metrics are reproducible from stored transactions.

No report is a system of record.

## Success Criteria

- New banks can be added without changing analytics.
- Historical data remains available forever.
- All transformations are traceable.
- Reports are reproducible.
- Mobile-first experience.
- Self-hostable.

---

# docs/01-principles.md

# Architectural Principles

## Principle 1: Source Agnostic Analytics

Analytics only consumes Gold datasets.

Analytics has no knowledge of:

- banks
- APIs
- CSV files
- import formats

## Principle 2: Immutable Raw Data

Imported transaction data is never modified.

Raw data is retained indefinitely.

## Principle 3: Deterministic Transformations

Silver data must always be reproducible from Bronze.

Gold data must always be reproducible from Silver.

## Principle 4: Replaceable Modules

Each module can be replaced without affecting downstream consumers.

## Principle 5: Python First

The primary implementation language is Python.

TypeScript is only introduced when a clear advantage exists.

## Principle 6: Domain Before Technology

Business concepts drive architecture.

Technology choices follow domain requirements.

---

# docs/02-architecture.md

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

---

# docs/architecture/bronze-layer.md

# Bronze Layer

## Purpose

Persist source data exactly as received.

## Inputs

- Danske API
- CSV exports
- Future bank connectors

## Outputs

Bronze transaction records.

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

---

# docs/architecture/silver-layer.md

# Silver Layer

## Purpose

Convert source-specific data into a canonical model.

## Canonical Transaction

```python
Transaction(
    transaction_id: str,
    account_id: str,
    booking_date: date,
    amount: Decimal,
    currency: str,
    description: str,
    source_system: str
)
```

## Responsibilities

- schema normalization
- validation
- deduplication
- enrichment of technical metadata

## Non-Responsibilities

- categorization
- budgeting
- reporting

## Ownership

Silver Agent

---

# docs/architecture/gold-layer.md

# Gold Layer

## Purpose

Represent financial business facts.

## Responsibilities

Classify:

- income
- expense
- transfer

Assign:

- categories
- account groups
- budget groups

## Output Contract

Gold data must remain stable even if source systems change.

## Example

```python
GoldTransaction(
    transaction_id: str,
    category: str,
    transaction_type: str,
    budget_group: str,
    reporting_period: str
)
```

## Consumers

- analytics
- forecasting
- dashboards

## Ownership

Gold Agent

---

# docs/agents/analytics-agent.md

# Analytics Agent

## Mission

Produce reporting datasets from Gold data.

## Inputs

Gold datasets only.

## Forbidden Dependencies

- APIs
- CSV files
- Bronze tables
- Silver tables

## Deliverables

### Monthly Report

Income

Expenses

Savings

Savings Rate

### Category Report

Spend by category.

### Trend Report

Month-over-month trends.

### Account Report

Balances and activity.

## Acceptance Criteria

A source-system replacement must not require any code changes.

The next document I would create is actually **`gold-contract.md`**.

That document defines the exact schema that Gold exposes to the rest of the platform. Once that contract is stable, analytics, forecasting, dashboards, AI categorization, and future mobile apps can all be developed independently by separate agents against the same interface. In a Wayfinder-style workflow, the Gold contract becomes the primary boundary around which work is delegated.
```
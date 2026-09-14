# ADR-001: Python-First Implementation

**Status:** Accepted

## Context

The household maintainer is fluent in Python and prefers it where no material
functionality is lost. The application needs ingestion, transformation,
analytics, scheduling, and a web interface.

## Decision

Use Python as the default language. The initial web direction is FastAPI,
Jinja/HTMX, and Plotly. Introduce TypeScript only when a concrete UI or tooling
benefit outweighs the maintenance cost.

## Consequences

- One primary ecosystem for data and application code.
- A modern SPA is not ruled out, but it needs a documented ADR.

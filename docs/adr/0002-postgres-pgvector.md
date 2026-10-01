# ADR 0002 — PostgreSQL + pgvector instead of a separate vector database

- **Status:** Accepted (Phase 1)
- **Date:** 2026-10-01

## Context
Matching (Phase 4) compares resume embeddings with tens of thousands of job embeddings and
combines the result with relational filters (active jobs, location, remote, experience) and
skill overlap. We also need transactional data for everything else.

## Decision
Store embeddings in PostgreSQL with the **pgvector** extension (HNSW indexes), alongside the
relational data. The extension is enabled in the very first migration.

## Consequences
- ✅ One database to run, back up and secure; one query can filter relationally **and** rank by
  vector distance; embeddings commit in the same transaction as the rows they describe.
- ✅ Azure Database for PostgreSQL supports pgvector, so the cloud move is configuration only.
- ✅ At GlideUp's scale (≤ ~1M vectors) HNSW in Postgres gives millisecond queries.
- ⚠️ Vector search shares CPU/RAM with OLTP queries. Mitigation: a read replica for matching
  if needed; re-evaluate a dedicated vector store (Qdrant, Azure AI Search) beyond ~10M vectors
  or if recall/latency targets are missed. Matching sits behind a service interface, so the
  swap stays local to one module.

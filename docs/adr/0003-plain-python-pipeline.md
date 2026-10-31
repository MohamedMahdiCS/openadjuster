# ADR 0003: A plain Python pipeline instead of an agent framework

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

The original plan had a LangGraph workflow, an investigator agent with tools, clause retrieval with
embeddings, PostgreSQL with pgvector and a Docker stack.

Once code took over the rules, most of the reasons for that stack went away. A claim follows the same
steps every time. The policy is short and structured, so clauses are looked up by ID. Nothing runs
for days or needs durable state.

## Decision

Keep one straight pipeline in plain Python, with JSON files for cases and an append-only audit log.
There is no investigator agent. When signals conflict, the claim goes to a person.

The MCP server exposes the same four operations as the console: list, assess, review and fetch a case.

## Consequences

- There is less to break, and a laptop can run it with `uv` and Ollama alone.
- Every path through the system is easy to test and replay.
- It doesn't scale to several reviewers or concurrent writers. A real deployment would need a database.
- The plan's LangGraph, RAG and Docker items were dropped on purpose. If a claim type appears that
  needs open-ended investigation, an agent could sit behind the same review step.

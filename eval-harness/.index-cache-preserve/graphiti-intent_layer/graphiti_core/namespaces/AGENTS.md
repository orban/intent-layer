# Namespaces

Typed accessor objects for entity/edge CRUD with automatic embedding generation.

## Architecture

`graphiti.nodes.entity`, `graphiti.edges.entity`, etc. are namespace objects that wrap driver operations. They handle embedding generation before save, so callers don't need to manage embeddings manually.

## Contracts

- Namespace accessors are the preferred public API for direct CRUD operations
- Always generates embeddings before persisting — don't bypass to driver directly
- Available via `Graphiti` instance properties (e.g., `graphiti.nodes`, `graphiti.edges`)

## Key files

- `nodes.py` — `EntityNodeNamespace`, `EpisodicNodeNamespace`, etc.
- `edges.py` — `EntityEdgeNamespace`, `EpisodicEdgeNamespace`, etc.

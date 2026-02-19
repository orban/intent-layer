# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Graphiti (`graphiti-core`) is a Python framework for building temporally-aware knowledge graphs for AI agents. It ingests "episodes" (messages, JSON, text), extracts entities and relationships via LLMs, and builds a queryable graph that tracks when facts were valid. Built by Zep Software.

## Testing

Run only the specific test file relevant to the bug, not the full test suite. For example:

```bash
uv run pytest tests/test_specific_file.py -x --tb=short
uv run pytest tests/test_specific_file.py::test_method_name
```

Environment variables needed for unit tests: `DISABLE_NEPTUNE=1 DISABLE_NEO4J=1 DISABLE_FALKORDB=1 DISABLE_KUZU=1`

## Architecture

### Episode ingestion pipeline

`Graphiti.add_episode()` runs: retrieve context → extract nodes via LLM → resolve/dedup nodes → extract edges via LLM → resolve/dedup edges → generate embeddings → save to graph → update communities.

### Key abstractions

- **`Graphiti`** (`graphiti.py`) — main entry point, constructor takes `graph_driver`, `llm_client`, `embedder`, `cross_encoder`, `tracer`
- **`GraphitiClients`** (`graphiti_types.py`) — bundles all clients into one Pydantic model passed through internal functions
- **`GraphDriver`** (`driver/driver.py`) — ABC for graph databases: Neo4j, FalkorDB, Kuzu, Neptune
- **`group_id`** — partition key on every node/edge, isolates graphs per user/agent

### Graph data model

Nodes: `EntityNode`, `EpisodicNode`, `CommunityNode`, `SagaNode` (in `nodes.py`)
Edges: `EntityEdge`, `EpisodicEdge`, `CommunityEdge`, `HasEpisodeEdge`, `NextEpisodeEdge` (in `edges.py`)

## Contracts

- Modules use ruff: 100-char lines, single quotes, rules E/F/UP/B/SIM/I
- `typing.TypedDict` is banned — use `typing_extensions.TypedDict` (Pydantic on Python <3.12)
- Integration tests use `_int` suffix and `@pytest.mark.integration`
- `module_utils` cannot import from outside itself (remote execution boundary)

## Pitfalls

- `make test` disables FalkorDB, Kuzu, Neptune via env vars — only runs Neo4j + unit tests
- Neptune is force-disabled in test fixtures (`os.environ['DISABLE_NEPTUNE'] = 'True'`)
- Content chunking is density-based (large JSON only), controlled by env vars: `CHUNK_TOKEN_SIZE`, `CHUNK_DENSITY_THRESHOLD`
- Namespace accessors (`graphiti.nodes.entity`) wrap driver operations with embedding generation — preferred API for CRUD

## Downlinks

| Area | Node |
|------|------|
| Core package | `graphiti_core/AGENTS.md` |
| Driver system | `graphiti_core/driver/AGENTS.md` |
| Search pipeline | `graphiti_core/search/AGENTS.md` |
| LLM client | `graphiti_core/llm_client/AGENTS.md` |
| Namespaces | `graphiti_core/namespaces/AGENTS.md` |
| Utils & maintenance | `graphiti_core/utils/AGENTS.md` |
| MCP server | `mcp_server/AGENTS.md` |
| Tests | `tests/AGENTS.md` |
| Server | `server/AGENTS.md` |

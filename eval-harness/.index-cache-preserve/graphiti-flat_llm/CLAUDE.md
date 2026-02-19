# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Graphiti (`graphiti-core`) is a Python framework for building temporally-aware knowledge graphs for AI agents. Instead of static RAG, it continuously ingests "episodes" (messages, JSON, text), extracts entities and relationships via LLMs, and builds a queryable graph that tracks when facts were valid. Built by Zep Software.

## Testing

Run only the specific test file relevant to the bug, not the full test suite. For example:

```bash
uv run pytest tests/test_specific_file.py -x --tb=short
uv run pytest tests/test_specific_file.py::test_method_name
```

Environment variables needed for unit tests: `DISABLE_NEPTUNE=1 DISABLE_NEO4J=1 DISABLE_FALKORDB=1 DISABLE_KUZU=1`

## Architecture

### Episode ingestion pipeline

The core workflow — `Graphiti.add_episode()` — runs this pipeline:

1. Retrieve recent episodes for context
2. Extract entity nodes via LLM (`extract_nodes()`)
3. Resolve/deduplicate against existing graph nodes (`resolve_extracted_nodes()`)
4. Extract relationship edges via LLM (`extract_edges()`)
5. Resolve/deduplicate edges (`resolve_extracted_edges()`)
6. Generate embeddings for new nodes and edges
7. Save everything to the graph database
8. Optionally update community clusters

Batch variant: `add_episode_bulk()` processes multiple episodes with cross-episode deduplication.

### Key abstractions

**`Graphiti`** (`graphiti.py`) — main entry point. Constructor takes optional `graph_driver`, `llm_client`, `embedder`, `cross_encoder`, `tracer`. Defaults to Neo4j + OpenAI.

**`GraphitiClients`** (`graphiti_types.py`) — Pydantic model bundling `driver + llm_client + embedder + cross_encoder + tracer`. Passed as a single object through internal functions instead of threading individual clients.

**`GraphDriver`** (`driver/driver.py`) — ABC for graph database backends. Four implementations: `Neo4jDriver`, `FalkorDriver`, `KuzuDriver`, `NeptuneDriver`. Each provides `ops` properties (e.g., `driver.entity_node_ops`, `driver.search_ops`) implementing abstract operation interfaces from `driver/operations/`.

**Namespace accessors** — `graphiti.nodes.entity`, `graphiti.edges.entity`, etc. are typed namespace objects that wrap driver operations with embedding generation. Preferred API for direct node/edge CRUD (e.g., `graphiti.nodes.entity.save(node)`).

**`group_id`** — partition key on every node and edge. Different users/agents get isolated graphs by using different group IDs. Maps to database name in Neo4j/FalkorDB, property filter in Kuzu.

### Driver operations architecture (v0.28.0)

```
driver/
├── driver.py                    # GraphDriver ABC, GraphProvider enum
├── operations/                  # Abstract operation interfaces
│   ├── entity_node_ops.py       # EntityNodeOperations ABC
│   ├── entity_edge_ops.py       # EntityEdgeOperations ABC
│   ├── search_ops.py            # SearchOperations ABC
│   └── ...                      # 11 operation ABCs total
├── neo4j/operations/            # Neo4j implementations
├── falkordb/operations/         # FalkorDB implementations
├── kuzu/operations/             # Kuzu implementations
└── neptune/operations/          # Neptune implementations
```

Each driver instantiates its own implementations of the abstract operation interfaces. The `GraphDriver` base returns `None` from `ops` properties; concrete drivers override with real implementations.

Transactions: `async with driver.transaction() as tx:` — drivers without real transaction support (FalkorDB, Kuzu) get a no-op wrapper where queries execute immediately.

### Search pipeline

`search/search.py` → `search()` function orchestrated by `SearchConfig`.

- **Search methods per layer**: `cosine_similarity`, `bm25`, `bfs` (graph traversal)
- **Rerankers**: `rrf` (Reciprocal Rank Fusion), `mmr` (Maximal Marginal Relevance), `node_distance`, `episode_mentions`, `cross_encoder`
- **Pre-built recipes** in `search_config_recipes.py`: `EDGE_HYBRID_SEARCH_RRF`, `COMBINED_HYBRID_SEARCH_CROSS_ENCODER`, etc.
- Four searchable layers: edges, nodes, episodes, communities — each independently configurable

### LLM client pattern

`LLMClient` ABC (`llm_client/client.py`) features:
- Diskcache for optional response caching
- Tenacity retry (4 attempts, exponential backoff) on rate limits and server errors
- Structured output via Pydantic models appended as JSON schema to prompts
- Two model sizes: `model` (medium, default `gpt-4.1-mini`) and `small_model` (small, default `gpt-4.1-nano`)

### Content chunking

`helpers.py` has density-based chunking — only chunks high-entity-density content (large JSON dumps), leaving prose unchanged. Controlled by env vars: `CHUNK_TOKEN_SIZE`, `CHUNK_DENSITY_THRESHOLD`, `CHUNK_MIN_TOKENS`, `CHUNK_OVERLAP_TOKENS`.

### Graph data model

Nodes: `EntityNode`, `EpisodicNode`, `CommunityNode`, `SagaNode`
Edges: `EntityEdge`, `EpisodicEdge`, `CommunityEdge`, `HasEpisodeEdge`, `NextEpisodeEdge`

All defined in `nodes.py` and `edges.py`. `EpisodeType` enum: `message`, `json`, `text`.

## Code style

- Ruff: 100-char lines, single quotes, rules E/F/UP/B/SIM/I
- `typing.TypedDict` is banned — use `typing_extensions.TypedDict` (Pydantic requirement on Python <3.12)
- Pyright: `typeCheckingMode = "basic"` for core library, `"standard"` for server
- Python 3.10+ target

## Test infrastructure

- pytest with `pytest-asyncio` (`asyncio_mode = auto`) and `pytest-xdist`
- Integration tests: `@pytest.mark.integration` decorator, filenames use `_int` suffix
- `conftest.py` exports `graph_driver` and `mock_embedder` fixtures (from `tests/helpers_test.py`)
- Driver selection via env vars: `DISABLE_NEO4J`, `DISABLE_FALKORDB`, `DISABLE_KUZU`, `DISABLE_NEPTUNE`
- Neptune is force-disabled in test fixtures (`os.environ['DISABLE_NEPTUNE'] = 'True'`)

## Environment variables

Required: `OPENAI_API_KEY` (or equivalent for your LLM provider)

Database connection: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `FALKORDB_HOST`, `FALKORDB_PORT`

Tuning: `SEMAPHORE_LIMIT` (default 20, controls async concurrency), `USE_PARALLEL_RUNTIME` (Neo4j enterprise only)

Provider keys: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `VOYAGE_API_KEY`

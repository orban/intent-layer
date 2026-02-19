# graphiti_core

> Core Python package: episode ingestion, entity/edge extraction, deduplication, and graph persistence.

## Entry points

- `graphiti.py` — `Graphiti` class is the only public export (`__init__.py` re-exports it). Constructor takes `graph_driver`, `llm_client`, `embedder`, `cross_encoder`, `tracer`.
- `nodes.py` — `Node` (ABC), `EntityNode`, `EpisodicNode`, `CommunityNode`, `SagaNode`. All use Pydantic `BaseModel`.
- `edges.py` — `Edge` (ABC), `EntityEdge`, `EpisodicEdge`, `CommunityEdge`, `HasEpisodeEdge`, `NextEpisodeEdge`.
- `helpers.py` — `semaphore_gather()`, `parse_db_date()`, `lucene_sanitize()`, chunking env vars.

## Module layout

| Module | Purpose |
|--------|---------|
| `graphiti.py` | Orchestration: `add_episode`, `add_episode_bulk`, `search`, `search_`, `add_triplet`, `remove_episode` |
| `nodes.py` / `edges.py` | Data models + per-driver CRUD (save/get/delete dispatch via `match driver.provider`) |
| `helpers.py` | Shared utilities, env-based config (`SEMAPHORE_LIMIT`, `CHUNK_*` vars) |
| `graphiti_types.py` | `GraphitiClients` Pydantic model bundling driver+llm+embedder+cross_encoder+tracer |
| `decorators.py` | `@handle_multiple_group_ids` — auto-iterates over group_ids list |
| `errors.py` | `NodeNotFoundError`, `EdgeNotFoundError`, `GroupIdValidationError` |
| `prompts/` | LLM prompt templates (extract_nodes, extract_edges, dedupe_nodes, dedupe_edges, summarize) |
| `tracer.py` | OpenTelemetry integration, `create_tracer()` |
| `telemetry/` | PostHog-based usage telemetry |

## Contracts

- Every node/edge has `uuid` (str, auto-generated UUID4) and `group_id` (partition key).
- `group_id` must match `^[a-zA-Z0-9_-]+$` or be empty string. FalkorDB default is `"\_"`, others use `""`.
- Driver dispatch uses `match driver.provider` pattern in `save()`/`delete()`. Kuzu stores edges as nodes (`RelatesToNode_`) — special delete logic required.
- `graph_operations_interface` on driver is checked first (try/except `NotImplementedError` fallback) for all CRUD operations.
- `semaphore_gather()` bounds all concurrent coroutines. Default limit is `SEMAPHORE_LIMIT=20` env var.

## Ingestion pipeline

`add_episode()` sequence:
1. Validate entity types, resolve group_id
2. Retrieve previous episodes for context
3. Extract nodes via LLM (`extract_nodes`)
4. Resolve/dedup nodes against existing graph (`resolve_extracted_nodes`)
5. Extract edges via LLM (`extract_edges`)
6. Resolve/dedup edges (`resolve_extracted_edges`)
7. Extract node attributes + summaries (only new edges to avoid duplicating summaries)
8. Save all via `add_nodes_and_edges_bulk` (single transaction)
9. Optionally update communities

`add_episode_bulk()` differs: no edge invalidation, no date extraction. For those, use single `add_episode()`.

## Pitfalls

- `add_episode` episodes must be added sequentially per group_id. Parallel adds to the same group cause race conditions.
- `add_triplet` checks if an edge UUID already exists with different source/target nodes. If so, it generates a new UUID to avoid overwriting unrelated edges.
- FalkorDB fulltext queries need pipe and slash character sanitization (see `lucene_sanitize`).
- Datetime comparison requires UTC normalization. Use `utc_now()` and `ensure_utc()` from `datetime_utils`.
- Neptune stores embeddings as comma-separated strings, requiring `split()/toFloat()` conversion on read.
- Content chunking is density-based, not size-based. Controlled by `CHUNK_TOKEN_SIZE`, `CHUNK_MIN_TOKENS`, `CHUNK_DENSITY_THRESHOLD` env vars.

## Downlinks

| Area | Node |
|------|------|
| Driver system | `graphiti_core/driver/AGENTS.md` |
| LLM clients | `graphiti_core/llm_client/AGENTS.md` |
| Namespaces | `graphiti_core/namespaces/AGENTS.md` |
| Search | `graphiti_core/search/AGENTS.md` |
| Utils | `graphiti_core/utils/AGENTS.md` |

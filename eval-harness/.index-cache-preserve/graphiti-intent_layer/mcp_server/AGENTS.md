# mcp_server

> MCP (Model Context Protocol) server exposing Graphiti as tools for AI agents. Separate package with its own pyproject.toml.

## Entry points

- `main.py` — entry point, calls `graphiti_mcp_server.main()`
- `src/graphiti_mcp_server.py` — FastMCP server definition, all MCP tools, `initialize_server()`, CLI arg parsing
- `config/config.yaml` — YAML-based configuration (providers, models, transport)

## Module layout

| Path | Purpose |
|------|---------|
| `src/graphiti_mcp_server.py` | MCP tool definitions, `GraphitiService` wrapper, server startup |
| `src/config/schema.py` | `GraphitiConfig`, `ServerConfig` Pydantic settings with env var + YAML support |
| `src/models/response_types.py` | `SuccessResponse`, `ErrorResponse`, `FactSearchResponse`, `NodeSearchResponse`, `StatusResponse` |
| `src/models/entity_types.py` | Dynamic entity type model generation |
| `src/services/factories.py` | `LLMClientFactory`, `EmbedderFactory`, `DatabaseDriverFactory` |
| `src/services/queue_service.py` | `QueueService` — per-group_id sequential episode processing |
| `src/utils/formatting.py` | `format_fact_result()` — strips embeddings from edge responses |
| `docker/` | Dockerfiles and compose files for Neo4j and FalkorDB deployments |
| `config/` | YAML configs for different deployment scenarios |

## MCP tools exposed

| Tool | Description |
|------|-------------|
| `add_memory` | Queue an episode for background processing |
| `search_nodes` | Search entity nodes by natural language query |
| `search_memory_facts` | Search entity edges (facts/relationships) |
| `get_entity_edge` | Get a single edge by UUID |
| `get_episodes` | List episodes by group_id |
| `delete_entity_edge` | Delete a single edge |
| `delete_episode` | Delete an episode and its exclusive nodes/edges |
| `clear_graph` | Delete all data for specified group_ids |
| `get_status` | Health check for DB connection |

## Contracts

- `add_memory` is async: returns immediately, processes in background via `QueueService`. Episodes within the same `group_id` are processed sequentially.
- Config resolution order: YAML file -> env vars -> CLI args (CLI wins).
- `SEMAPHORE_LIMIT` (default 10) controls concurrent Graphiti operations. Each episode involves multiple LLM calls.
- Transport options: `stdio` (default for local), `sse` (deprecated), `http` (recommended for deployment, streamable HTTP).
- `/health` endpoint available at all times (returns `{"status": "healthy"}`).

## Pitfalls

- The `graphiti_service` and `queue_service` are module-level globals. All tools check `if graphiti_service is None` before proceeding.
- FalkorDB default group_id is `"\_"` (escaped underscore). Don't confuse with empty string (Neo4j default).
- Docker: FalkorDB Browser UI runs on port 3000 by default when `BROWSER=1`.
- `source` parameter in `add_memory` must be one of `text`, `json`, `message`. Unknown values fall back to `text` with a warning.
- Dependency pinning: `mcp_server` pins its own `graphiti-core` version in pyproject.toml. Version mismatches between the server and core library can cause subtle failures.

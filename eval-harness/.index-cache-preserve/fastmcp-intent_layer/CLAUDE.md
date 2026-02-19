# FastMCP

## Purpose

FastMCP is a Python framework (>=3.10) for building MCP (Model Context Protocol) servers and clients — the ergonomic layer over the low-level `mcp` SDK.

## Code Map

| Path | Purpose |
|------|---------|
| `src/fastmcp/server/server.py` | `FastMCP` class — main server, 2100 lines |
| `src/fastmcp/server/providers/` | Provider chain — how components are sourced |
| `src/fastmcp/server/middleware/` | Request middleware pipeline |
| `src/fastmcp/server/auth/` | Authentication (15+ OAuth providers, proxy, OIDC) |
| `src/fastmcp/server/transforms/` | Component transforms (Namespace, Visibility, etc.) |
| `src/fastmcp/server/tasks/` | Background tasks (SEP-1686, pydocket/Redis) |
| `src/fastmcp/server/http.py` | Starlette ASGI app, StreamableHTTP + SSE |
| `src/fastmcp/server/context.py` | `Context` — injected into handlers via ContextVar |
| `src/fastmcp/client/client.py` | `Client` class — connects to MCP servers |
| `src/fastmcp/client/transports/` | Transport layer (stdio, HTTP, SSE, memory) |
| `src/fastmcp/tools/` | Tool definitions, function parsing, schema gen |
| `src/fastmcp/resources/` | Resources and URI templates |
| `src/fastmcp/prompts/` | Prompt templates |
| `src/fastmcp/cli/` | CLI commands (cyclopts-based) |
| `src/fastmcp/utilities/` | Shared utilities, OpenAPI parser, JSON schema |
| `tests/` | Pytest suite mirroring src structure |

## Build / Test / Run

```bash
uv sync                              # Install dependencies
uv run pytest -n auto                # Full test suite (default timeout: 5s)
uv run prek run --all-files          # Static checks: Ruff + Prettier + ty
```

- `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"` in pytest config
- Integration tests live in `tests/integration_tests/` and are auto-marked; deselect with `-m "not integration"`
- Windows: uses `WindowsSelectorEventLoopPolicy` to avoid ProactorEventLoop crashes
- File sizes enforced by [loq](https://github.com/jlowin/loq) — edit `loq.toml` to raise limits
- CLI entry point: `fastmcp` (maps to `fastmcp.cli:app` via cyclopts)

## Entry Points

| Task | Start here |
|------|-----------|
| Create an MCP server | `src/fastmcp/server/server.py` → `FastMCP` class |
| Add a tool/resource/prompt | `@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()` decorators on `FastMCP` |
| Connect as client | `src/fastmcp/client/client.py` → `Client` class |
| Add auth to a server | `src/fastmcp/server/auth/` — pick a provider from `auth/providers/` |
| Add middleware | Subclass `Middleware` in `src/fastmcp/server/middleware/middleware.py` |
| Mount/compose servers | `FastMCP.mount()` — creates providers with Namespace transforms |
| Run via CLI | `src/fastmcp/cli/cli.py` — cyclopts-based CLI |
| Background tasks | `src/fastmcp/server/tasks/` — requires pydocket + Redis |
| OpenAPI → MCP | `src/fastmcp/server/providers/openapi/` |

## Architecture

### Core Data Model
Four MCP component types flow through the system uniformly:
- **Tools** (`src/fastmcp/tools/`) — callable functions with JSON schema input/output
- **Resources** (`src/fastmcp/resources/`) — data endpoints with URIs; includes Templates for parameterized URIs
- **Prompts** (`src/fastmcp/prompts/`) — templated prompt messages

Each has a base class (`Tool`, `Resource`, `Prompt`) and a `Function*` variant created from decorated Python functions via `__fastmcp__` metadata on the callable.

### Provider Chain (how components are sourced)
`FastMCP` inherits from `Provider` (via `MCPOperationsMixin`). The resolution order:
1. **LocalProvider** — components registered via decorators (`@mcp.tool()`)
2. **Additional providers** — passed via `providers=[]` at construction (queried in registration order)
3. **AggregateProvider** — merges results from all providers

Provider semantics: `get_*` returns `None` to signal "not found" (search continues to next provider); first non-None wins.

### Transform System (component modification)
Transforms modify components in provider chains. Two patterns:
- **List ops**: pure function — receive sequence, return transformed sequence
- **Get ops**: middleware pattern with `call_next` for chaining lookups

Built-in transforms: `Namespace`, `Visibility`, `ToolTransform`, `PromptsAsTools`, `ResourcesAsTools`, `VersionFilter`.

### Middleware Pipeline (request modification)
Middleware operates on MCP requests/responses (not components). Defined in `server/middleware/middleware.py`. Built-in: error handling, logging, rate limiting, caching, timing, authorization, tool injection, ping, dereference, response limiting.

### Transport Layer
- Server: Starlette-based HTTP (`server/http.py`) with StreamableHTTP + SSE; also stdio
- Client: pluggable transports (`client/transports/`) — stdio, HTTP, SSE, memory, config-based

### Auth System
Server auth: `server/auth/` — providers (GitHub, Google, Azure, Auth0, Discord, etc.), OAuth proxy, OIDC proxy, JWT issuer. Client auth: `client/auth/` — OAuth flow, bearer tokens.

### Background Tasks (SEP-1686)
Async tool execution via pydocket (Redis-backed). Only async functions can be tasks (`task=True`). Task state tracked via key-value store with pub/sub notifications.

### Server Mixins
`FastMCP` is composed of three mixins: `LifespanMixin` (lifecycle), `MCPOperationsMixin` (list/get/call components), `TransportMixin` (run/http_app).

## Contracts

- **Four-type symmetry**: features touching MCP components MUST be applied to Tools, Resources, Resource Templates, AND Prompts. Forgetting one type is the #1 source of incomplete features.
- **Provider get_* returns None, not raises**: returning `None` means "not found, keep searching"; raising is an error. `list_*` errors are logged and return empty (graceful degradation).
- **Transforms vs Middleware**: Transforms modify _components_ (observable, used for task registration/tag filtering). Middleware modifies _requests_ (not visible to introspection). Never conflate them.
- **Components own execution**: providers source components; components execute themselves via `run()`/`read()`/`render()`. Providers should NOT execute.
- **ContextVar for request context**: `_current_context` ContextVar holds the `Context` object. Must be properly set before tool/resource execution. Background tasks must snapshot the access token before dispatching (stale context bug).
- **Session isolation**: visibility marks, proxy client state, and auth tokens are per-session. Leaking state across sessions has caused multiple bugs.
- **MCP spec compliance**: error codes must match spec (e.g., -32002 for resource not found). `additionalProperties: false` must be preserved in compressed schemas. Root-level `$ref` in outputSchema must be resolved.
- **Re-exports are intentional**: only `FastMCP`, `Client`, `Context`, `settings` at top-level. Module-specific types import from their submodule.

## Pitfalls

- **Stale request context in proxy handlers**: `StatefulProxyClient` handlers captured the request context at creation time; background operations saw stale context. Fixed by snapshotting access tokens (#3138, #3172).
- **Session visibility leaking**: Visibility marks (enable/disable components) leaked across sessions because they were stored globally. Must be per-session via ContextVar (#3132).
- **OAuth token refresh races**: `get_access_token()` could return stale tokens after refresh. Token storage TTL calculation had off-by-one. Multi-instance deployments need refresh token stored in shared backend (#2505, #2796, #2483).
- **Confused deputy in OAuth proxy**: consent page lacked binding cookie, allowing CSRF. Fixed with consent binding cookie (#3201).
- **CIMD redirect allowlist bypass**: redirect URI validation could be bypassed. Cache revalidation also needed fixing (#3098).
- **compress_schema drops additionalProperties**: schema compression stripped `additionalProperties: false`, breaking MCP validation (#3102).
- **include_tags/exclude_tags silently ignored**: tag filtering in MCPConfig was skipped when no tools matched initial filter (#3186).
- **OpenAPI $defs mutation**: `Tool.from_tool` transforms mutated the shared `$defs` dict. Must deep-copy before transforming (#2493).
- **Content-type header in get_http_headers()**: including it caused HTTP 415 errors on upstream calls (#3104).
- **Client pagination infinite loop**: misbehaving servers returning the same cursor caused infinite loops. Guard with seen-cursor set (#3167).
- **Nested mount routing (3+ levels)**: routing broke for servers mounted more than 2 levels deep (#2586).
- **functools.wraps + Context**: wrapped functions lost the `Context` parameter detection. `create_function_without_params` must modify the signature (#2563).
- **Windows-specific**: use `SelectorEventLoop` (not Proactor); skip `wait_closed()` to avoid socket hang; SQLite locking causes test timeouts (#2368, #2607).
- **Single-element list unwrapping**: tool results containing a single-element list were incorrectly unwrapped to a scalar (#1074).
- **Resource/Prompt refactor reverted twice**: meta support refactors for resources and prompts were each reverted then re-applied — check both `meta` and `_meta` usage carefully (#2598, #2600, #2608-2611).

## Downlinks

| Path | Scope |
|------|-------|
| [`src/fastmcp/server/AGENTS.md`](src/fastmcp/server/AGENTS.md) | Server core: providers, transforms, middleware, auth, tasks, HTTP transport |
| [`src/fastmcp/client/AGENTS.md`](src/fastmcp/client/AGENTS.md) | Client: transports, auth, mixins, session management |
| [`src/fastmcp/tools/AGENTS.md`](src/fastmcp/tools/AGENTS.md) | Tool definitions, function parsing, schema generation, tool transforms |
| [`tests/AGENTS.md`](tests/AGENTS.md) | Test organization, fixtures, patterns |

# Client Module

## Purpose

The `Client` class (`client.py`) connects to MCP servers over pluggable transports. It supports tools, resources, prompts, sampling, elicitation, roots, progress reporting, and background tasks. The class is composed of four mixins: `ClientToolsMixin`, `ClientResourcesMixin`, `ClientPromptsMixin`, `ClientTaskManagementMixin`.

## Code Map

| File/Dir | Role |
|----------|------|
| `client.py` (~700 lines) | `Client` class — session lifecycle, transport management, handler wiring |
| `mixins/tools.py` | `call_tool()`, `list_tools()` — tool operations |
| `mixins/resources.py` | `read_resource()`, `list_resources()` — resource operations |
| `mixins/prompts.py` | `get_prompt()`, `list_prompts()` — prompt operations |
| `mixins/task_management.py` | Task polling, notification handling for background tasks |
| `elicitation.py` | Client-side elicitation handling |
| `logging.py` | Log message handling from server |
| `messages.py` | Message handler protocol |
| `progress.py` | Progress reporting handler |
| `roots.py` | Roots handler (expose filesystem roots to server) |
| `sampling/` | Sampling handlers — Anthropic and OpenAI |
| `tasks.py` | `ToolTask`, `ResourceTask`, `PromptTask` — task wrappers |
| `telemetry.py` | Client-side OpenTelemetry spans |
| `oauth_callback.py` | Local OAuth callback server for client auth flows |

### transports/

| File | Role |
|------|------|
| `__init__.py` | `infer_transport()` — auto-detects transport from connection string |
| `base.py` | `ClientTransport` protocol |
| `stdio.py` | `PythonStdioTransport`, `NodeStdioTransport`, `StdioTransport` |
| `http.py` | `StreamableHttpTransport` — primary HTTP transport |
| `sse.py` | `SSETransport` — legacy SSE transport |
| `memory.py` | `FastMCPTransport` — in-process transport (for testing) |
| `config.py` | `MCPConfigTransport` — multi-server from config file |
| `inference.py` | Transport inference logic |

### auth/

| File | Role |
|------|------|
| `oauth.py` | Full OAuth 2.1 client flow with PKCE |
| `bearer.py` | Simple bearer token auth |

## Entry Points

| Task | Start here |
|------|-----------|
| Connect to a server | `client.py` → `Client` class |
| Add client auth | `auth/oauth.py` or `auth/bearer.py` |
| Custom transport | Subclass `transports/base.py` → `ClientTransport` |
| Handle sampling | `sampling/` → implement `SamplingHandler` |
| Background task polling | `mixins/task_management.py` |

## Key Exports

- `Client` — re-exported at `fastmcp.Client`
- `infer_transport()` — used by CLI and tests
- Transport classes — `StreamableHttpTransport`, `PythonStdioTransport`, etc.

## Contracts

- **Client is an async context manager**: enter via `async with Client(...) as client:` or `client.connect()`. Session is not available until entered.
- **Transport inference**: `infer_transport(target)` parses strings (`http://...` → HTTP, `path/to/server.py` → stdio, etc.) and `FastMCP` instances → `FastMCPTransport`.
- **stdio transport is single-use**: cannot reuse a stdio transport after disconnect. Calling `.connect()` again on a used stdio client logs a warning.
- **OAuth async_auth_flow**: the flow must not hold the MCP SDK's `context.lock` while awaiting. Previous implementations caused deadlocks (#2644).
- **Pagination cursor tracking**: `list_*` methods must track seen cursors to avoid infinite loops from misbehaving servers (#3167).

## Pitfalls

- **Client concurrency**: `Client` context management was refactored to avoid concurrency issues. Multiple concurrent `async with` blocks on the same client instance caused problems (#1054).
- **Proxy client session isolation**: multiple proxy clients sharing a session mixed up responses. Fixed with session isolation (#1083, #1245).
- **HTTP 4xx/5xx hanging**: client would hang on HTTP error responses instead of raising. Transport must propagate errors (#2803).
- **OAuth token stale after refresh**: `get_access_token()` could return the old token even after a successful refresh. Storage must be updated atomically (#2505).
- **OAuth metadata discovery**: client must preserve the full URL path for RFC 8414 metadata discovery, not just the base (#2577, #2533).
- **Azure scope mismatch**: Azure provider requires `offline_access` scope for token refresh. Client validation errors occurred when scope didn't match (#2243, #3001).
- **Timeout not propagating**: timeout setting didn't propagate to proxy clients in multi-server MCPConfig (#2809).
- **FastMCPTransport (memory)**: the in-process transport used for testing creates a real server session. State is shared — mutations in tools are visible across calls.

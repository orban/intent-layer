# Server Module

## Purpose

The server module implements the MCP server side of FastMCP. `FastMCP` (in `server.py`) is the main user-facing class — it composes `LifespanMixin`, `MCPOperationsMixin`, and `TransportMixin` and inherits from `Provider`.

## Code Map

| File/Dir | Role |
|----------|------|
| `server.py` (~2100 lines) | `FastMCP` class: registration decorators, mount(), provider management |
| `context.py` | `Context` object — injected into tool/resource/prompt functions via ContextVar |
| `mixins/mcp_operations.py` | Implements list/get/call for all four component types |
| `mixins/transport.py` | `run()`, `run_http()`, `http_app()` — server startup |
| `mixins/lifespan.py` | Lifecycle management for startup/shutdown hooks |
| `http.py` | Starlette ASGI app construction, StreamableHTTP + SSE endpoints |
| `low_level.py` | `LowLevelServer` wrapping the `mcp` SDK's server |
| `proxy.py` | Deprecated `FastMCPProxy` — use `ProxyProvider` instead |
| `apps.py` | MCP Apps config (CSP, permissions, UI) |
| `elicitation.py` | Server-side elicitation relay for background tasks |
| `event_store.py` | SSE polling support with EventStore |

### providers/

| File | Role |
|------|------|
| `base.py` | `Provider` abstract base — override `_list_*` / `_get_*` methods |
| `local_provider/` | `LocalProvider` — stores components registered via decorators |
| `fastmcp_provider.py` | `FastMCPProvider` — wraps a `FastMCP` instance as a provider (used by mount) |
| `aggregate.py` | `AggregateProvider` — merges multiple providers |
| `proxy.py` | `ProxyProvider` — proxies to remote MCP server via client factory |
| `openapi/` | `OpenAPIProvider` — converts OpenAPI specs to MCP tools |
| `filesystem.py` | `FileSystemProvider` — discovers components from Python files on disk |
| `skills/` | Skill providers (Claude skills, directory-based, vendor) |
| `wrapped_provider.py` | Base for providers that wrap another provider with transforms |

### middleware/

Middleware operates on MCP **requests** (not components). Subclass `Middleware` and override hooks like `on_call_tool`, `on_list_tools`, `on_read_resource`, etc.

| File | Role |
|------|------|
| `middleware.py` | `Middleware` base class, `MiddlewareContext`, pipeline construction |
| `error_handling.py` | Catches exceptions, converts to MCP error responses |
| `logging.py` | Structured logging of MCP operations |
| `rate_limiting.py` | Per-session rate limiting |
| `caching.py` | Response caching (cache key includes mounted server prefix) |
| `authorization.py` | Auth check enforcement |
| `tool_injection.py` | Injects list/read resource/prompt tools for client compatibility |

### auth/

| File | Role |
|------|------|
| `auth.py` | `AuthProvider` protocol, `AuthContext`, `run_auth_checks` |
| `providers/` | 15+ OAuth/OIDC providers (GitHub, Google, Azure, Auth0, etc.) |
| `oauth_proxy/` | Full OAuth proxy server — issues its own tokens, consent page |
| `oidc_proxy.py` | OIDC proxy (lighter than full OAuth proxy) |
| `jwt_issuer.py` | JWT token issuance for OAuth proxy |
| `middleware.py` | `RequireAuthMiddleware` for Starlette |
| `redirect_validation.py` | Validates redirect URIs |
| `ssrf.py` | SSRF protection for OAuth callbacks |

### transforms/

Transforms modify **components** in provider chains. Unlike middleware, transforms are visible to task registration and introspection.

| File | Role |
|------|------|
| `namespace.py` | `Namespace` — prefixes tool/resource names for mounted servers |
| `visibility.py` | `Visibility` — enable/disable components per session |
| `tool_transform.py` | `ToolTransform` — rename, redescribe, filter args on tools |
| `prompts_as_tools.py` | Exposes prompts as callable tools |
| `resources_as_tools.py` | Exposes resources as callable tools |
| `version_filter.py` | Filters components by version |

### tasks/

Background task execution (SEP-1686). Requires `pydocket` (Redis-backed).

| File | Role |
|------|------|
| `config.py` | `TaskConfig`, `TaskMeta`, `TaskMode` |
| `handlers.py` | Task execution handlers |
| `keys.py` | Task key construction/parsing |
| `notifications.py` | Pub/sub notification delivery |
| `elicitation.py` | Elicitation relay for background tasks |

## Entry Points

| Task | Start here |
|------|-----------|
| Create a server | `server.py` → `FastMCP` class |
| Add a custom provider | Subclass `providers/base.py` → `Provider` |
| Add middleware | Subclass `middleware/middleware.py` → `Middleware` |
| Add auth | Pick a provider from `auth/providers/` |
| Mount another server | `FastMCP.mount()` in `server.py` |
| Add a transform | Subclass `transforms/__init__.py` → `Transform` |
| Background tasks | `tasks/config.py` → `TaskConfig` |

## Key Exports Used by Other Modules

- `FastMCP` — main server class (re-exported at `fastmcp.FastMCP`)
- `Context` — request context (re-exported at `fastmcp.Context`)
- `Provider` — base class for custom providers
- `Middleware`, `MiddlewareContext` — middleware system
- `Transform`, `Namespace`, `Visibility`, `ToolTransform` — transform system
- `AuthProvider`, `AuthContext` — auth system

## Contracts

- **Provider resolution order**: LocalProvider first, then additional providers in registration order. Static components (decorators) always win.
- **get_* returns None, never raises for "not found"**: returning None means "I don't have it, keep searching." Raising is an error.
- **list_* errors degrade gracefully**: logged, returns empty. Other providers still contribute.
- **Middleware call_next chain**: each middleware gets `(context, call_next)`. Must call `call_next(context)` to continue the chain.
- **Transform list ops are pure functions**: receive sequence, return sequence. No side effects.
- **Transform get ops use call_next pattern**: must call `call_next(name, version=version)` to delegate.
- **Components execute themselves**: providers source components; `Tool.run()`, `Resource.read()`, `Prompt.render()` do execution.
- **ASGI lifespan must be passed through**: when mounting FastMCP in FastAPI, the ASGI app's lifespan MUST be passed to the parent app. Missing this causes "Task group is not initialized" errors.

## Pitfalls

- **Stale request context in proxy**: `StatefulProxyClient` captured context at creation. Background tasks saw stale access tokens. Always snapshot tokens before dispatching to background (#3138, #3172).
- **Session visibility leaks**: visibility marks stored globally leaked across sessions. Must use per-session ContextVar (#3132).
- **Caching with mounted prefixes**: cache keys must include the mounted server prefix, otherwise different mounted servers share cache entries (#2762).
- **OAuth proxy consent CSRF**: consent page needed binding cookie to prevent confused deputy attacks (#3201).
- **CIMD redirect bypass**: redirect URI allowlist validation had bypass; ensure strict matching (#3098).
- **content-type in get_http_headers()**: including it caused HTTP 415 on upstream calls. Excluded since #3104.
- **Tags ignored without tools**: include_tags/exclude_tags in MCPConfig silently did nothing when no tools matched initial filter (#3186).
- **Docket function name collisions**: multi-mount setups need prefixed Docket function names to avoid collisions (#2575).
- **Race condition with mounted server task results**: tasks from mounted servers could race with result delivery (#2575).
- **on_initialize middleware got wrong params**: was receiving the whole request instead of just params (#2357).

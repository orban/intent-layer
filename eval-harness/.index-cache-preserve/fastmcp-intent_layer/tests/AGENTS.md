# Tests

## Purpose

Pytest-based test suite mirroring the `src/fastmcp/` structure. Uses `pytest-asyncio` (auto mode), `pytest-xdist` for parallel execution, and `inline-snapshot` for snapshot testing.

## Entry Points

| Task | Start here |
|------|-----------|
| Run all tests | `uv run pytest -n auto` |
| Run specific area | `uv run pytest tests/server/` or `tests/tools/` etc. |
| Add a test | Mirror the `src/` path in `tests/`; use `FastMCPTransport` for in-process testing |
| Shared fixtures | `conftest.py` → `fastmcp_server`, `tool_server`, `free_port` |

## Code Map

Same structure as `src/fastmcp/` — each subdirectory corresponds to the source module it tests.

## Structure

| Directory | Tests for |
|-----------|----------|
| `server/` | Server core — context, providers, middleware, auth, transforms, tasks, HTTP, mount, sampling, telemetry |
| `client/` | Client operations, auth, transports, concurrent usage |
| `tools/` | Tool creation, function parsing, schema generation, tool transforms |
| `resources/` | Resource and template creation, URI handling |
| `prompts/` | Prompt creation, argument handling |
| `cli/` | CLI commands — run, install, config, discovery, generate |
| `utilities/` | JSON schema, OpenAPI parsing, async utils |
| `integration_tests/` | Auto-marked with `@pytest.mark.integration`; tests against real servers |
| `contrib/` | Community contrib modules |
| `deprecated/` | Tests for deprecated features (preserved for backwards-compat verification) |
| `telemetry/` | OpenTelemetry tracing tests |

## Key Fixtures (conftest.py)

- **`isolate_settings_home`** (autouse): each test gets isolated `settings.home` in `tmp_path` — prevents file locking issues from shared OAuth storage
- **`enable_fastmcp_logger_propagation`** (autouse): enables FastMCP logger propagation so `caplog` captures log messages (FastMCP loggers have `propagate=False` by default)
- **`import_rich_rule`** (autouse): pre-imports `rich.rule` to avoid import timing issues
- **`fastmcp_server`**: creates a standard `FastMCP` with tools, resources, prompts for reuse
- **`tool_server`**: comprehensive tool set for provider tests (images, audio, files, mixed content, errors)
- **`tagged_resources_server`**: server with tagged resources/templates
- **`free_port` / `free_port_factory`**: allocates free TCP ports for HTTP server tests
- **`otel_trace_provider` / `trace_exporter`**: session-scoped OpenTelemetry tracing for test spans

## Config

- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed
- `asyncio_default_fixture_loop_scope = "function"` — fresh event loop per test
- Default timeout: **5 seconds** — keep tests fast; use `@pytest.mark.timeout(30)` for slower tests
- `FASTMCP_TEST_MODE=1` env var set in all tests
- `addopts = ["--inline-snapshot=disable"]` — snapshots disabled by default; enable with `--inline-snapshot=update`
- Unawaited coroutine warnings are treated as errors

## Contracts

- **Test isolation**: each test gets its own `settings.home` directory. Don't share state between tests via the filesystem.
- **No subprocess-based servers in unit tests**: replaced with in-process async servers (#2006). Use `FastMCPTransport` for testing.
- **Integration tests are separate**: anything in `tests/integration_tests/` is auto-marked and excluded from default runs.
- **Windows compatibility**: `SelectorEventLoop` is forced on Windows. Some tests are skipped on Windows due to platform differences.

## Pitfalls

- **Shared FakeServer state**: tests using `FakeServer` must create a fresh instance per test to prevent shared state issues (#2540).
- **Docket strike monitoring**: disable Docket strike monitoring in tests using `fakeredis` to avoid busy-loops (#2540).
- **caplog not capturing**: FastMCP loggers have `propagate=False`. The `enable_fastmcp_logger_propagation` fixture handles this, but if you create a new logger in test code, ensure it propagates.
- **OAuth proxy file locking**: tests that use OAuth proxy must use `MemoryStore` (not disk) to avoid SQLite locking issues on Windows (#2368, #3123).
- **OTel TracerProvider can only be set once**: `otel_trace_provider` is session-scoped for this reason. Don't create new providers in test functions.
- **Port conflicts**: use `free_port` fixture instead of hardcoded ports. The `--reload` flag had port conflict issues with explicit ports (#3070).
- **inline-snapshot serialization**: MCP SDK version changes can alter snapshot serialization (e.g., field ordering). Update snapshots with `--inline-snapshot=update`.

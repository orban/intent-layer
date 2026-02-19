# Server

FastAPI REST service exposing Graphiti functionality.

## Development

```bash
cd server/
uv sync --extra dev
uvicorn graph_service.main:app --reload
make format / make lint / make test
```

## Architecture

- `graph_service/main.py` — FastAPI app entry point
- Separate pyproject.toml and dev dependencies from the core library
- Wraps `Graphiti` client for HTTP access

## Contracts

- Pyright `typeCheckingMode = "standard"` (stricter than core library's `"basic"`)
- Has its own test suite separate from the core library

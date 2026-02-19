# tests

> Test suite for graphiti_core. Mix of unit tests, mock-based tests, and integration tests requiring live databases.

## Entry points

- `test_graphiti_mock.py` — largest test file (65k), comprehensive mock-based tests of the full pipeline
- `test_graphiti_int.py` — integration test for end-to-end episode ingestion
- `test_add_triplet.py` — tests for `add_triplet()` flow

## Test organization

| Path | Type | What it tests |
|------|------|---------------|
| `test_graphiti_mock.py` | Unit (mocked) | Full pipeline: add_episode, add_episode_bulk, search, add_triplet, remove_episode |
| `test_graphiti_int.py` | Integration | End-to-end with live DB |
| `test_add_triplet.py` | Unit + Integration | Triplet creation, dedup, edge resolution |
| `test_edge_int.py` | Integration | Edge CRUD operations per driver |
| `test_node_int.py` | Integration | Node CRUD operations per driver |
| `test_entity_exclusion_int.py` | Integration | Entity type exclusion filtering |
| `test_text_utils.py` | Unit | Text truncation utilities |
| `helpers_test.py` | Unit | `semaphore_gather`, `validate_group_id`, `lucene_sanitize` |
| `llm_client/` | Unit | Per-provider LLM client tests (OpenAI, Anthropic, Gemini, Groq, Azure) |
| `embedder/` | Unit | Per-provider embedder tests (OpenAI, Gemini, Voyage) |
| `driver/` | Unit | FalkorDB driver tests |
| `cross_encoder/` | Unit | BGE reranker, Gemini reranker |
| `utils/` | Unit | Content chunking, maintenance operations |
| `evals/` | Evaluation | LongMemEval benchmark (large JSON data file in `evals/data/`) |

## Running tests

```bash
# Unit tests only (disable all DB drivers)
DISABLE_NEPTUNE=1 DISABLE_NEO4J=1 DISABLE_FALKORDB=1 DISABLE_KUZU=1 uv run pytest tests/ -x --tb=short

# Single test file
uv run pytest tests/test_graphiti_mock.py -x

# Integration tests (need live Neo4j)
uv run pytest tests/test_graphiti_int.py -x --tb=short
```

## Contracts

- Integration tests use `_int` suffix in filename and `@pytest.mark.integration` decorator.
- Tests separated into unit, database, and API integration categories (see commit `e72f810`).
- `evals/data/longmemeval_data/longmemeval_oracle.json` is ~3.8M tokens. Don't try to read or process it in normal test runs.

## Pitfalls

- `make test` disables FalkorDB, Kuzu, Neptune via env vars. Only runs Neo4j + pure unit tests.
- Neptune is force-disabled in test fixtures (`os.environ['DISABLE_NEPTUNE'] = 'True'`).
- Mock tests patch at the module level where functions are imported, not where they're defined. Watch import paths.
- FalkorDB driver tests need a running FalkorDB instance (default port 6379).

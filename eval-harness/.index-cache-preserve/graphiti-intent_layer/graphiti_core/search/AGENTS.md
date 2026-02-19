# Search Pipeline

Hybrid search across four graph layers with configurable reranking.

## Architecture

`search/search.py` → `search()` orchestrated by `SearchConfig`.

Four searchable layers: edges, nodes, episodes, communities — each independently configurable.

### Search methods (per layer)
- `cosine_similarity` — embedding-based
- `bm25` — text-based
- `bfs` — graph traversal

### Rerankers
- `rrf` — Reciprocal Rank Fusion
- `mmr` — Maximal Marginal Relevance
- `node_distance` — graph proximity
- `episode_mentions` — recency weighting
- `cross_encoder` — ML reranking

### Pre-built recipes

`search_config_recipes.py` has ready-made configs: `EDGE_HYBRID_SEARCH_RRF`, `COMBINED_HYBRID_SEARCH_CROSS_ENCODER`, etc.

## Contracts

- Search configs specify methods and rerankers per layer
- Results are unified across layers before final reranking
- `cross_encoder` reranker requires a `CrossEncoderClient` in `GraphitiClients`

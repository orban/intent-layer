# graphiti_core/utils

> Maintenance operations, content chunking, bulk graph operations, and deduplication logic.

## Entry points

- `maintenance/` — node extraction, edge extraction, dedup, community ops, graph data ops
- `bulk_utils.py` — `RawEpisode`, `add_nodes_and_edges_bulk`, `dedupe_nodes_bulk`, `dedupe_edges_bulk`, `extract_nodes_and_edges_bulk`
- `content_chunking.py` — density-based chunking for JSON, text, and message content

## Module layout

| File | Purpose |
|------|---------|
| `maintenance/node_operations.py` | `extract_nodes()`, `resolve_extracted_nodes()`, `extract_attributes_from_nodes()` |
| `maintenance/edge_operations.py` | `extract_edges()`, `resolve_extracted_edges()`, `resolve_extracted_edge()`, `build_episodic_edges()` |
| `maintenance/community_operations.py` | `build_communities()`, `remove_communities()`, `update_community()` |
| `maintenance/graph_data_operations.py` | `retrieve_episodes()`, `clear_data()`, `EPISODE_WINDOW_LEN` |
| `maintenance/dedup_helpers.py` | `_build_candidate_indexes()`, `_resolve_with_similarity()`, MinHash + Jaccard similarity |
| `bulk_utils.py` | Bulk save/extract/dedup with transaction support, union-find for UUID map compression |
| `content_chunking.py` | `should_chunk()`, `chunk_json_content()`, `chunk_text_content()`, `chunk_message_content()`, `generate_covering_chunks()` |
| `datetime_utils.py` | `utc_now()`, `ensure_utc()`, `convert_datetimes_to_strings()` |
| `text_utils.py` | `truncate_at_sentence()`, `MAX_SUMMARY_CHARS` |
| `ontology_utils/entity_types_utils.py` | `validate_entity_types()` — checks Pydantic model constraints |

## Contracts

- `maintenance/__init__.py` exports: `extract_edges`, `build_episodic_edges`, `extract_nodes`, `clear_data`, `retrieve_episodes`
- Bulk operations use `GraphDriverSession.execute_write()` for transactional saves. Kuzu falls back to one-by-one inserts (no `UNWIND` support for `STRUCT[]`).
- `dedupe_nodes_bulk` runs a two-pass strategy: (1) resolve each episode against the live graph in parallel, (2) cross-dedupe the batch using deterministic similarity heuristics + union-find.
- Union-find for UUID maps uses directed path compression: `_build_directed_uuid_map()` in `bulk_utils.py`.

## Chunking behavior

Content is only chunked when **both** conditions hold:
1. Token count >= `CHUNK_MIN_TOKENS` (default 1000)
2. Entity density exceeds `CHUNK_DENSITY_THRESHOLD` (default 0.15)

JSON density = elements per 1000 tokens. Text density = capitalized words per 1000 tokens (half the threshold).

`generate_covering_chunks()` solves the Handshake Flights / Covering Design problem: given N items and chunk size K, greedily selects chunks to cover all pairs. Falls back to random sampling when C(n,k) > 1000.

## Pitfalls

- `dedupe_nodes_bulk` rebuilds the MinHash candidate index for each new node against the canonical pool. O(n^2) in batch size. Fine for typical batches (<=10) but would need incremental indexing for larger ones.
- `add_nodes_and_edges_bulk_tx` generates embeddings inline if missing. This means embedding generation happens inside the DB transaction on Kuzu.
- Edge dedup uses word-overlap + cosine similarity (min 0.6) as a pre-filter before LLM resolution. Edges between different node pairs are never compared.
- `clear_data()` deletes by group_id. Calling without group_ids deletes everything in the database.

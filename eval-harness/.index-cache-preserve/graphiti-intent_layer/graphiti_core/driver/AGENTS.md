# Driver System

Graph database abstraction layer with four backends.

## Architecture

`GraphDriver` (ABC in `driver.py`) defines abstract `ops` properties returning operation interfaces. Each backend implements all 11 operation ABCs.

```
driver.py                    # GraphDriver ABC, GraphProvider enum
operations/                  # Abstract operation interfaces (11 ABCs)
  entity_node_ops.py         # EntityNodeOperations
  entity_edge_ops.py         # EntityEdgeOperations
  search_ops.py              # SearchOperations
  ...
neo4j/operations/            # Neo4j implementations
falkordb/operations/         # FalkorDB implementations
kuzu/operations/             # Kuzu implementations
neptune/operations/          # Neptune implementations
```

## Contracts

- `GraphDriver` base returns `None` from `ops` properties — concrete drivers override
- Transactions: `async with driver.transaction() as tx:` — FalkorDB and Kuzu get no-op wrappers where queries execute immediately
- Each driver instantiates its own operation implementations

## Pitfalls

- Neo4j `USE_PARALLEL_RUNTIME` env var only works with Neo4j Enterprise — causes errors on Community Edition
- FalkorDB and Kuzu lack real transaction support — the `transaction()` context manager is a no-op
- Neptune requires AWS credentials and specific IAM permissions, not just host/port

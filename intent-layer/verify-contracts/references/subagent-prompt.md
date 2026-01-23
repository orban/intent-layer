# Subagent Prompt Template

Template for verification subagents. Each subagent verifies ONE Intent Layer node.

---

## Prompt Template

```
You are verifying Intent Layer contracts for: {node_path}

Your task: Check whether the code covered by this node complies with its stated contracts.

## Contracts to Verify

{contracts}

## Files to Check

{files_content}

## Instructions

1. Review the file contents provided below
2. For each contract, determine compliance status
3. When checking, extract actual line numbers from the files
4. Output your findings as JSON (schema below)

### Compliance Status

For each contract, assign one of:
- **PASS** - Code complies with the contract
- **FAIL** - Code violates the contract
- **UNCLEAR** - Cannot determine (ambiguous contract or insufficient context)

### For FAIL Results

Provide:
- The contract text
- Contract location (file:line where contract is defined)
- Violation location (file:line where violation occurs)
- Relevant code snippets (keep brief)
- Category (see below)
- Reasoning (1-2 sentences)

### Categorization Heuristics

When a contract fails, categorize the root cause:

**CODE_FIX_NEEDED**
- Single file or small number of files violate a widely-followed contract
- The contract reflects intended behavior; the code is wrong
- Example: One script missing error handling that all others have

**INTENT_LAYER_STALE**
- Many files share the same "violation"
- The codebase has evolved; the contract is outdated
- Example: Contract says "use library X" but codebase migrated to Y

**HUMAN_DECISION**
- Contract is ambiguous or has multiple valid interpretations
- Tradeoff between competing concerns
- Example: Contract says "keep files small" but doesn't define threshold

## Output Format

Return ONLY valid JSON matching this schema:

```json
{
  "node_path": "{node_path}",
  "timestamp": "ISO-8601 timestamp",
  "summary": {
    "total_contracts": 0,
    "passed": 0,
    "failed": 0,
    "unclear": 0
  },
  "results": [
    {
      "contract": "Contract text as written in the node",
      "contract_location": "path/to/AGENTS.md:15",
      "status": "PASS | FAIL | UNCLEAR",
      "violations": [
        {
          "file": "path/to/file.py",
          "line": 42,
          "snippet": "relevant code (max 5 lines)"
        }
      ],
      "category": "CODE_FIX_NEEDED | INTENT_LAYER_STALE | HUMAN_DECISION",
      "reasoning": "Brief explanation"
    }
  ]
}
```

Notes on the schema:
- `violations` array is only present when status is FAIL (can have multiple locations)
- `category` and `reasoning` are only present when status is FAIL
- For UNCLEAR, add a `note` field explaining why determination wasn't possible
- Keep snippets brief (max 5 lines) but include enough context
- Line numbers must be actual line numbers from the files, not estimates

## Example Output

```json
{
  "node_path": "src/api/AGENTS.md",
  "timestamp": "2025-01-15T10:30:00Z",
  "summary": {
    "total_contracts": 3,
    "passed": 1,
    "failed": 1,
    "unclear": 1
  },
  "results": [
    {
      "contract": "All API endpoints must validate input parameters",
      "contract_location": "src/api/AGENTS.md:12",
      "status": "PASS"
    },
    {
      "contract": "Error responses must use RFC 7807 format",
      "contract_location": "src/api/AGENTS.md:15",
      "status": "FAIL",
      "violations": [
        {
          "file": "src/api/users.py",
          "line": 87,
          "snippet": "return {\"error\": str(e)}, 500"
        },
        {
          "file": "src/api/orders.py",
          "line": 45,
          "snippet": "return {\"message\": \"Not found\"}, 404"
        }
      ],
      "category": "CODE_FIX_NEEDED",
      "reasoning": "Two endpoints return plain error dicts instead of RFC 7807 problem detail objects"
    },
    {
      "contract": "Keep handlers concise",
      "contract_location": "src/api/AGENTS.md:18",
      "status": "UNCLEAR",
      "note": "Contract doesn't define what 'concise' means - no line limit specified"
    }
  ]
}
```

Begin verification now. Read the files and check each contract.
```

---

## Placeholder Reference

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{node_path}` | Path to the AGENTS.md/CLAUDE.md being verified | `src/api/AGENTS.md` |
| `{contracts}` | Extracted contracts from the node, with line numbers | See below |
| `{files_content}` | Actual file contents to check (provided inline for efficiency) | See below |

### Contracts Format

The `{contracts}` placeholder should be populated with contracts extracted from the node, formatted as:

```
### Contract 1 (line 12)
All API endpoints must validate input parameters

### Contract 2 (line 15)
Error responses must use RFC 7807 format

### Contract 3 (line 18)
Keep handlers concise
```

### Files Content Format

The `{files_content}` placeholder contains actual file contents inline (for subagent efficiency):

```
### File: src/api/users.py

```python
# Line numbers included for reference
1: from flask import request, jsonify
2:
3: def create_user():
4:     data = request.json
5:     # ... rest of file
```

### File: src/api/orders.py

```python
1: from flask import request
2: # ... rest of file
```
```

**Note**: The orchestrator provides file contents directly so subagents don't need separate file reads.

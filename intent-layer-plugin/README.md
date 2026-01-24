# Intent Layer Plugin

A Claude Code plugin implementing a continuous learning loop that captures mistakes and injects learnings into agent workflows.

## Features

### Capture Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `capture-tool-failure` | PostToolUseFailure | Suggests `capture_mistake.sh` on Edit/Write/Bash failures |
| Stop prompt | Stop | LLM evaluates session for learnings, blocks if found |

### Feedback Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `inject-learnings` | SessionStart | Injects recent accepted mistakes (7-day window) |
| `pre-edit-check` | PreToolUse | Injects Pitfalls from covering AGENTS.md |

### Adaptive Behavior

The PreToolUse hook uses **adaptive gating** based on mistake history:
- **Quiet mode** (0-1 previous mistakes): Informational pitfalls display
- **Gated mode** (2+ previous mistakes): Strong warning requiring review

## Installation

```bash
claude plugin install ./intent-layer-plugin
```

## Requirements

- `jq` for JSON parsing (`brew install jq` or `apt install jq`)
- The `intent-layer` skill for `capture_mistake.sh`

## Directory Structure

```
intent-layer-plugin/
├── .claude-plugin/plugin.json
├── hooks/
│   ├── hooks.json           # Hook registration (official format)
│   └── scripts/
│       ├── capture-tool-failure.sh
│       ├── inject-learnings.sh
│       └── pre-edit-check.sh
├── lib/
│   ├── common.sh
│   ├── aggregate_learnings.sh
│   ├── find_covering_node.sh
│   └── check_mistake_history.sh
└── tests/test_hooks.sh
```

## How It Works

```
Agent encounters unexpected failure
    ↓
PostToolUseFailure hook suggests capture_mistake.sh
    ↓
Mistake report created in .intent-layer/mistakes/pending/
    ↓
Human reviews → moves to accepted/ or rejected/
    ↓
Human updates AGENTS.md with check/pitfall
    ↓
Next session: SessionStart injects recent learnings
    ↓
Agent edits file: PreToolUse injects relevant pitfalls
```

## Testing

```bash
./tests/test_hooks.sh
```

## Configuration

- Risk threshold: Edit `check_mistake_history.sh` `--threshold N` (default: 2)
- Learnings window: Edit `aggregate_learnings.sh` `--days N` (default: 7)

## Documentation Reference

https://code.claude.com/docs/en/hooks

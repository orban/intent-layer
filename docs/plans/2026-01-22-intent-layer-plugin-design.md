# Intent Layer Plugin Design

> Convert intent-layer skills to a Claude Code plugin with hooks and agents.

## Goals

- **Integration**: Add hooks and agents beyond pure skills
- **Automation**: PostToolUse hook flags files covered by Intent Layer
- **Analysis**: Specialized agents for exploration, validation, auditing

## Plugin Structure

```
intent-layer-plugin/
├── .claude-plugin/
│   ├── plugin.json          # Manifest (name, version, author)
│   └── marketplace.json     # For distribution (optional)
├── skills/
│   ├── intent-layer/        # Main setup skill
│   ├── intent-layer-maintenance/
│   ├── intent-layer-query/
│   └── intent-layer-onboarding/
├── agents/
│   ├── explorer/            # Analyzes directories, proposes nodes
│   ├── validator/           # Deep validation against codebase
│   └── auditor/             # Drift detection, staleness check
├── hooks/
│   └── post-edit-check/     # PostToolUse hook for Edit/Write
├── scripts/                 # Existing bash scripts (shared)
└── references/              # Templates, protocols (shared)
```

## Hook: post-edit-check

**Trigger**: PostToolUse on Edit/Write tools

**Logic**:
1. Find covering node - walk up from edited file until AGENTS.md found
2. Quick relevance check - did edit touch contracts/entry points/patterns?
3. If relevant - output reminder with node path and sections to review
4. If not relevant - silent (no output = no interruption)

**Performance**: Must complete in <500ms (only flags, doesn't analyze)

**Output format**:
```
ℹ️ Intent Layer: src/api/handlers/auth.ts is covered by src/api/AGENTS.md
   Sections to review if behavior changed: Contracts, Pitfalls
```

## Agents

### Explorer (`intent-layer:explorer`)

**Purpose**: Analyze a directory and propose AGENTS.md content.

**When invoked**: Setting up new nodes, or when directory flagged as needing coverage.

**Capabilities**:
- Reads code to extract contracts, patterns, entry points
- Mines git history for pitfalls (integrates git-history sub-skill logic)
- Proposes structured AGENTS.md draft using templates
- Identifies cross-cutting concerns for LCA placement

**Output**: Draft AGENTS.md content + confidence scores per section.

### Validator (`intent-layer:validator`)

**Purpose**: Deep validation that a node accurately reflects its codebase.

**When invoked**: After creating/updating nodes, or as part of PR review.

**Capabilities**:
- Compares documented contracts against actual code enforcement
- Verifies entry points still exist and are accurate
- Checks that documented patterns are actually followed
- Flags undocumented patterns that appear frequently

**Output**: Validation report with PASS/WARN/FAIL per section.

### Auditor (`intent-layer:auditor`)

**Purpose**: Find drift between nodes and current code state.

**When invoked**: Quarterly maintenance, post-merge, or when hook accumulates flags.

**Capabilities**:
- Runs validator across all nodes in parallel
- Compares node timestamps vs code change timestamps
- Identifies stale sections (code changed but node didn't)
- Prioritizes findings by impact (contracts > pitfalls > patterns)

**Output**: Prioritized list of nodes needing updates + specific sections.

## Integration Flow

```
DURING NORMAL WORK:
  Edit file → [Hook] finds covering AGENTS.md → Outputs reminder → Work continues

ON DEMAND / SCHEDULED:
  "Check Intent Layer" → [Auditor] runs → spawns [Validator] per node → Returns findings

NEW AREA SETUP:
  "Add to src/payments/" → [Explorer] analyzes → proposes draft → [Validator] checks → User approves
```

**Principle**: Hooks inform (passive), agents analyze (active), skills guide (interactive).

## Migration Steps

1. Create `intent-layer-plugin/` directory
2. Create `.claude-plugin/plugin.json` manifest
3. Move skills to `skills/` (update internal paths)
4. Move scripts/references to plugin root
5. Create agent AGENT.md files in `agents/`
6. Create hook files in `hooks/`
7. Test with `claude plugin install ./intent-layer-plugin`
8. Remove old symlinks from `~/.claude/skills/`

## Out of Scope (v1)

- MCP tools (bash scripts sufficient)
- PreToolUse hooks ("read first" warnings)
- Stop hook for session summaries
- CI/CD integration scripts
- Web dashboard or visualization

## Future Possibilities

- `intent-layer:chat` agent for codebase Q&A
- Automatic PR comments via GitHub MCP
- Token budget tracking across nodes

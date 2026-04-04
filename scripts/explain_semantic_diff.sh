#!/usr/bin/env bash
# Explain the semantic meaning of code changes for affected Intent Nodes.
# Usage: ./explain_semantic_diff.sh [base_ref] [head_ref] [options]

set -euo pipefail

MODEL="claude-haiku-4-5-20251001"
MAX_DIFF_CHARS=12000
MAX_RETRIES=3
SENSITIVE_PATTERNS='(^|/)\.env($|\.)|credentials\.json$|\.pem$|\.key$|\.secret$'

show_help() {
    cat << 'EOF'
explain_semantic_diff.sh - Explain the semantic meaning of code changes

USAGE:
    explain_semantic_diff.sh [OPTIONS] [BASE_REF] [HEAD_REF]

ARGUMENTS:
    BASE_REF    Git ref to compare from (default: uncommitted changes)
    HEAD_REF    Git ref to compare to (default: HEAD)

OPTIONS:
    --dry-run    Show affected nodes and scoped files without semantic analysis
    -h, --help   Show this help message

MODES:
    No arguments:           Analyze uncommitted changes (staged + unstaged)
    BASE_REF only:          Compare BASE_REF to HEAD
    BASE_REF and HEAD_REF:  Compare BASE_REF to HEAD_REF

OUTPUT:
    Structured semantic explanations per affected Intent Node covering:
    - behavioral impact
    - contract changes
    - likely internal-only changes
    - review focus

AI SUPPORT:
    With ANTHROPIC_API_KEY set, the script asks Claude for richer semantic
    summaries after filtering sensitive files. Without a key, it falls back
    to local heuristics so the command remains useful offline.

EXAMPLES:
    explain_semantic_diff.sh
    explain_semantic_diff.sh main HEAD
    explain_semantic_diff.sh HEAD~5 HEAD
    explain_semantic_diff.sh --dry-run main HEAD
EOF
    exit 0
}

DRY_RUN=false
POSITIONAL=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        --dry-run) DRY_RUN=true; shift ;;
        -*) echo "Error: Unknown option: $1" >&2; echo "Run with --help for usage." >&2; exit 1 ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done

BASE_REF="${POSITIONAL[0]:-}"
HEAD_REF="${POSITIONAL[1]:-HEAD}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIND_COVERING_NODE="$SCRIPT_DIR/../lib/find_covering_node.sh"

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Error: Not in a git repository." >&2
    exit 1
}

cd "$REPO_ROOT"

if [[ -n "$BASE_REF" ]] && ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    echo "Error: Invalid git ref: $BASE_REF" >&2
    echo "Check that the branch/tag/commit exists." >&2
    exit 1
fi

if [[ -n "$BASE_REF" ]] && ! git rev-parse --verify "$HEAD_REF" >/dev/null 2>&1; then
    echo "Error: Invalid git ref: $HEAD_REF" >&2
    echo "Check that the branch/tag/commit exists." >&2
    exit 1
fi

if [[ ! -x "$FIND_COVERING_NODE" ]]; then
    echo "Error: find_covering_node.sh not found at $FIND_COVERING_NODE" >&2
    exit 1
fi

is_intent_node() {
    local path="$1"
    [[ "$path" == "AGENTS.md" || "$path" == "CLAUDE.md" || "$path" == */AGENTS.md || "$path" == */CLAUDE.md ]]
}

is_test_file() {
    local path="$1"
    [[ "$path" == tests/* || "$path" == *"/tests/"* || "$path" == test/* || "$path" == *"_test."* || "$path" == *".spec."* || "$path" == *".test."* ]]
}

is_doc_file() {
    local path="$1"
    [[ "$path" == *.md || "$path" == docs/* || "$path" == references/* ]]
}

is_config_file() {
    local path="$1"
    [[ "$path" == *.json || "$path" == *.yaml || "$path" == *.yml || "$path" == *.toml || "$path" == *.ini || "$path" == *.cfg || "$path" == *.conf || "$path" == *.lock ]]
}

is_internal_artifact_file() {
    local path="$1"
    [[ "$path" == .intent-layer/* || "$path" == *.log ]]
}

is_sensitive_file() {
    local path="$1"
    [[ "$path" =~ $SENSITIVE_PATTERNS ]]
}

is_contract_file() {
    local path="$1"
    [[ "$path" == *"/api/"* || "$path" == *"/schema/"* || "$path" == *"/schemas/"* || "$path" == *"/types/"* || "$path" == *"/contracts/"* || "$path" == *"/interface"* || "$path" == *".proto" || "$path" == *".graphql" || "$path" == *".avsc" ]]
}

get_changed_files() {
    if [[ -z "$BASE_REF" ]]; then
        {
            git diff --name-only 2>/dev/null || true
            git diff --name-only --cached 2>/dev/null || true
        } | awk 'NF' | sort -u
    else
        git diff --name-only "$BASE_REF" "$HEAD_REF" 2>/dev/null
    fi
}

get_file_numstat() {
    local path="$1"
    local output

    if [[ -z "$BASE_REF" ]]; then
        output=$({
            git diff --numstat -- "$path" 2>/dev/null || true
            git diff --cached --numstat -- "$path" 2>/dev/null || true
        } | awk -v target="$path" '$3 == target {add += $1; del += $2} END {printf "%s %s\n", add + 0, del + 0}')
    else
        output=$(git diff --numstat "$BASE_REF" "$HEAD_REF" -- "$path" 2>/dev/null | awk -v target="$path" '$3 == target {add += $1; del += $2} END {printf "%s %s\n", add + 0, del + 0}')
    fi

    if [[ -z "$output" ]]; then
        echo "0 0"
    else
        echo "$output"
    fi
}

get_file_diff() {
    local path="$1"
    if [[ -z "$BASE_REF" ]]; then
        {
            git diff -- "$path" 2>/dev/null || true
            git diff --cached -- "$path" 2>/dev/null || true
        }
    else
        git diff "$BASE_REF" "$HEAD_REF" -- "$path" 2>/dev/null || true
    fi
}

extract_entry_points() {
    local node="$1"
    awk '
        /^## / {
            if (in_section) exit
            if ($0 == "## Entry Points") { in_section=1; next }
        }
        in_section { print }
    ' "$node" | grep -o '`[^`][^`]*`' | tr -d '`' || true
}

filter_sensitive_diff() {
    local diff_text="$1"
    local in_sensitive=false

    while IFS= read -r line; do
        if [[ "$line" == "diff --git"* ]]; then
            in_sensitive=false
            if echo "$line" | grep -Eq "$SENSITIVE_PATTERNS"; then
                in_sensitive=true
            fi
        fi
        if ! $in_sensitive; then
            printf '%s\n' "$line"
        fi
    done <<< "$diff_text"
}

sanitize_for_jq() {
    printf '%s' "$1"
}

call_haiku() {
    local node="$1"
    local node_content="$2"
    local diff_text="$3"

    if ! command -v curl >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
        return 1
    fi

    local prompt
    prompt="Explain the semantic meaning of this git diff for an Intent Layer node.

Node file: $node

Current node content:
---
$node_content
---

Scoped git diff:
---
$diff_text
---

Return exactly one JSON object with this shape:
{
  \"summary\": \"one sentence\",
  \"behavior_change\": \"what user-visible behavior or runtime semantics changed; say 'No material behavioral change detected.' if none\",
  \"contract_change\": \"what interfaces, invariants, inputs/outputs, or expectations changed; say 'No contract change detected.' if none\",
  \"internal_only\": \"what looks internal-only or low-risk; say 'No clear internal-only signal.' if not confident\",
  \"review_focus\": [\"short review item\", \"short review item\"],
  \"confidence\": \"high|medium|low\"
}

Rules:
- Prefer concrete semantic impact over line-by-line narration.
- Distinguish behavior changes from pure refactors.
- Do not mention secrets or include sensitive file contents.
- Keep each string concise."

    local request_body
    request_body=$(jq -n \
        --arg model "$MODEL" \
        --arg user_msg "$prompt" \
        '{
            model: $model,
            max_tokens: 900,
            messages: [{role: "user", content: $user_msg}]
        }')

    local attempt=0
    local backoff=2

    while [[ $attempt -lt $MAX_RETRIES ]]; do
        attempt=$((attempt + 1))

        set +e
        response=$(curl -s --connect-timeout 10 --max-time 30 \
            -w "\n%{http_code}" \
            -H "x-api-key: ${ANTHROPIC_API_KEY}" \
            -H "anthropic-version: 2023-06-01" \
            -H "content-type: application/json" \
            "https://api.anthropic.com/v1/messages" \
            -d "$request_body" 2>/dev/null)
        local curl_exit=$?
        set -e

        if [[ $curl_exit -ne 0 ]]; then
            sleep "$backoff"
            backoff=$((backoff * 2))
            continue
        fi

        local http_code
        http_code=$(echo "$response" | tail -1)
        local body
        body=$(echo "$response" | sed '$d')

        if [[ "$http_code" == "429" ]]; then
            sleep "$backoff"
            backoff=$((backoff * 2))
            continue
        fi

        if [[ "$http_code" =~ ^2 ]]; then
            local text_content
            text_content=$(echo "$body" | jq -r '.content[0].text // empty' 2>/dev/null)
            if [[ -n "$text_content" ]]; then
                echo "$text_content"
                return 0
            fi
        fi

        sleep "$backoff"
        backoff=$((backoff * 2))
    done

    return 1
}

extract_json_object() {
    local raw="$1"
    local candidate=""

    if echo "$raw" | jq -e '.summary and .behavior_change and .contract_change and .internal_only and .review_focus and .confidence' >/dev/null 2>&1; then
        echo "$raw"
        return 0
    fi

    candidate=$(echo "$raw" | sed '/^```/d' | tr -d '\n')
    if echo "$candidate" | jq -e '.summary and .behavior_change and .contract_change and .internal_only and .review_focus and .confidence' >/dev/null 2>&1; then
        echo "$candidate"
        return 0
    fi

    candidate=$(echo "$raw" | tr -d '\n' | sed 's/.*\({.*"summary".*"confidence".*}\).*/\1/' || true)
    if [[ -n "$candidate" ]] && echo "$candidate" | jq -e '.summary and .behavior_change and .contract_change and .internal_only and .review_focus and .confidence' >/dev/null 2>&1; then
        echo "$candidate"
        return 0
    fi

    return 1
}

declare -A NODE_FILES
declare -A NODE_DEPTH
declare -A FILE_ADDS
declare -A FILE_DELS
declare -A FILE_DIFFS

add_file_to_node() {
    local node="$1"
    local file="$2"

    if [[ -z "${NODE_FILES[$node]:-}" ]]; then
        NODE_FILES["$node"]="$file"
        NODE_DEPTH["$node"]=$(echo "$node" | tr -cd '/' | wc -c | tr -d ' ')
        return
    fi

    if ! echo "${NODE_FILES[$node]}" | grep -Fxq "$file"; then
        NODE_FILES["$node"]="${NODE_FILES[$node]}"$'\n'"$file"
    fi
}

CHANGED_FILES="$(get_changed_files)"

if [[ -z "$CHANGED_FILES" ]]; then
    echo "# Semantic Diff Explainer"
    echo ""
    echo "No changed files detected."
    exit 0
fi

while IFS= read -r file; do
    [[ -z "$file" ]] && continue

    read -r adds dels <<< "$(get_file_numstat "$file")"
    FILE_ADDS["$file"]="$adds"
    FILE_DELS["$file"]="$dels"
    FILE_DIFFS["$file"]="$(get_file_diff "$file")"

    if is_intent_node "$file"; then
        add_file_to_node "$file" "$file"
        continue
    fi

    node=$("$FIND_COVERING_NODE" "$REPO_ROOT/$file" 2>/dev/null | sed "s|^$REPO_ROOT/||") || true
    [[ -z "$node" ]] && continue

    add_file_to_node "$node" "$file"
done <<< "$CHANGED_FILES"

DIRECT_NODES=()
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    if is_intent_node "$file"; then
        DIRECT_NODES+=("$file")
    fi
done <<< "$CHANGED_FILES"

if [[ ${#NODE_FILES[@]} -eq 0 && ${#DIRECT_NODES[@]} -eq 0 ]]; then
    echo "# Semantic Diff Explainer"
    echo ""
    echo "No Intent Nodes cover the changed files."
    exit 0
fi

echo "# Semantic Diff Explainer"
echo ""

if [[ -z "$BASE_REF" ]]; then
    echo "Range: uncommitted changes"
else
    echo "Range: $BASE_REF..$HEAD_REF"
fi

change_count=$(echo "$CHANGED_FILES" | wc -l | tr -d ' ')
echo "Changed files: $change_count"
echo ""

if [[ ${#DIRECT_NODES[@]} -gt 0 ]]; then
    echo "## Directly Modified Nodes"
    echo ""
    for node in "${DIRECT_NODES[@]}"; do
        echo "- $node"
    done
    echo ""
fi

if $DRY_RUN; then
    echo "Dry-run mode: showing affected nodes and scoped files only."
    echo ""
    echo "## Affected Nodes"
    echo ""
    for node in "${!NODE_FILES[@]}"; do
        file_count=$(echo "${NODE_FILES[$node]}" | awk 'NF' | wc -l | tr -d ' ')
        echo "### $node"
        echo "Files: $file_count"
        echo ""
        while IFS= read -r file; do
            [[ -z "$file" ]] && continue
            echo "- $file"
        done <<< "${NODE_FILES[$node]}"
        echo ""
    done | awk '1'
    exit 0
fi

ordered_nodes=$(
    for node in "${!NODE_FILES[@]}"; do
        printf '%s\t%s\n' "${NODE_DEPTH[$node]:-0}" "$node"
    done | sort -rn | cut -f2
)

for node in $ordered_nodes; do
    files="${NODE_FILES[$node]}"
    file_count=$(echo "$files" | awk 'NF' | wc -l | tr -d ' ')
    total_adds=0
    total_dels=0
    prod_files=0
    test_files=0
    config_files=0
    doc_files=0
    internal_artifact_files=0
    sensitive_files=0
    contract_signals=0
    behavior_signals=0
    internal_signals=0
    major_files=()
    review_focus=()
    scope_diff=""
    entry_points="$(extract_entry_points "$node" 2>/dev/null || true)"

    while IFS= read -r file; do
        [[ -z "$file" ]] && continue

        adds="${FILE_ADDS[$file]:-0}"
        dels="${FILE_DELS[$file]:-0}"
        total_adds=$((total_adds + adds))
        total_dels=$((total_dels + dels))

        if is_sensitive_file "$file"; then
            sensitive_files=$((sensitive_files + 1))
        fi
        if is_internal_artifact_file "$file"; then
            internal_artifact_files=$((internal_artifact_files + 1))
        elif is_test_file "$file"; then
            test_files=$((test_files + 1))
        elif is_doc_file "$file"; then
            doc_files=$((doc_files + 1))
        elif is_config_file "$file"; then
            config_files=$((config_files + 1))
        else
            prod_files=$((prod_files + 1))
        fi

        if is_contract_file "$file"; then
            contract_signals=$((contract_signals + 1))
        fi

        if echo "$entry_points" | grep -qx "$file" 2>/dev/null; then
            contract_signals=$((contract_signals + 1))
            behavior_signals=$((behavior_signals + 1))
            review_focus+=("Re-read the node entry point \`$file\` because the main workflow changed.")
        fi

        diff_text="${FILE_DIFFS[$file]:-}"
        scope_diff+="$diff_text"$'\n'

        if [[ $((adds + dels)) -ge 80 ]]; then
            major_files+=("$file")
        fi

        if ! is_test_file "$file" && ! is_doc_file "$file" && ! is_config_file "$file" && ! is_internal_artifact_file "$file"; then
            if echo "$diff_text" | grep -Eq '^[+-].*(export |def |func |class |interface |type |schema|contract|public |api|route|handler|signature|return type|response|request)' 2>/dev/null; then
                contract_signals=$((contract_signals + 1))
            fi

            if echo "$diff_text" | grep -Eq '^[+-].*(if |else|case |match |switch |throw |raise |return |await |retry|timeout|validate|auth|permission|query|SELECT|INSERT|UPDATE|DELETE|status|error|cache|feature flag)' 2>/dev/null; then
                behavior_signals=$((behavior_signals + 1))
            fi

            if echo "$diff_text" | grep -Eq '^[+-].*(private |internal |refactor|rename|extract|helper|cleanup|comment|formatting)' 2>/dev/null; then
                internal_signals=$((internal_signals + 1))
            fi
        fi

        if is_internal_artifact_file "$file"; then
            review_focus+=("Ignore generated or internal artifacts in \`$file\` unless they indicate a workflow contract drift.")
        elif is_test_file "$file"; then
            review_focus+=("Check whether test updates in \`$file\` reflect intended behavior rather than masking a regression.")
        elif is_config_file "$file"; then
            review_focus+=("Verify configuration changes in \`$file\` do not widen behavior unexpectedly.")
        elif is_doc_file "$file"; then
            review_focus+=("Confirm documentation in \`$file\` still matches runtime behavior.")
        else
            review_focus+=("Inspect \`$file\` for user-visible logic changes and edge-case handling.")
        fi
    done <<< "$files"

    filtered_diff="$(filter_sensitive_diff "$scope_diff")"
    truncated_diff="$(printf '%s' "$filtered_diff" | head -c "$MAX_DIFF_CHARS")"

    summary="Changes are concentrated in $file_count file(s) under this node."
    behavior_change="No material behavioral change detected."
    contract_change="No contract change detected."
    internal_only="No clear internal-only signal."
    confidence="medium"

    if [[ $prod_files -eq 0 && $test_files -gt 0 && $config_files -eq 0 && $doc_files -eq 0 && $internal_artifact_files -eq 0 ]]; then
        summary="This node changed only through tests."
        behavior_change="Runtime behavior is probably unchanged; the diff mainly adjusts verification around existing logic."
        internal_only="The changed files are test-only, so this looks internal unless the tests were updated to match a new contract."
        confidence="high"
    elif [[ $prod_files -eq 0 && $doc_files -gt 0 && $config_files -eq 0 && $internal_artifact_files -eq 0 ]]; then
        summary="This node changed only through documentation."
        behavior_change="No material behavioral change detected."
        internal_only="The diff is documentation-only, so the semantic impact is likely explanatory rather than executable."
        confidence="high"
    elif [[ $prod_files -eq 0 && $internal_artifact_files -gt 0 && $test_files -eq 0 && $config_files -eq 0 && $doc_files -eq 0 ]]; then
        summary="This node changed only through internal artifacts."
        behavior_change="No material behavioral change detected."
        internal_only="The diff is limited to generated or internal tracking artifacts, so runtime semantics are likely unchanged."
        confidence="high"
    elif [[ $behavior_signals -gt 0 || ${#major_files[@]} -gt 0 ]]; then
        behavior_change="Behavior likely changed in code paths covered by this node, not just formatting or comments."
        summary="The diff changes executable code in this node and deserves semantic review."
        confidence="high"
    fi

    if [[ $contract_signals -gt 0 ]]; then
        contract_change="Interfaces, invariants, or caller expectations likely changed and should be reviewed against the node guidance."
    elif [[ $config_files -gt 0 && $prod_files -eq 0 ]]; then
        contract_change="No code-level contract change detected, but configuration defaults may have shifted."
    elif [[ $internal_artifact_files -gt 0 && $prod_files -eq 0 && $test_files -eq 0 && $config_files -eq 0 && $doc_files -eq 0 ]]; then
        contract_change="No contract change detected; the diff appears limited to internal bookkeeping artifacts."
    fi

    if [[ $internal_signals -gt 0 && $behavior_signals -eq 0 && $contract_signals -eq 0 ]]; then
        internal_only="The diff has refactor-style signals and may be internal-only, but review is still warranted for hidden behavior changes."
    elif [[ $test_files -gt 0 && $prod_files -eq 0 ]]; then
        internal_only="Changes are isolated to tests, which is a strong internal-only signal."
    elif [[ $doc_files -gt 0 && $prod_files -eq 0 && $config_files -eq 0 && $internal_artifact_files -eq 0 ]]; then
        internal_only="Changes are isolated to docs, which is a strong internal-only signal."
    elif [[ $internal_artifact_files -gt 0 && $prod_files -eq 0 && $test_files -eq 0 && $config_files -eq 0 && $doc_files -eq 0 ]]; then
        internal_only="Changes are isolated to internal artifacts, which is a strong internal-only signal."
    fi

    if [[ ${#major_files[@]} -gt 0 ]]; then
        review_focus+=("Review larger diffs in ${major_files[0]} first; size increases the chance of hidden contract drift.")
    fi
    if [[ $sensitive_files -gt 0 ]]; then
        review_focus+=("Sensitive files changed in this scope; the summary intentionally excludes their contents.")
    fi

    if [[ -n "${ANTHROPIC_API_KEY:-}" && -n "$truncated_diff" ]]; then
        if command -v jq >/dev/null 2>&1 && command -v curl >/dev/null 2>&1; then
            node_content="$(cat "$node" 2>/dev/null || true)"
            ai_raw="$(call_haiku "$node" "$node_content" "$truncated_diff" 2>/dev/null || true)"
            ai_json="$(extract_json_object "$ai_raw" 2>/dev/null || true)"
            if [[ -n "$ai_json" ]]; then
                summary="$(echo "$ai_json" | jq -r '.summary')"
                behavior_change="$(echo "$ai_json" | jq -r '.behavior_change')"
                contract_change="$(echo "$ai_json" | jq -r '.contract_change')"
                internal_only="$(echo "$ai_json" | jq -r '.internal_only')"
                confidence="$(echo "$ai_json" | jq -r '.confidence')"
                mapfile -t ai_focus < <(echo "$ai_json" | jq -r '.review_focus[]?')
                if [[ ${#ai_focus[@]} -gt 0 ]]; then
                    review_focus=("${ai_focus[@]}")
                fi
            fi
        fi
    fi

    unique_focus=()
    declare -A seen_focus=()
    for item in "${review_focus[@]}"; do
        [[ -z "$item" ]] && continue
        if [[ -z "${seen_focus[$item]:-}" ]]; then
            unique_focus+=("$item")
            seen_focus["$item"]=1
        fi
        [[ ${#unique_focus[@]} -ge 4 ]] && break
    done
    unset seen_focus

    echo "## $node"
    echo ""
    echo "Summary: $summary"
    echo "Changed files: $file_count"
    echo "Confidence: $confidence"
    echo ""
    echo "Behavioral impact: $behavior_change"
    echo "Contract impact: $contract_change"
    echo "Internal-only signal: $internal_only"
    echo ""
    echo "Review focus:"
    if [[ ${#unique_focus[@]} -eq 0 ]]; then
        echo "- Review the scoped diff for behavior changes and contract drift."
    else
        for item in "${unique_focus[@]}"; do
            echo "- $item"
        done
    fi
    echo ""
done

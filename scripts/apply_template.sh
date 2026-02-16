#!/usr/bin/env bash
# Apply an Intent Layer template to a project
# Usage: apply_template.sh <project_root> <template_name> [options]
#
# Templates live in $PLUGIN_ROOT/references/templates/<name>/
# Copies .template files, stripping the suffix, preserving directory structure.

set -euo pipefail

# Find plugin root by walking up to .claude-plugin/ directory
find_plugin_root() {
    local dir
    dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    while [[ "$dir" != "/" ]]; do
        if [[ -d "$dir/.claude-plugin" ]]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    echo "Error: Could not find plugin root (.claude-plugin/ directory)" >&2
    return 1
}

PLUGIN_ROOT="$(find_plugin_root)"
TEMPLATES_DIR="$PLUGIN_ROOT/references/templates"

show_help() {
    cat << 'EOF'
apply_template.sh - Apply an Intent Layer template to a project

USAGE:
    apply_template.sh [OPTIONS] <PROJECT_ROOT> <TEMPLATE_NAME>

ARGUMENTS:
    PROJECT_ROOT    Target project directory
    TEMPLATE_NAME   Name of the template to apply (see --list)

OPTIONS:
    --list              List available templates
    --preview           Show what would be created (dry-run)
    --force             Overwrite existing files
    -h, --help          Show this help message

TEMPLATES:
    Templates live in references/templates/<name>/ inside the plugin.
    Each template contains .template files that get copied with the
    suffix stripped, preserving directory structure.

EXIT CODES:
    0    Success (or --list/--preview completed)
    1    Invalid input (bad args, bad project root)
    2    Template not found (shows available templates)

EXAMPLES:
    apply_template.sh /path/to/project generic
    apply_template.sh --list
    apply_template.sh --preview /path/to/project generic
    apply_template.sh --force /path/to/project generic
EOF
    exit 0
}

# Resolve a path to its canonical form
resolve_path() {
    local path="$1"
    if command -v realpath &>/dev/null; then
        realpath "$path" 2>/dev/null || return 1
    elif command -v readlink &>/dev/null && readlink -f "$path" &>/dev/null 2>&1; then
        readlink -f "$path"
    else
        echo "$(cd "$(dirname "$path")" 2>/dev/null && pwd)/$(basename "$path")"
    fi
}

# List available templates
list_templates() {
    if [[ ! -d "$TEMPLATES_DIR" ]]; then
        echo "No templates directory found at: $TEMPLATES_DIR" >&2
        exit 1
    fi

    local found=false
    for tpl_dir in "$TEMPLATES_DIR"/*/; do
        [[ -d "$tpl_dir" ]] || continue
        found=true
        local name
        name="$(basename "$tpl_dir")"
        local desc=""
        if [[ -f "$tpl_dir/README.md" ]]; then
            desc="$(head -1 "$tpl_dir/README.md")"
        fi
        printf "  %-20s %s\n" "$name" "$desc"
    done

    if [[ "$found" = false ]]; then
        echo "No templates found in: $TEMPLATES_DIR" >&2
    fi
}

# Resolve a path that may not exist yet by resolving its parent directory
resolve_path_safe() {
    local path="$1"
    local dir
    dir="$(dirname "$path")"
    local base
    base="$(basename "$path")"

    # If the directory exists, resolve it
    if [[ -d "$dir" ]]; then
        local resolved_dir
        resolved_dir="$(resolve_path "$dir")"
        echo "$resolved_dir/$base"
        return 0
    fi

    # Directory doesn't exist — walk up to find an existing ancestor
    local prefix="$base"
    local current="$dir"
    while [[ ! -d "$current" && "$current" != "/" ]]; do
        prefix="$(basename "$current")/$prefix"
        current="$(dirname "$current")"
    done

    if [[ -d "$current" ]]; then
        local resolved_ancestor
        resolved_ancestor="$(resolve_path "$current")"
        echo "$resolved_ancestor/$prefix"
        return 0
    fi

    echo "Error: Cannot resolve path: $path" >&2
    return 1
}

# Check if a destination path is safely inside the project root
validate_dest_path() {
    local project_root="$1"
    local dest="$2"

    local resolved_dest
    resolved_dest="$(resolve_path_safe "$dest")" || {
        echo "Error: Cannot resolve path: $dest" >&2
        return 1
    }

    local resolved_root
    resolved_root="$(resolve_path "$project_root")"

    # Check prefix match
    case "$resolved_dest" in
        "$resolved_root"/*)
            return 0
            ;;
        "$resolved_root")
            return 0
            ;;
        *)
            echo "Error: Path traversal detected — destination '$resolved_dest' is outside project root '$resolved_root'" >&2
            return 1
            ;;
    esac
}

# Parse arguments
PROJECT_ROOT=""
TEMPLATE_NAME=""
LIST=false
PREVIEW=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        --list)
            LIST=true
            shift
            ;;
        --preview)
            PREVIEW=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            echo "  Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            if [[ -z "$PROJECT_ROOT" ]]; then
                PROJECT_ROOT="$1"
            elif [[ -z "$TEMPLATE_NAME" ]]; then
                TEMPLATE_NAME="$1"
            else
                echo "Error: Too many arguments" >&2
                echo "  Run with --help for usage information" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Handle --list
if [[ "$LIST" = true ]]; then
    echo "Available templates:"
    echo ""
    list_templates
    exit 0
fi

# Validate required arguments
if [[ -z "$PROJECT_ROOT" ]]; then
    echo "Error: No project root specified" >&2
    echo "" >&2
    echo "  Usage: apply_template.sh <project_root> <template_name>" >&2
    echo "  Run with --help for more information" >&2
    exit 1
fi

if [[ -z "$TEMPLATE_NAME" ]]; then
    echo "Error: No template name specified" >&2
    echo "" >&2
    echo "  Usage: apply_template.sh <project_root> <template_name>" >&2
    echo "  Run with --list to see available templates" >&2
    exit 1
fi

# Validate project root
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Error: Project root is not a directory: $PROJECT_ROOT" >&2
    exit 1
fi

PROJECT_ROOT="$(resolve_path "$PROJECT_ROOT")"

# Validate template exists
TEMPLATE_DIR="$TEMPLATES_DIR/$TEMPLATE_NAME"
if [[ ! -d "$TEMPLATE_DIR" ]]; then
    echo "Error: Template not found: $TEMPLATE_NAME" >&2
    echo "" >&2
    echo "Available templates:" >&2
    list_templates >&2
    exit 2
fi

# Check if Intent Layer already exists (warn unless --force)
if [[ "$FORCE" = false ]]; then
    if [[ -f "$PROJECT_ROOT/CLAUDE.md" ]] || [[ -f "$PROJECT_ROOT/AGENTS.md" ]]; then
        echo "Intent Layer already exists. Use --force to overwrite." >&2
        exit 1
    fi
fi

# Collect template files
TEMPLATE_FILES=()
while IFS= read -r file; do
    [[ -n "$file" ]] && TEMPLATE_FILES+=("$file")
done < <(find "$TEMPLATE_DIR" -name "*.template" -type f 2>/dev/null)

if [[ ${#TEMPLATE_FILES[@]} -eq 0 ]]; then
    echo "Error: No .template files found in: $TEMPLATE_DIR" >&2
    exit 1
fi

# Process each template file
CREATED=0
SKIPPED=0

for template_file in "${TEMPLATE_FILES[@]}"; do
    # Compute relative path within the template directory
    local_path="${template_file#"$TEMPLATE_DIR/"}"
    # Strip .template suffix
    dest_rel="${local_path%.template}"
    dest="$PROJECT_ROOT/$dest_rel"

    # Path traversal protection
    if ! validate_dest_path "$PROJECT_ROOT" "$dest"; then
        echo "  REJECTED: $dest_rel (path traversal)" >&2
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    if [[ "$PREVIEW" = true ]]; then
        echo "  would create: $dest_rel"
        CREATED=$((CREATED + 1))
        continue
    fi

    # Check for existing file
    if [[ -f "$dest" ]] && [[ "$FORCE" = false ]]; then
        echo "  SKIP: $dest_rel (already exists, use --force to overwrite)"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # Create intermediate directories
    mkdir -p "$(dirname "$dest")"

    # Copy template
    cp "$template_file" "$dest"
    echo "  created: $dest_rel"
    CREATED=$((CREATED + 1))
done

# Summary
echo ""
if [[ "$PREVIEW" = true ]]; then
    echo "Preview complete: $CREATED file(s) would be created"
else
    echo "Applied template '$TEMPLATE_NAME': $CREATED file(s) created, $SKIPPED skipped"
fi

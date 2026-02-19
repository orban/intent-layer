# Tools Module

## Purpose

Defines the MCP tool abstraction — from Python function to JSON-schema-validated MCP tool. This module handles function parsing, schema generation, tool transformation, and result serialization.

## Code Map

| File | Role |
|------|------|
| `tool.py` | `Tool` base class, `ToolResult` model, serialization |
| `function_tool.py` | `FunctionTool` — created from decorated Python functions via `@tool` / `@mcp.tool()` |
| `function_parsing.py` | `ParsedFunction` — inspects Python functions to extract JSON schema, handles Pydantic models, `Context` injection |
| `tool_transform.py` | `TransformedTool`, `ToolTransformConfig` — rename, redescribe, add/remove/transform arguments |

## Design

### Function → Tool pipeline
1. `@mcp.tool()` decorator attaches `ToolMeta` as `fn.__fastmcp__`
2. `FunctionTool.from_function(fn)` uses `ParsedFunction` to extract parameter schema
3. `ParsedFunction` introspects the function signature, builds JSON schema via Pydantic's `TypeAdapter`
4. Schema generation handles: `Context` parameter removal, dependency injection, `exclude_args`, `SkipJsonSchema`
5. `Tool.to_mcp_tool()` produces the MCP SDK `Tool` object with input/output schemas

### Execution flow
1. `FunctionTool.run(arguments, context)` is called by the server
2. Arguments are validated against the JSON schema
3. Injected parameters (Context, dependencies) are resolved
4. Sync functions are run in a thread pool via `call_sync_fn_in_threadpool`
5. Return value is serialized via `ToolResult` → `CallToolResult`

### Result serialization
- Return values are converted to `list[ContentBlock]` via `ToolResult`
- `Image`, `Audio`, `File` types from `utilities/types.py` are converted to appropriate content blocks
- Lists of content blocks are preserved; single values are wrapped
- Custom serializer can be set per-tool via `serializer` parameter
- Default serializer: `pydantic_core.to_json(data, fallback=str)`

## Entry Points

| Task | Start here |
|------|-----------|
| Define a tool | `function_tool.py` → `@tool` decorator or `FunctionTool.from_function()` |
| Customize tool schema | `function_parsing.py` → `ParsedFunction` |
| Transform a tool | `tool_transform.py` → `TransformedTool` |
| Serialize tool results | `tool.py` → `ToolResult` |

## Key Exports

- `Tool` — base class (used by providers to source tools)
- `FunctionTool` — the decorator-created variant
- `ToolResult` — structured result model
- `TransformedTool`, `ToolTransformConfig` — for tool transforms

## Contracts

- **Tool names must be MCP-valid**: validated by `mcp.shared.tool_name_validation.validate_and_warn_tool_name`
- **Context parameter is auto-removed from schema**: `ParsedFunction` detects `Context` type-annotated params and excludes them from the JSON schema, injecting them at call time
- **output_schema generation**: by default, tools get an output schema from their return type annotation. Set `output_schema=None` to disable. `output_schema=False` is legacy and still supported.
- **$defs must not be mutated**: schema `$defs` are shared across tool instances. Transforms must deep-copy before modifying (#2493).
- **Root-level $ref must be resolved**: MCP spec requires resolved schemas, not top-level `$ref` (#2720).
- **additionalProperties: false must be preserved**: schema compression must not strip this (#3102).

## Pitfalls

- **$defs mutation in transforms**: `Tool.from_tool()` transforms shared the `$defs` dict. Transforms that modify `$defs` corrupt all tools sharing that schema. Always deep-copy (#2493).
- **compress_schema stripping additionalProperties**: the schema compression utility removed `additionalProperties: false`, which MCP validation requires (#3102).
- **Single-element list unwrapping**: a tool returning `[single_item]` was unwrapped to just `single_item`, changing the response structure. Lists must be preserved (#1074).
- **Field() in function parameters**: using Pydantic `Field()` as default values in tool functions required special handling (#3050).
- **title metadata in JSON schema**: schema generation added `title` fields that conflicted with parameters actually named `title`. Must strip metadata titles while preserving real ones (#1872).
- **functools.wraps breaks Context detection**: wrapped functions lose their signature. `create_function_without_params` must also update the signature, not just the function body (#2563).
- **Exclude_args with non-serializable types**: `exclude_args` failed when the excluded parameter had a non-serializable default value (#2440).
- **Union type output schemas**: non-object union types needed special schema wrapping to produce valid MCP output schemas (#995).
- **OpenAPI tool name registration**: tool names modified by `mcp_component_fn` weren't registered under the new name (#1096).

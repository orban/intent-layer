# LLM Client

Pluggable LLM abstraction with caching and retry logic.

## Architecture

`LLMClient` ABC (`client.py`) with implementations for OpenAI, Anthropic, Google, Groq, Voyage.

### Features
- Diskcache for optional response caching
- Tenacity retry: 4 attempts, exponential backoff on rate limits and server errors
- Structured output via Pydantic models appended as JSON schema to prompts
- Two model sizes: `model` (medium, default `gpt-4.1-mini`) and `small_model` (small, default `gpt-4.1-nano`)

## Contracts

- All implementations must handle both `model` and `small_model` calls
- Structured output requires a Pydantic model class — schema is auto-appended to prompt
- Cache key includes model name + prompt text — different models get separate cache entries

## Pitfalls

- Default models are OpenAI-specific names — other providers need explicit model configuration
- Cache is per-model, so switching models doesn't use cached results from the old model

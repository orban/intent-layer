# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Plan: Add statistical analysis to eval harness

## Context

Our eval harness runs Claude bug-fix trials under 3 conditions (none, flat_llm, intent_layer) but reports raw pass/fail counts with no statistical analysis. The paper we're replicating (arxiv 2602.11988v1) ran each task once with no confidence intervals — their 2-4% differences are indistinguishable from noise.

We explored integrating with Cerberus (external TypeScript stats tool) but 3 independent re...

### Prompt 2

commit this


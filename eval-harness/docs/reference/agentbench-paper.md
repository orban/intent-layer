# Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?

**Thibaud Gloaguen, Niels Mündler, Mark Müller, Veselin Raychev, Martin Vechev**
**Source**: https://arxiv.org/html/2602.11988v1

## Abstract

A widespread practice in software development is to tailor coding agents to repositories using context files, such as AGENTS.md, by either manually or automatically generating them. Although this practice is strongly encouraged by agent developers, there is currently no rigorous investigation into whether such context files are actually effective for real-world tasks. In this work, we study this question and evaluate coding agents' task completion performance in two complementary settings: established SWE-bench tasks from popular repositories, with LLM-generated context files following agent-developer recommendations, and a novel collection of issues from repositories containing developer-committed context files.

Across multiple coding agents and LLMs, we find that context files tend to _reduce_ task success rates compared to providing no repository context, while also _increasing inference cost_ by over 20%. Behaviorally, both LLM-generated and developer-provided context files encourage broader exploration (e.g., more thorough testing and file traversal), and coding agents tend to respect their instructions. Ultimately, we conclude that unnecessary requirements from context files make tasks harder, and human-written context files should describe only minimal requirements.

## 1 Introduction

Coding agents are being rapidly adopted across the software engineering industry, and providing context files like AGENTS.md, a README specifically targeting agents, has become common practice. With various industry leaders recommending this approach to adapt their agents to specific repositories, context files are now supported by most popular agent frameworks, and included in over 60,000 open-source repositories at the time of writing.

These context files typically contain a repository overview and information on relevant developer tooling, aiming to help coding agents to navigate a given repository more efficiently, run build and test commands correctly, adhere to style guides and design patterns, and ultimately to solve tasks to the user's satisfaction more frequently. To date, despite their widespread adoption, the impact of context files on the coding agent's ability to solve complex software engineering tasks has not been rigorously studied.

### This work: Benchmarking context files' impact on resolving GitHub issues

In this work, we investigate the effect of actively used context files on the resolution of real-world coding tasks. We evaluate agents both in popular and less-known repositories, and, importantly, with context files provided by repository developers. For this purpose, we construct a novel benchmark, AGENTbench, comprising Python software engineering tasks, created specifically from real GitHub issues. The benchmark contains 138 unique instances, covering both bug-fixing and feature addition tasks across 12 recent and niche repositories, which all feature developer-written context files.

We evaluate coding agents in three settings: without any context file, with context files automatically generated using agent-developer recommendations, and with the developer-provided context file.

Surprisingly, we observe that developer-provided files only marginally improve performance compared to omitting them entirely (an increase of 4% on average), while LLM-generated context files have a small negative effect on agent performance (a decrease of 3% on average). These observations are robust across different LLMs and prompts used to generate the context files. In a more detailed analysis, we observe that context files lead to increased exploration, testing, and reasoning by coding agents, and, as a result, increase costs by over 20%. We therefore suggest omitting LLM-generated context files for the time being, contrary to agent developers' recommendations, and including only minimal requirements.

### Key contributions

1. AGENTbench, a new curated benchmark for the impact of actively used context files on agents' ability to solve real-world software engineering tasks.
2. An extensive evaluation of different coding agents and underlying models on AGENTbench and SWE-bench Lite, showing that LLM-generated context files tend to decrease agent performance, across models or prompts used to generate them, while developer-written context files tend to slightly improve it.
3. A detailed investigation of agent traces, showing that context files lead to more thorough testing and exploration by coding agents.

## 2 Background and Related Work

### Coding agents

Coding agents are LLM-based systems designed for autonomous resolution of coding tasks. Typically, they consist of a harness that allows an LLM to interact with its environment using specialized tools for, e.g., executing bash commands, conducting web searches, or reading, creating, or modifying files. Their impressive performance on repository-level coding tasks like SWE-bench led to rapid adoption in the software engineering community and the development of new agents by specialized companies and model providers.

### Context files

As coding agents were more broadly adopted, a common need arose to provide the agent with additional context about novel and little-known codebases. To address this issue, model and agent developers recommend including context files, such as AGENTS.md or CLAUDE.md, with codebases. Many agent harnesses provide built-in commands to initialize such context files automatically using the coding agent itself. At the time of writing, over 60,000 public GitHub repositories include a context file.

### Evaluating context files

Prior work collected and categorized the content of context files, deriving mostly descriptive metrics about their content without investigating their effectiveness. We are the first to investigate the impact of actively used context files on agent behavior and performance at scale.

### Repository-level evaluation

Evaluating coding agents on the autonomous resolution of real-world repository-level tasks quickly became the gold standard for assessing their capabilities.

## 3 AGENTbench

### 3.1 Notation and Definitions

- R = codebase/repository
- R∘X = repository after applying patch X
- T = test suite, exec_R(T) ∈ {pass, fail}
- Instance = (I, R, T, X*) where I=issue, X*=golden patch
- Success rate S = percentage where exec_{R∘X̂}(T) = pass

### 3.2 Generation of AGENTbench Instances

Five-stage process:

1. **Finding repositories**: GitHub search for repos with context files at root, Python main language, test suite, 400+ PRs
2. **Filtering PRs**: Rule-based + LLM agent to select PRs with deterministic, testable behaviors
3. **Environment Setup**: Coding agent creates Docker env + test runner scripts
4. **Task Descriptions**: LLM standardizes PR/issue into 6 sections (description, steps to reproduce, expected behavior, observed behavior, specification, additional info)
5. **Test Generation**: LLM generates unit tests that fail on R, pass on R∘X*. Average 75% coverage.

Result: 138 instances from 5694 PRs across 12 repositories.

## 4 Experimental Evaluation

### 4.1 Setup

**Agents**: Claude Code (Sonnet-4.5), Codex (GPT-5.2, GPT-5.1 mini), Qwen Code (Qwen3-30b-coder)

**Datasets**: SWE-bench Lite (300 tasks, 11 repos), AGENTbench (138 tasks, 12 repos)

**Settings**: None / LLM / Human

**Metrics**: Success rate, steps, cost

### 4.2 Main Results

- LLM-generated: -0.5% success (SWE-bench), -2% success (AGENTbench)
- Human-written: +4% success (AGENTbench)
- Cost increase: +20% (SWE-bench), +23% (AGENTbench)
- Steps increase: +2.45 (SWE-bench), +3.92 (AGENTbench)
- Human outperforms LLM for ALL four agents
- No meaningful reduction in discovery speed
- When docs removed: LLM context files improve by +2.7% (confirms redundancy)

### 4.3 Trace Analysis

- More testing and exploration with context files
- Instructions are typically followed (tools mentioned get 1.6-2.5x more usage)
- Reasoning tokens increase 10-22%

### 4.4 Ablations

- Stronger models don't generate better context files
- No consistent difference between Codex vs Claude prompts

## 5 Limitations

1. Python-focused (well-represented in training data)
2. Only task resolution measured (not code quality/security)
3. Niche repos less strict about PR requirements
4. Context files only formalized August 2025
5. Many repos don't include context files

## 6 Conclusion

All context files consistently increase steps. LLM-generated have marginal negative effect. Developer-written provide marginal gain. Context files "have only marginal effect on agent behavior, and are likely only desirable when manually written."

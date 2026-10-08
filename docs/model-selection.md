# Model selection

Research date: **2026-10-08**. These assignments are recommendations for this
workflow, based on the official documentation below. They have not been
benchmarked against this repository's tasks.

## Default assignments

| Role | Codex model | Codex effort | Claude Code model | Claude effort |
| --- | --- | --- | --- | --- |
| Planner | `gpt-6-astra` | `xhigh` | `claude-opus-5-5` | `high` |
| Worker | `gpt-6-luna` | `high` | `claude-sonnet-5-5` | `high` |
| Reviewer | `gpt-6.1-sol` | `high` | `claude-opus-5-5` | `high` |

The existing Codex assignments are retained. OpenAI positions Astra for its
most demanding work, Sol 6.1 for a balance of capability and cost, and Luna for
focused tasks. See the [OpenAI model catalog](https://developers.openai.com/api/docs/models).

## Why these Claude models

**Planner: Opus 5.5.** Planning is reserved for ambiguous, cross-module, or
high-risk changes. A plan must identify dependencies and constraints before
implementation starts. Opus is a suitable starting point for that judgment;
Anthropic describes it as a model for sustained coding and professional tasks.
[Opus 5.5 documentation](https://platform.claude.com/docs/en/models/opus-5-5/overview).

**Worker: Sonnet 5.5.** The worker receives a bounded contract and an approved
plan. Sonnet's balance of speed and capability fits everyday implementation
and debugging. Its listed API input/output rates are $2/$10 per million tokens,
compared with Opus's $4/$20; actual task cost also depends on token usage.
[Sonnet 5.5 documentation](https://platform.claude.com/docs/en/models/sonnet-5-5/overview),
[Opus pricing](https://platform.claude.com/docs/en/models/opus-5-5/overview#pricing).

**Reviewer: Opus 5.5.** Review needs careful reasoning about omissions,
regressions, compatibility, and security. This workflow spends more capability
on that check. Independence comes from a fresh review context and an evidence
packet, rather than requiring a different model family. The root still decides
which findings block completion. This is a workflow design choice informed by
[Anthropic's model-selection guidance](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model).

## Effort and version requirements

Claude Code supports an `effort` setting in each agent's frontmatter. This
package explicitly chooses `high` for all three roles because verification and
edge cases matter. Claude Code defaults the 5.5 models to `medium`; the Sonnet
API default is separately documented as `high`. Effort labels are calibrated
per model, so GPT `xhigh` is not a numerical equivalent of Claude `xhigh`.
Higher settings should be evaluated on representative work before becoming
defaults. See [Claude Code model configuration](https://code.claude.com/docs/en/model-config#adjust-effort-level)
and [agent frontmatter](https://code.claude.com/docs/en/sub-agents#frontmatter-reference).

The default pair requires **Claude Code 2.1.284 or newer**: Opus 5.5 support
starts at 2.1.280 and Sonnet 5.5 at 2.1.284. Optional Haiku 5.5 use requires
2.1.293 or newer. Full model IDs are pinned because family aliases can resolve
to older models on some providers. Provider access, organization settings,
forced model overrides, and environment effort overrides can affect a running
session. The verifier checks installed configuration, not account access or
the model actually serving a request.
[Claude Code model configuration](https://code.claude.com/docs/en/model-config).

## When to change the default

- **Haiku 5.5:** consider it for repetitive edits, extraction, and tightly
  specified low-risk work after checking results on your tasks. It was released
  on October 7, 2026 and supports adjustable effort. It is an optional choice,
  not this package's general implementation default.
  [Haiku 5.5 announcement](https://www.anthropic.com/claude-haiku-5-5).
- **Opus implementation:** use it for consequential migrations, concurrency,
  security-sensitive changes, or work that outgrows the Sonnet contract. The
  root can choose a stronger implementation path under the shared routing rules.
- **Fable 5.1:** reserve it for demanding work where evaluations with Opus at
  higher effort still fall short. The three bounded roles do not require it as
  a default. [Anthropic's model-selection guidance](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model).

To persist a different Claude assignment, edit the `model` or `effort` in the
appropriate `adapters/claude/*.toml`, then reinstall and verify the Claude
target. The adapters accept `low`, `medium`, `high`, `xhigh`, and `max`.
Keep the role's tool restrictions. The shared prompts need no model
names. Codex model and effort choices live in `adapters/codex/*.toml`; a pinned
custom agent's settings can take precedence over a spawn-time override, so use
an appropriately configured root or a deliberately selected strong default
agent for high-risk implementation.
[Codex custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents).

## Validation scope

The implementation is tested offline for installation, migration, preservation,
and generated configuration. Model quality and account availability require
separate evaluation. During this change, the available Claude Code installation
was 2.1.207, below the version required by the selected models; native 5.5 model
loading and live agent execution were therefore not validated.

# Codex global planner/worker/reviewer workflow

A portable, machine-wide Codex setup for proportional routing through three custom agents:

- `planner`: GPT-6 Sol xhigh, read-only architecture and planning
- `worker`: GPT-6 Luna high, bounded implementation and verification
- `reviewer`: GPT-6 Sol high, independent read-only defect review

The root Codex agent remains responsible for task classification, integration, reviewer-finding triage, and final acceptance. The full pipeline is reserved for work whose complexity or risk justifies its coordination cost.

Sol handles architecture and independent review; Luna executes bounded implementation tasks with high reasoning effort. For high-risk implementation, the root should use Sol through the existing suitably strong implementation path. Model IDs and supported reasoning levels are listed in the [OpenAI model catalog](https://developers.openai.com/api/docs/models).

## Install

Requirements:

- A current Codex CLI installation
- Python 3.11 or newer

Clone this private repository, then run:

```bash
./install.sh
```

The installer:

1. Uses `$CODEX_HOME`, or `~/.codex` when it is unset.
2. Creates a timestamped backup under `$CODEX_HOME/backups/`.
3. Installs the three agents under `$CODEX_HOME/agents/`.
4. Merges the workflow into the global `AGENTS.md` using managed markers.
5. Enables multi-agent support and sets the open subagent-thread cap to three without replacing unrelated configuration.
6. Validates the installed TOML files.

Restart Codex after installation so it reloads the global instructions.

## Verify

```bash
./verify.sh
```

Then, from any project, ask Codex:

```text
Summarize the global proportional development workflow and list the custom agents available.
```

## Update another machine

```bash
git pull
./install.sh
```

Each installation creates a fresh rollback backup.

## Test prompt

```text
Explain how you would route this task under the global development workflow,
but do not implement it: add rate limiting to authentication endpoints.
```

## Files

```text
agents/planner.toml
agents/worker.toml
agents/reviewer.toml
AGENTS.workflow.md
install.sh
verify.sh
scripts/install.py
scripts/verify.py
```

The repository intentionally excludes your authentication data and complete machine-specific `config.toml`.

# Shared Codex and Claude Code agent workflow

One workflow and three role prompts, installed as native global configuration for Codex, Claude Code, or both. The root agent owns task classification, integration, review triage, and final acceptance. Delegation is proportional to the task: simple work stays local; complex work uses planning, bounded implementation, and independent review.

| Role | Codex | Claude Code | Access |
| --- | --- | --- | --- |
| `planner` | GPT-6 Astra, xhigh | Claude Opus 5.5, high | Read-only planning |
| `worker` | GPT-6 Luna, high | Claude Sonnet 5.5, high | Bounded implementation and verification |
| `reviewer` | GPT-6.1 Sol, high | Claude Opus 5.5, high | Read-only review |

These are recommendations, not measured cross-vendor performance results. See [model selection and limitations](docs/model-selection.md) for the dated research and optional alternatives.

## Requirements

- Python 3.11 or newer; the installer and tests use only the standard library.
- A Codex CLI that supports standalone TOML custom agents, when installing for Codex.
- Claude Code **2.1.284 or newer** for the default Opus 5.5 and Sonnet 5.5 assignments. Model access must also be available through your provider.

This repository does not install or upgrade either CLI or call models. Validation is offline. The local Claude Code 2.1.207 used during development was too old to validate native loading of these agents; model loading and live model evaluations have not been verified.

## Install and verify

From this checkout, the original no-argument commands still select Codex:

```sh
./install.sh
./verify.sh
```

Choose either platform or both:

```sh
./install.sh --target claude
./verify.sh --target claude

./install.sh --target both
./verify.sh --target both
```

Home resolution is independent for each selected platform: an explicit flag takes precedence over the environment variable, followed by the default directory.

| Target | Flag | Environment | Default |
| --- | --- | --- | --- |
| Codex | `--codex-home PATH` | `CODEX_HOME` | `~/.codex` |
| Claude Code | `--claude-home PATH` | `CLAUDE_CONFIG_DIR` | `~/.claude` |

```sh
CODEX_HOME="$HOME/custom-codex" ./install.sh
CLAUDE_CONFIG_DIR="$HOME/custom-claude" ./install.sh --target claude

./install.sh --target both \
  --codex-home "$HOME/custom-codex" \
  --claude-home "$HOME/custom-claude"
./verify.sh --target both \
  --codex-home "$HOME/custom-codex" \
  --claude-home "$HOME/custom-claude"
```

The Python entry points also accept an optional positional repository root, preserving the old installer interface:

```sh
python3 scripts/install.py /path/to/checkout --target both
python3 scripts/verify.py /path/to/checkout --target both
```

The wrappers supply their own checkout root and forward all flags. An unselected platform's home and adapter files are not inspected. Restart the selected CLI after installation. In a new session, ask it to describe the proportional workflow and list the available custom agents.

To update an installation, pull the desired repository revision, rerun the same install command, then verify against that checkout. Verification compares complete native agent content, including metadata and prompt, with the shared sources. It also checks the workflow block and Codex configuration. Edits made only to installed managed content will fail verification and be replaced by a subsequent installation.

## Sources and owned files

```text
shared/workflow.md                 shared global routing instructions
shared/prompts/{planner,worker,reviewer}.md
                                  shared role instructions
adapters/codex/{planner,worker,reviewer}.toml
adapters/claude/{planner,worker,reviewer}.toml
                                  platform metadata only
shared/legacy/codex-workflow-v1.md  immutable historical migration snapshot
scripts/common.py                 validation, rendering, and preflight
scripts/{install,verify}.py        CLI entry points
```

Edit the shared workflow or role prompts once, then reinstall the selected platforms. Rendered agents contain their complete prompts and have no runtime dependency on this checkout. To use another model available through your provider, change its `model` field in the appropriate adapter and reinstall. Role names, effort levels, access constraints, and the metadata schema are validated; additional managed role source files are rejected. Keep the legacy snapshot unchanged: it exists only to recognize exact older installations.

The installer owns these destinations:

| Platform | Managed destination | Behavior |
| --- | --- | --- |
| Codex | `AGENTS.md` | Merge one managed workflow block |
| Codex | `agents/planner.toml`, `agents/worker.toml`, `agents/reviewer.toml` | Replace complete native agent files |
| Codex | `config.toml` | Set `[agents] enabled = true` and `max_concurrent_threads_per_session = 3`; remove the old `max_threads` alias; enforce mode `0600` |
| Claude Code | `CLAUDE.md` | Merge one managed workflow block |
| Claude Code | `agents/planner.md`, `agents/worker.md`, `agents/reviewer.md` | Replace complete native agent files |

Unrelated instructions, other agents, and unrelated Codex values and comments are preserved. Claude `settings.json` and authentication files are neither read nor written. No project files are installed, and Claude uses its native global `CLAUDE.md` rather than an assumed `AGENTS.md` fallback.

Codex configuration updates preserve lines and verify that unrelated parsed values are unchanged. Unusual layouts, such as inline or dotted `agents` definitions, fail before installation; use a plain `[agents]` section if the installer reports an unsupported layout. Managed file destinations must be regular files. The managed home, `agents`, and `backups` directories must be ordinary directories rather than symlinks.

## Migration and recovery

The current markers are:

```markdown
<!-- global-agent-workflow:start -->
... shared workflow ...
<!-- global-agent-workflow:end -->
```

Installation migrates old `codex-global-agent-workflow` blocks and consolidates repeated complete old or current blocks. An unmarked copy is removed only when it exactly matches the historical workflow as a standalone block. Modified unmarked instructions remain. Stray, reversed, nested, or mismatched markers fail preflight so unrelated instructions are not accidentally removed.

All selected sources and destinations are checked before any home is changed, including when installing `both`. Changed existing files are copied with their relative paths and permissions into a uniquely named directory printed as `Backup:` under that home:

```text
<home>/backups/global-agent-workflow-<unique suffix>/
```

Repeated installs with no changes create no backups. A fresh install with no existing managed files also needs no backup. Writes use a temporary file and atomic replacement for each destination. This is **per-file atomicity**, not a transaction spanning files or homes: an operating-system error during writes can leave a partial installation. Existing files have already been backed up before writes start.

To roll back, stop the relevant CLI and copy the saved files from the printed backup directory to the same relative locations under that platform's home, preserving permissions. For example, restore a Codex config when that backup contains one:

```sh
cp -p "/path/to/backup/config.toml" "/path/to/codex-home/config.toml"
```

Restore other saved instruction and agent files the same way. Backups contain only changed files that already existed; remove newly created managed files manually if a complete rollback requires it. Do not replace unrelated files or delete the whole home directory. To verify a rolled-back version, use the corresponding repository revision.

## Access boundaries and high-risk work

Codex sandbox modes and Claude tool allowlists are different mechanisms, with no claim of equivalent isolation. Codex planner/reviewer agents request `read-only`; the worker requests `workspace-write`. Parent/runtime policy may constrain or override agent configuration.

Claude planner/reviewer agents have only `Read`, `Glob`, and `Grep`. The worker additionally has `Bash`, `Edit`, and `Write`. The adapters do not set `permissionMode`, allow `Agent` or MCP tools, or bypass permissions. Claude's read-only roles cannot run shell checks: the root must supply the final diff and verification evidence and resolve requests for missing evidence.

For high-risk implementation, the root must choose a suitably strong implementation path. A Codex custom worker's pinned Luna configuration takes precedence over a model override passed while spawning it; do not assume a spawn override elevates that worker. Use an appropriately configured Sol/Astra root or an explicitly selected strong default agent. Claude can explicitly select Opus for that work. This workflow does not automatically elevate a role or bypass runtime permissions.

## Test without changing live configuration

Run the integration suite:

```sh
python3 -m unittest discover -s tests -v
./install.sh --help
./verify.sh --help
git diff --check
```

Tests invoke the real wrappers using copied source trees and temporary homes. They cover both targets, migration, preservation, backup recovery, source and destination failures, and verification drift.

For a manual smoke test, use temporary homes explicitly:

```sh
workflow_test_dir=$(mktemp -d)
./install.sh --target both \
  --codex-home "$workflow_test_dir/codex" \
  --claude-home "$workflow_test_dir/claude"
./verify.sh --target both \
  --codex-home "$workflow_test_dir/codex" \
  --claude-home "$workflow_test_dir/claude"
```

Inspect the generated files and backups there, then remove that temporary directory when finished. No live global installation is required for these checks.

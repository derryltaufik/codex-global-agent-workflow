#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import sys
import tomllib
from datetime import datetime
from pathlib import Path

START = "<!-- codex-global-agent-workflow:start -->"
END = "<!-- codex-global-agent-workflow:end -->"


def replace_managed_block(existing: str, workflow: str) -> str:
    workflow = workflow.strip()
    block = f"{START}\n{workflow}\n{END}"
    pattern = re.compile(
        rf"(?:\n*){re.escape(START)}.*?{re.escape(END)}(?:\n*)",
        re.DOTALL,
    )
    unmanaged = pattern.sub("\n", existing)

    # Migrate installations created before managed markers were introduced.
    # Remove only exact copies of this workflow, preserving all other guidance.
    unmanaged = unmanaged.replace(workflow, "")
    unmanaged = unmanaged.strip()
    if unmanaged:
        return f"{unmanaged}\n\n{block}\n"
    return f"{block}\n"


def update_agents_config(existing: str) -> str:
    lines = existing.splitlines()
    section_start = None
    section_end = len(lines)

    for index, line in enumerate(lines):
        if line.strip() == "[agents]":
            section_start = index
            for later in range(index + 1, len(lines)):
                stripped = lines[later].strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    section_end = later
                    break
            break

    desired = {
        "enabled": "enabled = true",
        "max_concurrent_threads_per_session": "max_concurrent_threads_per_session = 3",
    }

    if section_start is None:
        suffix = "" if not existing.strip() else "\n\n"
        return existing.rstrip() + suffix + "[agents]\nenabled = true\nmax_concurrent_threads_per_session = 3\n"

    found: set[str] = set()
    for index in range(section_start + 1, section_end):
        match = re.match(r"\s*([A-Za-z0-9_]+)\s*=", lines[index])
        if match and match.group(1) in desired:
            key = match.group(1)
            lines[index] = desired[key]
            found.add(key)

    insert_at = section_end
    for key, value in desired.items():
        if key not in found:
            lines.insert(insert_at, value)
            insert_at += 1

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: install.py REPOSITORY_ROOT")

    source = Path(sys.argv[1]).resolve()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    agents_dir = codex_home / "agents"
    config_path = codex_home / "config.toml"
    instructions_path = codex_home / "AGENTS.md"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = codex_home / "backups" / f"global-agent-workflow-{stamp}"

    agents_dir.mkdir(parents=True, exist_ok=True)
    (backup / "agents").mkdir(parents=True, exist_ok=True)

    for path in (config_path, instructions_path):
        if path.exists():
            shutil.copy2(path, backup / path.name)

    for name in ("planner.toml", "worker.toml", "reviewer.toml"):
        destination = agents_dir / name
        if destination.exists():
            shutil.copy2(destination, backup / "agents" / name)

        source_agent = source / "agents" / name
        tomllib.loads(source_agent.read_text(encoding="utf-8"))
        shutil.copy2(source_agent, destination)

    current_instructions = instructions_path.read_text(encoding="utf-8") if instructions_path.exists() else ""
    workflow = (source / "AGENTS.workflow.md").read_text(encoding="utf-8")
    instructions_path.write_text(replace_managed_block(current_instructions, workflow), encoding="utf-8")

    current_config = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    updated_config = update_agents_config(current_config)
    tomllib.loads(updated_config)
    config_path.write_text(updated_config, encoding="utf-8")
    config_path.chmod(0o600)

    print(f"Installed global Codex workflow in {codex_home}")
    print(f"Backup: {backup}")
    print("Restart Codex to load the updated agents and instructions.")


if __name__ == "__main__":
    main()

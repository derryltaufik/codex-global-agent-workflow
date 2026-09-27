#!/usr/bin/env python3
from __future__ import annotations

import os
import tomllib
from pathlib import Path

START = "<!-- codex-global-agent-workflow:start -->"
END = "<!-- codex-global-agent-workflow:end -->"


def main() -> None:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    config = tomllib.loads((codex_home / "config.toml").read_text(encoding="utf-8"))
    agents = config.get("agents", {})
    assert agents.get("enabled") is True, "multi-agent support is not enabled"
    assert agents.get("max_concurrent_threads_per_session") == 3, "unexpected thread cap"

    expected = {
        "planner.toml": ("planner", "gpt-6-sol", "xhigh"),
        "worker.toml": ("worker", "gpt-6-luna", "high"),
        "reviewer.toml": ("reviewer", "gpt-6-sol", "high"),
    }
    for filename, (name, model, effort) in expected.items():
        data = tomllib.loads((codex_home / "agents" / filename).read_text(encoding="utf-8"))
        assert data.get("name") == name, f"invalid agent name in {filename}"
        assert data.get("model") == model, f"unexpected model in {filename}"
        assert data.get("model_reasoning_effort") == effort, f"unexpected reasoning effort in {filename}"
        for required in ("description", "developer_instructions"):
            assert data.get(required), f"missing {required} in {filename}"

    instructions = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
    assert instructions.count(START) == 1, "expected exactly one workflow start marker"
    assert instructions.count(END) == 1, "expected exactly one workflow end marker"
    print(f"Verified global Codex workflow in {codex_home}")


if __name__ == "__main__":
    main()

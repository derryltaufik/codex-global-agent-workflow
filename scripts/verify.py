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
        "planner.toml": "planner",
        "worker.toml": "worker",
        "reviewer.toml": "reviewer",
    }
    for filename, name in expected.items():
        data = tomllib.loads((codex_home / "agents" / filename).read_text(encoding="utf-8"))
        assert data.get("name") == name, f"invalid agent name in {filename}"
        for required in ("description", "developer_instructions"):
            assert data.get(required), f"missing {required} in {filename}"

    instructions = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
    assert START in instructions and END in instructions, "managed workflow block is missing"
    print(f"Verified global Codex workflow in {codex_home}")


if __name__ == "__main__":
    main()

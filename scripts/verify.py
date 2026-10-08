#!/usr/bin/env python3
from __future__ import annotations

import sys

from common import (WorkflowError, arguments, destination_text, load_sources, selected_homes,
                    validate_home, verify_config, verify_workflow)


def main() -> None:
    args = arguments('Verify installed native agents and workflow against this checkout.')
    homes = selected_homes(args)
    sources = load_sources(args.repository_root, homes)
    for target, home in homes.items():
        validate_home(home)
        instruction = home / ('AGENTS.md' if target == 'codex' else 'CLAUDE.md')
        content = destination_text(instruction)
        if content is None:
            raise WorkflowError(f'{instruction}: missing instructions')
        verify_workflow(content, sources, str(instruction))
        suffix = '.toml' if target == 'codex' else '.md'
        for role, expected in sources.roles[target].items():
            path = home / 'agents' / f'{role}{suffix}'
            if destination_text(path) != expected:
                raise WorkflowError(f'{path}: installed agent differs from shared prompt or adapter metadata')
        if target == 'codex':
            path = home / 'config.toml'
            config = destination_text(path)
            if config is None:
                raise WorkflowError(f'{path}: missing config')
            verify_config(config)
            if path.stat().st_mode & 0o777 != 0o600:
                raise WorkflowError(f'{path}: expected permissions 0600')
        print(f'Verified global {target} workflow in {home}')


if __name__ == '__main__':
    try:
        main()
    except (WorkflowError, OSError, UnicodeError) as error:
        print(f'Verification failed: {error}', file=sys.stderr)
        raise SystemExit(1)

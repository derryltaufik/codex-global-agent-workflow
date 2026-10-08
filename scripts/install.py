#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from common import WorkflowError, arguments, load_sources, prepare_changes, selected_homes


def atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    args = arguments('Install the shared global workflow and native agents.')
    homes = selected_homes(args)
    sources = load_sources(args.repository_root, homes)
    changes = prepare_changes(homes, sources)
    # Every selected source and destination is validated before creating backups
    # or changing any home. Back up all changed existing files before writes.
    backups = {}
    for change in changes:
        if change.previous is None:
            continue
        if change.target not in backups:
            parent = change.home / 'backups'
            parent.mkdir(parents=True, exist_ok=True)
            backups[change.target] = Path(tempfile.mkdtemp(prefix='global-agent-workflow-', dir=parent))
        backup = backups[change.target] / change.path.relative_to(change.home)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(change.path, backup)
    for change in changes:
        atomic_write(change.path, change.content, change.mode)
    for target, home in homes.items():
        count = sum(change.target == target for change in changes)
        print(f'Installed global {target} workflow in {home} ({count} files changed)')
        if target in backups:
            print(f'Backup: {backups[target]}')
    print('Restart the selected CLI(s) to load the updated agents and instructions.')


if __name__ == '__main__':
    try:
        main()
    except (WorkflowError, OSError, UnicodeError) as error:
        print(f'Install failed: {error}', file=sys.stderr)
        raise SystemExit(1)

"""Shared source validation, native rendering, and safe destination preparation."""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROLES = ('planner', 'worker', 'reviewer')
SUPPORTED_EFFORTS = frozenset({'low', 'medium', 'high', 'xhigh', 'max'})
START = '<!-- global-agent-workflow:start -->'
END = '<!-- global-agent-workflow:end -->'
OLD_START = '<!-- codex-global-agent-workflow:start -->'
OLD_END = '<!-- codex-global-agent-workflow:end -->'
MARKERS = re.compile('|'.join(re.escape(x) for x in (START, END, OLD_START, OLD_END)))


class WorkflowError(ValueError):
    """A source or destination cannot be safely managed."""


def arguments(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('repository_root', nargs='?', type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument('--target', choices=('codex', 'claude', 'both'), default='codex')
    parser.add_argument('--codex-home', type=Path, help='override CODEX_HOME or ~/.codex')
    parser.add_argument('--claude-home', type=Path, help='override CLAUDE_CONFIG_DIR or ~/.claude')
    return parser.parse_args()


def selected_homes(args: argparse.Namespace) -> dict[str, Path]:
    result = {}
    for target in ('codex', 'claude') if args.target == 'both' else (args.target,):
        env = 'CODEX_HOME' if target == 'codex' else 'CLAUDE_CONFIG_DIR'
        override = getattr(args, f'{target}_home')
        home = override if override is not None else Path(os.environ.get(env) or Path.home() / f'.{target}')
        result[target] = home.expanduser().absolute()
    return result


def read_text(path: Path) -> str:
    # Preserve newlines in unmanaged content, including CRLF.
    with path.open(encoding='utf-8', newline='') as stream:
        return stream.read()


def parse_toml(text: str, label: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise WorkflowError(f'{label}: invalid TOML: {error}') from error


def require_directory(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise WorkflowError(f'{path}: expected a directory, not a symlink or other file type')


def destination_text(path: Path) -> str | None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise WorkflowError(f'{path}: managed destination must be a regular file')
    return read_text(path) if path.exists() else None


def validate_home(home: Path) -> None:
    # Validate ancestors too, before mkdir can encounter a file or follow a link.
    require_directory(home)
    for directory in home.parents:
        if directory.exists() and not directory.is_dir():
            raise WorkflowError(f'{directory}: expected a directory')
    for directory in (home / 'agents', home / 'backups'):
        require_directory(directory)


def role_sources(directory: Path, suffix: str) -> None:
    expected = {f'{role}{suffix}' for role in ROLES}
    actual = {path.name for path in directory.glob(f'*{suffix}')}
    if actual != expected:
        raise WorkflowError(f'{directory}: expected exactly {sorted(expected)}, found {sorted(actual)}')


def metadata(source: Path, target: str, role: str) -> dict:
    path = source / 'adapters' / target / f'{role}.toml'
    data = parse_toml(read_text(path), str(path))
    keys = {'name', 'description', 'model'} | (
        {'model_reasoning_effort', 'sandbox_mode'} if target == 'codex' else {'effort', 'tools'})
    if set(data) != keys:
        raise WorkflowError(f'{path}: expected metadata fields {sorted(keys)}')
    for key in keys - {'tools'}:
        if not isinstance(data[key], str) or not data[key].strip():
            raise WorkflowError(f'{path}: {key} must be a nonempty string')
    if data['name'] != role:
        raise WorkflowError(f'{path}: name must be {role!r}')
    effort_key = 'model_reasoning_effort' if target == 'codex' else 'effort'
    if data[effort_key] not in SUPPORTED_EFFORTS:
        raise WorkflowError(f'{path}: {effort_key} must be one of {sorted(SUPPORTED_EFFORTS)}')
    if target == 'codex':
        sandbox = 'workspace-write' if role == 'worker' else 'read-only'
        if data['sandbox_mode'] != sandbox:
            raise WorkflowError(f'{path}: expected sandbox {sandbox!r}')
    else:
        tools = ['Read', 'Glob', 'Grep'] + (['Bash', 'Edit', 'Write'] if role == 'worker' else [])
        if data['tools'] != tools:
            raise WorkflowError(f'{path}: expected tools {tools!r}')
    return data


def render_role(data: dict, prompt: str, target: str) -> str:
    if target == 'codex':
        native = {**data, 'developer_instructions': prompt}
        result = ''.join(f'{key} = {json.dumps(value, ensure_ascii=False)}\n' for key, value in native.items())
        if parse_toml(result, 'rendered Codex agent') != native:
            raise WorkflowError('Codex agent could not be rendered losslessly')
        return result
    # JSON strings and arrays are valid YAML scalars and flow sequences.
    frontmatter = ''.join(f'{key}: {json.dumps(value, ensure_ascii=False)}\n' for key, value in data.items())
    return f'---\n{frontmatter}---\n\n{prompt}'


@dataclass(frozen=True)
class Sources:
    workflow: str
    legacy: str
    roles: dict[str, dict[str, str]]


def load_sources(source: Path, targets: dict[str, Path]) -> Sources:
    source = source.expanduser().resolve()
    workflow = read_text(source / 'shared/workflow.md').strip()
    legacy = read_text(source / 'shared/legacy/codex-workflow-v1.md').strip()
    if not workflow or not legacy or MARKERS.search(workflow) or MARKERS.search(legacy):
        raise WorkflowError('shared workflow and legacy snapshot must be nonempty and contain no managed markers')
    role_sources(source / 'shared/prompts', '.md')
    prompts = {}
    for role in ROLES:
        prompt = read_text(source / 'shared/prompts' / f'{role}.md').strip()
        if not prompt:
            raise WorkflowError(f'shared/prompts/{role}.md: prompt must be nonempty')
        prompts[role] = prompt + '\n'
    rendered = {}
    for target in targets:
        role_sources(source / 'adapters' / target, '.toml')
        rendered[target] = {role: render_role(metadata(source, target, role), prompts[role], target)
                            for role in ROLES}
    return Sources(workflow, legacy, rendered)


def managed_spans(text: str) -> list[tuple[int, int, str]]:
    spans = []
    opened = None
    for match in MARKERS.finditer(text):
        token = match.group()
        before = text[text.rfind('\n', 0, match.start()) + 1:match.start()]
        after = text[match.end():text.find('\n', match.end()) if '\n' in text[match.end():] else len(text)]
        if before.strip() or after.strip():
            raise WorkflowError('managed workflow markers must be on standalone lines')
        if token in (START, OLD_START):
            if opened is not None:
                raise WorkflowError('nested workflow start markers')
            opened = (match.start(), token)
        else:
            if opened is None:
                raise WorkflowError('workflow end marker has no matching start')
            begin, start = opened
            if (start == START) != (token == END):
                raise WorkflowError('mismatched legacy and neutral workflow markers')
            spans.append((begin, match.end(), start))
            opened = None
    if opened is not None:
        raise WorkflowError('workflow start marker has no matching end')
    return spans


def legacy_spans(text: str, legacy: str) -> list[tuple[int, int, str]]:
    # Only complete, exact paragraphs qualify. Modified historical guidance stays.
    pattern = re.compile(r'(?:\A|(?<=\n\n))' + re.escape(legacy) + r'(?=\n\n|\n?\Z)')
    return [(match.start(), match.end(), 'unmarked') for match in pattern.finditer(text)]


def replace_managed_block(existing: str, workflow: str, legacy: str) -> str:
    spans = managed_spans(existing)
    unmanaged = existing
    for begin, end, _ in reversed(spans):
        unmanaged = unmanaged[:begin] + (' ' * (end - begin)) + unmanaged[end:]
    spans += legacy_spans(unmanaged, legacy)
    spans.sort()
    block = f'{START}\n{workflow}\n{END}'
    if spans:
        pieces = []
        offset = 0
        for index, (begin, end, _) in enumerate(spans):
            pieces += [existing[offset:begin], block if index == 0 else '']
            offset = end
        return ''.join(pieces) + existing[offset:]
    separator = '' if not existing or existing.endswith('\n\n') else ('\n' if existing.endswith('\n') else '\n\n')
    return existing + separator + block + '\n'


def verify_workflow(existing: str, sources: Sources, label: str) -> None:
    spans = managed_spans(existing)
    if len(spans) != 1 or spans[0][2] != START:
        raise WorkflowError(f'{label}: expected exactly one neutral workflow block')
    begin, end, _ = spans[0]
    if existing[begin:end] != f'{START}\n{sources.workflow}\n{END}':
        raise WorkflowError(f'{label}: workflow content differs from shared/workflow.md')
    if replace_managed_block(existing, sources.workflow, sources.legacy) != existing:
        raise WorkflowError(f'{label}: obsolete unmarked workflow copy remains')


def update_agents_config(existing: str) -> str:
    original = parse_toml(existing, 'config.toml')
    if 'agents' in original and not isinstance(original['agents'], dict):
        raise WorkflowError('config.toml: agents must be a table')
    lines = existing.splitlines(keepends=True)
    headers = [index for index, line in enumerate(lines)
               if re.fullmatch(r'[ \t]*\[agents\][ \t]*(?:#[^\r\n]*)?(?:\r?\n)?', line)]
    newline = '\r\n' if '\r\n' in existing else '\n'
    desired = {'enabled': 'true', 'max_concurrent_threads_per_session': '3'}
    if not headers:
        if 'agents' in original:
            raise WorkflowError('config.toml: unsupported agents table layout; use a plain [agents] section')
        separator = '' if not existing or existing.endswith(newline * 2) else (newline if existing.endswith(newline) else newline * 2)
        candidate = existing + separator + '[agents]' + newline + ''.join(f'{key} = {value}{newline}' for key, value in desired.items())
    else:
        begin = headers[0] + 1
        if not lines[begin - 1].endswith(('\n', '\r')):
            lines[begin - 1] += newline
        end = next((index for index in range(begin, len(lines)) if re.match(r'\s*\[', lines[index])), len(lines))
        found = set()
        edits = []
        canonical_exists = 'max_concurrent_threads_per_session' in original.get('agents', {})
        for line in lines[begin:end]:
            match = re.fullmatch(r'([ \t]*)([A-Za-z0-9_]+)([ \t]*=[ \t]*)([^#\r\n]*)(#[^\r\n]*)?(\r?\n)?', line)
            if not match or match[2] not in {*desired, 'max_threads'}:
                edits.append(line)
                continue
            indent, key, equals, value, comment, ending = match.groups()
            if key == 'max_threads' and canonical_exists:
                edits.append(f'{indent}{comment}{ending or ""}' if comment else '')
                continue
            if key == 'max_threads':
                key = 'max_concurrent_threads_per_session'
            tail = value[len(value.rstrip()):]
            edits.append(f'{indent}{key}{equals}{desired[key]}{tail}{comment or ""}{ending or ""}')
            found.add(key)
        if edits and not edits[-1].endswith(('\n', '\r')):
            edits[-1] += newline
        edits.extend(f'{key} = {value}{newline}' for key, value in desired.items() if key not in found)
        candidate = ''.join(lines[:begin] + edits + lines[end:])
    expected = copy.deepcopy(original)
    expected.setdefault('agents', {}).update(enabled=True, max_concurrent_threads_per_session=3)
    expected['agents'].pop('max_threads', None)
    if parse_toml(candidate, 'updated config.toml') != expected:
        raise WorkflowError('config.toml: unsupported layout; unrelated settings could not be preserved')
    return candidate


def verify_config(text: str) -> None:
    agents = parse_toml(text, 'config.toml').get('agents')
    if not isinstance(agents, dict) or agents.get('enabled') is not True:
        raise WorkflowError('config.toml: multi-agent support is not enabled')
    cap = agents.get('max_concurrent_threads_per_session')
    if type(cap) is not int or cap != 3 or 'max_threads' in agents:
        raise WorkflowError('config.toml: expected thread cap 3 and no obsolete max_threads alias')


@dataclass(frozen=True)
class Change:
    target: str
    home: Path
    path: Path
    content: str
    previous: str | None
    mode: int


def prepare_changes(homes: dict[str, Path], sources: Sources) -> list[Change]:
    changes = []
    for target, home in homes.items():
        validate_home(home)
        instruction_path = home / ('AGENTS.md' if target == 'codex' else 'CLAUDE.md')
        previous = destination_text(instruction_path)
        expected = {instruction_path: replace_managed_block(previous or '', sources.workflow, sources.legacy)}
        suffix = '.toml' if target == 'codex' else '.md'
        expected.update({home / 'agents' / f'{role}{suffix}': text for role, text in sources.roles[target].items()})
        if target == 'codex':
            config_path = home / 'config.toml'
            expected[config_path] = update_agents_config(destination_text(config_path) or '')
        for path, content in expected.items():
            previous = destination_text(path)
            old_mode = stat.S_IMODE(path.stat().st_mode) if previous is not None else 0o644
            mode = 0o600 if path == home / 'config.toml' else old_mode
            if previous != content or old_mode != mode:
                changes.append(Change(target, home, path, content, previous, mode))
    return changes

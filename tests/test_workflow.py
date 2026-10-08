"""Integration tests: every install/verify runs the real CLI in isolated homes."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
START = '<!-- global-agent-workflow:start -->'
END = '<!-- global-agent-workflow:end -->'
OLD_START = '<!-- codex-global-agent-workflow:start -->'
OLD_END = '<!-- codex-global-agent-workflow:end -->'


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='agent-workflow-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'checkout with spaces'
        shutil.copytree(REPOSITORY, self.source, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        self.codex = self.base / 'codex home'
        self.claude = self.base / 'claude home'
        self.env = dict(os.environ, CODEX_HOME=str(self.codex), CLAUDE_CONFIG_DIR=str(self.claude),
                        HOME=str(self.base / 'fallback home'), PYTHONDONTWRITEBYTECODE='1')

    def run_cli(self, command, *args, success=True, env=None):
        result = subprocess.run([str(self.source / f'{command}.sh'), *map(str, args)],
                                cwd=self.base, env=env or self.env, capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result.stderr.strip())
        return result

    def put(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def snapshot(self, home):
        if not home.exists():
            return None
        return {str(path.relative_to(home)): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                for path in home.rglob('*') if path.is_file()}

    def backups(self, home):
        parent = home / 'backups'
        return sorted(parent.iterdir()) if parent.exists() else []

    def instruction(self, target):
        return (self.codex / 'AGENTS.md') if target == 'codex' else (self.claude / 'CLAUDE.md')

    def test_fresh_update_and_idempotence_for_each_target_and_both(self):
        for target in ('codex', 'claude', 'both'):
            with self.subTest(target=target):
                shutil.rmtree(self.codex, ignore_errors=True)
                shutil.rmtree(self.claude, ignore_errors=True)
                self.run_cli('install', '--target', target)
                self.run_cli('verify', '--target', target)
                selected = ('codex', 'claude') if target == 'both' else (target,)
                for name in selected:
                    home = getattr(self, name)
                    self.assertEqual(self.backups(home), [])
                    self.assertEqual(len(list((home / 'agents').iterdir())), 3)
                before = (self.snapshot(self.codex), self.snapshot(self.claude))
                self.run_cli('install', '--target', target)
                self.assertEqual(before, (self.snapshot(self.codex), self.snapshot(self.claude)))
                prompt = self.source / 'shared/prompts/worker.md'
                prompt.write_text(prompt.read_text() + '\nAdditional bounded instruction.\n')
                self.run_cli('verify', '--target', target, success=False)
                self.run_cli('install', '--target', target)
                self.run_cli('verify', '--target', target)
                for name in selected:
                    self.assertEqual(len(self.backups(getattr(self, name))), 1)

    def test_default_codex_and_positional_python_compatibility(self):
        self.run_cli('install')
        self.run_cli('verify')
        self.assertFalse(self.claude.exists())
        for command in ('install', 'verify'):
            result = subprocess.run(['python3', str(self.source / 'scripts' / f'{command}.py'), str(self.source)],
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        data = tomllib.loads((self.codex / 'agents/planner.toml').read_text())
        self.assertEqual(data['model'], 'gpt-6-astra')
        self.assertEqual(data['model_reasoning_effort'], 'xhigh')
        self.assertEqual(data['sandbox_mode'], 'read-only')

    def test_flags_override_environment_and_fallback_homes(self):
        alternate_codex, alternate_claude = self.base / 'explicit codex', self.base / 'explicit claude'
        args = ('--target', 'both', '--codex-home', alternate_codex, '--claude-home', alternate_claude)
        self.run_cli('install', *args)
        self.run_cli('verify', *args)
        self.assertFalse(self.codex.exists())
        self.assertFalse(self.claude.exists())
        env = {key: value for key, value in self.env.items() if key not in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR')}
        self.run_cli('install', '--target', 'both', env=env)
        self.run_cli('verify', '--target', 'both', env=env)
        self.assertTrue((Path(env['HOME']) / '.codex/AGENTS.md').exists())
        self.assertTrue((Path(env['HOME']) / '.claude/CLAUDE.md').exists())

    def test_unmanaged_content_settings_auth_agents_and_config_preserved(self):
        config = '# leading comment\nmodel = "custom" # keep model\n\n[agents] # routing\nenabled = false # enable comment\nmax_threads = 9 # old cap comment\ncustom = [1, 2]\n\n[agents.other]\nconfig_file = "other.toml"\n\n[features]\nthing = true # final comment\n'
        self.put(self.codex / 'config.toml', config)
        self.put(self.codex / 'agents/other.toml', 'custom unrelated agent\n')
        self.put(self.claude / 'agents/other.md', 'custom unrelated agent\n')
        unmanaged = '\n# User instructions\n\nPreserve these exact spaces.  \n'
        for target in ('codex', 'claude'):
            self.put(self.instruction(target), unmanaged)
        for filename in ('settings.json', '.credentials.json', 'auth.json'):
            self.put(self.claude / filename, 'opaque user data: '+filename)
        protected = {path: path.read_bytes() for path in self.claude.iterdir() if path.is_file() and path.name != 'CLAUDE.md'}
        self.run_cli('install', '--target', 'both')
        self.run_cli('verify', '--target', 'both')
        installed = (self.codex / 'config.toml').read_text()
        self.assertIn('enabled = true # enable comment', installed)
        self.assertIn('max_concurrent_threads_per_session = 3 # old cap comment', installed)
        self.assertIn('[agents] # routing', installed)
        self.assertIn('[features]\nthing = true # final comment\n', installed)
        self.assertEqual(tomllib.loads(installed)['agents']['other'], {'config_file': 'other.toml'})
        self.assertEqual(stat.S_IMODE((self.codex / 'config.toml').stat().st_mode), 0o600)
        for target in ('codex', 'claude'):
            self.assertTrue(self.instruction(target).read_text().startswith(unmanaged))
        for path, content in protected.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual((self.codex / 'agents/other.toml').read_text(), 'custom unrelated agent\n')
        self.assertEqual((self.claude / 'agents/other.md').read_text(), 'custom unrelated agent\n')

    def test_alias_and_canonical_together_preserve_comments(self):
        self.put(self.codex / 'config.toml', '[agents]\nmax_threads = 10 # alias note\nmax_concurrent_threads_per_session = 8 # cap note\n')
        self.run_cli('install')
        text = (self.codex / 'config.toml').read_text()
        self.assertIn('# alias note', text)
        self.assertIn('max_concurrent_threads_per_session = 3 # cap note', text)
        self.assertNotIn('max_threads', tomllib.loads(text)['agents'])
        self.run_cli('verify')

    def test_empty_agents_header_without_newline(self):
        self.put(self.codex / 'config.toml', '[agents]')
        self.run_cli('install')
        self.run_cli('verify')

    def test_crlf_unmanaged_text_preserved(self):
        raw = b'# User\r\n\r\nKeep this.\r\n'
        self.codex.mkdir()
        (self.codex / 'AGENTS.md').write_bytes(raw)
        (self.codex / 'config.toml').write_bytes(b'# custom\r\n[agents]\r\nenabled = false # note\r\n')
        self.run_cli('install')
        self.run_cli('verify')
        self.assertTrue((self.codex / 'AGENTS.md').read_bytes().startswith(raw))
        self.assertIn(b'enabled = true # note\r\n', (self.codex / 'config.toml').read_bytes())

    def test_old_mixed_duplicate_and_unmarked_migrations(self):
        legacy = (self.source / 'shared/legacy/codex-workflow-v1.md').read_text().strip()
        old = f'{OLD_START}\nobsolete content\n{OLD_END}'
        neutral = f'{START}\nobsolete content\n{END}'
        for text in (old, old+'\n\n'+neutral+'\n\n'+old, legacy, legacy+'\n\n'+legacy,
                     old+'\n\n'+legacy+'\n\n'+neutral):
            with self.subTest(text=text[:60]):
                self.put(self.claude / 'CLAUDE.md', '# Before\n\n'+text+'\n\n# After\n')
                self.run_cli('install', '--target', 'claude')
                self.run_cli('verify', '--target', 'claude')
                installed = (self.claude / 'CLAUDE.md').read_text()
                self.assertEqual(installed.count(START), 1)
                self.assertNotIn(OLD_START, installed)
                self.assertNotIn('obsolete content', installed)
                self.assertIn('# Before\n\n', installed)
                self.assertTrue(installed.endswith('\n\n# After\n'))

    def test_modified_unmarked_historical_text_preserved(self):
        legacy = (self.source / 'shared/legacy/codex-workflow-v1.md').read_text().strip()
        modified = legacy.replace('root agent owns', 'lead agent owns')
        embedded = 'Prefix on the same line '+legacy+' suffix on the same line'
        for text in (modified, embedded):
            self.put(self.claude / 'CLAUDE.md', text)
            self.run_cli('install', '--target', 'claude')
            self.run_cli('verify', '--target', 'claude')
            self.assertTrue((self.claude / 'CLAUDE.md').read_text().startswith(text))

    def test_malformed_second_target_markers_prevent_all_mutation(self):
        malformed = (START, END, END+'\n'+START, START+'\n'+START+'\n'+END+'\n'+END,
                     START+'\n'+OLD_END, OLD_START+'\n'+END, 'prefix '+START+'\n'+END)
        for text in malformed:
            with self.subTest(text=text):
                self.put(self.codex / 'config.toml', '# pristine\n')
                self.put(self.claude / 'CLAUDE.md', text)
                before = (self.snapshot(self.codex), self.snapshot(self.claude))
                self.run_cli('install', '--target', 'both', success=False)
                self.assertEqual(before, (self.snapshot(self.codex), self.snapshot(self.claude)))

    def test_bad_config_or_unsupported_layout_prevents_all_mutation(self):
        configs = ('[agents', 'agents = false\n', 'agents = {enabled = false}\n',
                   'agents.enabled = false\n', '["agents"]\nenabled = false\n',
                   '[agents]\n"enabled" = false\n')
        for config in configs:
            with self.subTest(config=config):
                self.put(self.codex / 'config.toml', config)
                before = (self.snapshot(self.codex), self.snapshot(self.claude))
                self.run_cli('install', '--target', 'both', success=False)
                self.assertEqual(before, (self.snapshot(self.codex), self.snapshot(self.claude)))

    def test_source_validation_prevents_all_mutation(self):
        path = self.source / 'adapters/claude/reviewer.toml'
        original = path.read_text()
        cases = ('broken = [', original.replace('name = "reviewer"', 'name = "wrong"'),
                 original.replace('effort = "high"', 'effort = "ultra"'),
                 original.replace('["Read", "Glob", "Grep"]', '["Read", "Bash"]'),
                 original+'permissionMode = "bypassPermissions"\n',
                 original.replace('model = "claude-opus-5-5"', 'model = 5'),
                 original.replace('description = ', 'extra_description = '))
        for text in cases:
            with self.subTest(text=text[-100:]):
                path.write_text(text)
                self.run_cli('install', '--target', 'both', success=False)
                self.assertIsNone(self.snapshot(self.codex))
                self.assertIsNone(self.snapshot(self.claude))
        path.write_text(original)
        for extra in ('adapters/claude/extra.toml', 'shared/prompts/extra.md'):
            extra_path = self.source / extra
            extra_path.write_text('unexpected source')
            self.run_cli('install', '--target', 'both', success=False)
            self.assertFalse(self.codex.exists())
            self.assertFalse(self.claude.exists())
            extra_path.unlink()

    def test_nonregular_second_target_destinations_prevent_all_mutation(self):
        self.put(self.claude / 'CLAUDE.md', '# original\n')
        external = self.base / 'external.md'
        external.write_text('untouched\n')
        bad = self.claude / 'agents/reviewer.md'
        bad.parent.mkdir()
        bad.symlink_to(external)
        self.run_cli('install', '--target', 'both', success=False)
        self.assertFalse(self.codex.exists())
        self.assertEqual(external.read_text(), 'untouched\n')
        self.assertEqual((self.claude / 'CLAUDE.md').read_text(), '# original\n')
        bad.unlink()
        bad.mkdir()
        self.run_cli('install', '--target', 'both', success=False)
        self.assertFalse(self.codex.exists())

    def test_unique_backups_recover_original_files(self):
        self.put(self.codex / 'config.toml', '# original config\n')
        self.put(self.codex / 'AGENTS.md', '# original instructions\n')
        self.put(self.codex / 'agents/worker.toml', 'old native worker\n')
        before = self.snapshot(self.codex)
        self.run_cli('install')
        first = self.backups(self.codex)[0]
        for relative, (content, mode) in before.items():
            backup = first / relative
            self.assertEqual(backup.read_bytes(), content)
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), mode)
        self.assertFalse((first / 'agents/planner.toml').exists())
        self.put(self.codex / 'agents/worker.toml', 'second old worker\n')
        self.run_cli('install')
        backups = self.backups(self.codex)
        self.assertEqual(len(backups), 2)
        second = next(path for path in backups if path != first)
        self.assertEqual((second / 'agents/worker.toml').read_text(), 'second old worker\n')
        for relative in before:
            shutil.copy2(first / relative, self.codex / relative)
        for relative, expected in before.items():
            self.assertEqual(self.snapshot(self.codex)[relative], expected)

    def test_all_native_drift_is_detected(self):
        self.run_cli('install', '--target', 'both')
        cases = [
            (self.codex / 'agents/planner.toml', 'gpt-6-astra', 'another-model'),
            (self.codex / 'agents/planner.toml', 'xhigh', 'low'),
            (self.codex / 'agents/reviewer.toml', 'read-only', 'workspace-write'),
            (self.codex / 'agents/worker.toml', 'Act as the implementation owner.', 'Changed prompt.'),
            (self.claude / 'agents/planner.md', 'claude-opus-5-5', 'claude-sonnet-5-5'),
            (self.claude / 'agents/reviewer.md', 'effort: "high"', 'effort: "low"'),
            (self.claude / 'agents/reviewer.md', '["Read", "Glob", "Grep"]', '["Read", "Glob", "Grep", "Bash"]'),
            (self.claude / 'agents/worker.md', 'Act as the implementation owner.', 'Changed prompt.'),
            (self.claude / 'agents/worker.md', '\n---\n\n', '\npermissionMode: bypassPermissions\n---\n\n'),
            (self.claude / 'CLAUDE.md', 'root agent owns', 'somebody owns'),
            (self.codex / 'config.toml', 'enabled = true', 'enabled = false'),
            (self.codex / 'config.toml', 'max_concurrent_threads_per_session = 3', 'max_concurrent_threads_per_session = 4'),
        ]
        for path, before, after in cases:
            with self.subTest(path=path.name, change=after):
                original = path.read_text()
                self.assertIn(before, original)
                path.write_text(original.replace(before, after, 1))
                self.run_cli('verify', '--target', 'both', success=False)
                path.write_text(original)
        self.run_cli('verify', '--target', 'both')
        config = self.codex / 'config.toml'
        config.chmod(0o644)
        self.run_cli('verify', success=False)
        self.run_cli('install')
        self.run_cli('verify')

    def test_verify_rejects_duplicate_legacy_and_unmarked_copies(self):
        self.run_cli('install', '--target', 'claude')
        path = self.claude / 'CLAUDE.md'
        original = path.read_text()
        legacy = (self.source / 'shared/legacy/codex-workflow-v1.md').read_text()
        for extra in (original, f'{OLD_START}\nold\n{OLD_END}\n', legacy):
            path.write_text(original+'\n'+extra)
            self.run_cli('verify', '--target', 'claude', success=False)
        path.write_text(original)
        self.run_cli('verify', '--target', 'claude')

    def test_custom_model_ids_use_adapter_source(self):
        for target in ('codex', 'claude'):
            path = self.source / 'adapters' / target / 'worker.toml'
            text = path.read_text()
            old = 'gpt-6-luna' if target == 'codex' else 'claude-sonnet-5-5'
            path.write_text(text.replace(old, 'custom-provider-model'))
        self.run_cli('install', '--target', 'both')
        self.run_cli('verify', '--target', 'both')
        self.assertIn('custom-provider-model', (self.codex / 'agents/worker.toml').read_text())
        self.assertIn('custom-provider-model', (self.claude / 'agents/worker.md').read_text())

    def test_supported_custom_efforts_install_and_verify_for_both_targets(self):
        for effort in ('low', 'medium', 'high', 'xhigh', 'max'):
            with self.subTest(effort=effort):
                for target in ('codex', 'claude'):
                    key = 'model_reasoning_effort' if target == 'codex' else 'effort'
                    for role in ('planner', 'worker', 'reviewer'):
                        adapter = self.source / 'adapters' / target / f'{role}.toml'
                        lines = adapter.read_text().splitlines()
                        adapter.write_text('\n'.join(f'{key} = "{effort}"' if line.startswith(f'{key} =')
                                                     else line for line in lines)+'\n')
                self.run_cli('install', '--target', 'both')
                self.run_cli('verify', '--target', 'both')
                for role in ('planner', 'worker', 'reviewer'):
                    native = tomllib.loads((self.codex / 'agents' / f'{role}.toml').read_text())
                    self.assertEqual(native['model_reasoning_effort'], effort)
                    self.assertIn(f'\neffort: "{effort}"\n', (self.claude / 'agents' / f'{role}.md').read_text())

    def test_invalid_custom_efforts_fail_without_mutating_either_home(self):
        self.run_cli('install', '--target', 'both')
        before = (self.snapshot(self.codex), self.snapshot(self.claude))
        for target in ('codex', 'claude'):
            path = self.source / 'adapters' / target / 'worker.toml'
            original = path.read_text()
            key = 'model_reasoning_effort' if target == 'codex' else 'effort'
            for invalid in ('ultra', 'none', 'High', '', 1):
                with self.subTest(target=target, effort=invalid):
                    path.write_text(original.replace(f'{key} = "high"', f'{key} = {json.dumps(invalid)}'))
                    self.run_cli('install', '--target', 'both', success=False)
                    self.run_cli('verify', '--target', 'both', success=False)
                    self.assertEqual(before, (self.snapshot(self.codex), self.snapshot(self.claude)))
                    self.assertEqual(self.backups(self.codex), [])
                    self.assertEqual(self.backups(self.claude), [])
            path.write_text(original)
        self.run_cli('verify', '--target', 'both')

    def test_rendered_prompts_are_standalone_and_support_unicode(self):
        prompt = 'Read "quoted" paths and Unicode 🧪 correctly.\nKeep a backslash: \\.\n'
        self.put(self.source / 'shared/prompts/worker.md', prompt)
        description = 'Bounded worker: "review #1" 🧪'
        for target in ('codex', 'claude'):
            adapter = self.source / 'adapters' / target / 'worker.toml'
            lines = adapter.read_text().splitlines()
            adapter.write_text('\n'.join('description = '+json.dumps(description, ensure_ascii=False)
                                         if line.startswith('description =') else line for line in lines)+'\n')
        self.run_cli('install', '--target', 'both')
        self.run_cli('verify', '--target', 'both')
        codex = tomllib.loads((self.codex / 'agents/worker.toml').read_text())
        self.assertEqual(codex['developer_instructions'], prompt)
        self.assertEqual(codex['description'], description)
        claude = (self.claude / 'agents/worker.md').read_text()
        self.assertTrue(claude.endswith('---\n\n'+prompt))
        self.assertNotIn(str(self.source), claude)
        self.assertNotIn(str(self.source), codex['developer_instructions'])

    def test_unselected_malformed_home_and_adapter_are_ignored(self):
        self.put(self.codex / 'config.toml', 'invalid = [')
        self.put(self.source / 'adapters/codex/worker.toml', 'invalid = [')
        before = self.snapshot(self.codex)
        self.run_cli('install', '--target', 'claude')
        self.run_cli('verify', '--target', 'claude')
        self.assertEqual(before, self.snapshot(self.codex))
        self.put(self.claude / 'CLAUDE.md', START)
        self.put(self.source / 'adapters/codex/worker.toml', (REPOSITORY / 'adapters/codex/worker.toml').read_text())
        self.put(self.codex / 'config.toml', '')
        before = self.snapshot(self.claude)
        self.run_cli('install')
        self.run_cli('verify')
        self.assertEqual(before, self.snapshot(self.claude))

    def test_help_and_optimized_python_still_enforce_verification(self):
        for command in ('install', 'verify'):
            self.assertIn('--target', self.run_cli(command, '--help').stdout)
        self.run_cli('install')
        self.put(self.codex / 'agents/worker.toml', 'invalid')
        env = dict(self.env, PYTHONOPTIMIZE='1')
        self.run_cli('verify', success=False, env=env)


if __name__ == '__main__':
    unittest.main()

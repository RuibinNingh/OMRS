"""门禁必须实际执行带参数的联调，并如实报告环境跳过。"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests import run_gates
from tests.run_gates import execution_status, gates


class GateExecutionTests(unittest.TestCase):
    def test_integration_outputs_are_distinct_and_helper_is_not_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            entries = {name: (group, command) for group, name, command in gates('HEAD', out=temp)}
            self.assertNotIn('e2e-zuoyebang_paper', entries)
            direct = entries['e2e-zuoyebang_gateway_integration'][1]
            prefix = entries['e2e-zuoyebang_gateway_prefix'][1]
            self.assertEqual(Path(direct[direct.index('--out') + 1]), Path(temp) / 'integration-direct')
            self.assertEqual(Path(prefix[prefix.index('--out') + 1]), Path(temp) / 'integration-prefix')
            self.assertIn('--with-prefix', prefix)
            self.assertTrue({'gateway-unit', 'boxdetect-unit', 'gateway-browser'} <= entries.keys())

    def test_successful_process_with_skipped_dependency_is_not_passed(self):
        self.assertEqual(execution_status(0, 'SKIP 缺少MCP SDK')[0], 'skipped')
        self.assertEqual(execution_status(0, 'OK (skipped=2)')[0], 'skipped')
        self.assertEqual(execution_status(0, '# skipped 0\nOK')[0], 'passed')
        self.assertEqual(execution_status(1, 'SKIP 缺少MCP SDK')[0], 'failed')
        self.assertEqual(execution_status(0, '5 passed, 1 skipped in 1s')[0], 'skipped')
        self.assertEqual(execution_status(0, '# skipped 1')[0], 'skipped')

    def test_dataset_cannot_fall_back_to_local_training_directory(self):
        with self.assertRaisesRegex(ValueError, '冻结train_dir'):
            gates('HEAD', dataset='/synthetic/dataset')
        entries = {name: command for _, name, command in gates('HEAD', dataset='/synthetic/dataset', train_dir='/synthetic/train')}
        command = entries['e2e-boxdetect']
        self.assertEqual(command[command.index('--train-dir') + 1], '/synthetic/train')

    def test_main_rejects_empty_selections_without_executing_or_reporting_success(self):
        cases = [(['--groups', 'unit', '--only', 'e2e-ai_review'], '没有共同的可执行门禁'),
                 (['--groups', ' , '], '--groups至少指定一个门禁组'),
                 (['--groups', 'unit', '--only', ' , '], '--only至少指定一个门禁ID')]
        for arguments, reason in cases:
            with self.subTest(arguments=arguments), tempfile.TemporaryDirectory() as temp:
                errors = io.StringIO()
                argv = ['run_gates.py', '--out', temp, *arguments]
                with patch.object(sys, 'argv', argv), patch.object(run_gates.subprocess, 'run') as execute:
                    with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                        run_gates.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(reason, errors.getvalue())
                execute.assert_not_called()
                self.assertFalse((Path(temp) / 'results.json').exists())

    def test_main_resolves_output_before_entering_service_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp).resolve() / 'evidence'
            relative = os.path.relpath(destination, Path.cwd())
            command = [sys.executable, 'synthetic-browser.py']
            entries = [('services', 'gateway-browser', command)]
            argv = ['run_gates.py', '--groups', 'services', '--only', 'gateway-browser', '--out', relative]
            with (patch.object(sys, 'argv', argv),
                  patch.object(run_gates, 'gates', return_value=entries) as build,
                  patch.object(run_gates.subprocess, 'run', return_value=subprocess.CompletedProcess(command, 0)) as execute,
                  patch.dict(os.environ, {'OMRS_SYSTEMD_SERVICE': 'synthetic-only',
                                          'OMRS_BOXDETECT_CONTROL': 'synthetic-only'}),
                  redirect_stdout(io.StringIO())):
                self.assertEqual(run_gates.main(), 0)
            self.assertEqual(build.call_args.kwargs['out'], destination)
            execute.assert_called_once()
            self.assertEqual(execute.call_args.kwargs['cwd'], run_gates.ROOT / 'services/zuoyebang')
            child_env = execute.call_args.kwargs['env']
            self.assertNotIn('OMRS_SYSTEMD_SERVICE', child_env)
            self.assertNotIn('OMRS_BOXDETECT_CONTROL', child_env)
            for key in ('OMRS_E2E_SHOTS', 'OMRS_ZYB_SHOTS', 'ZYB_TEST_EVIDENCE_DIR'):
                self.assertEqual(child_env[key], str(destination / 'gateway-browser'))
                self.assertTrue(Path(child_env[key]).is_absolute())
            report = json.loads((destination / 'results.json').read_text(encoding='utf-8'))
            self.assertEqual(report['results'][0]['status'], 'passed')
            self.assertTrue(Path(report['results'][0]['log']).is_absolute())

    def test_main_uses_independent_camera_browser_only_for_zuoyebang(self):
        with tempfile.TemporaryDirectory() as temp:
            entries = [('e2e', 'e2e-zuoyebang', ['synthetic-camera']),
                       ('e2e', 'e2e-zuoyebang_service', ['synthetic-service']),
                       ('services', 'gateway-browser', ['synthetic-gateway'])]
            argv = ['run_gates.py', '--groups', 'e2e,services', '--out', temp]
            inherited = {'OMRS_TEST_CDP_URL': 'http://synthetic-cdp.invalid:9222',
                         'ZYB_TEST_CDP_URL': 'http://synthetic-gateway-cdp.invalid:9222'}
            with (patch.object(sys, 'argv', argv),
                  patch.object(run_gates, 'gates', return_value=entries),
                  patch.object(run_gates.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as execute,
                  patch.dict(os.environ, inherited), redirect_stdout(io.StringIO())):
                self.assertEqual(run_gates.main(), 0)
                for key, value in inherited.items():
                    self.assertEqual(os.environ[key], value)
            self.assertEqual(execute.call_count, 3)
            camera, service, gateway = [call.kwargs['env'] for call in execute.call_args_list]
            self.assertNotIn('OMRS_TEST_CDP_URL', camera)
            self.assertEqual(camera['ZYB_TEST_CDP_URL'], inherited['ZYB_TEST_CDP_URL'])
            for child in (service, gateway):
                for key, value in inherited.items():
                    self.assertEqual(child[key], value)

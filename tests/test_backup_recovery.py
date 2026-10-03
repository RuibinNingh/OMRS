"""真实磁盘/WAL备份、恢复故障与进程中断的行为回归。"""
import concurrent.futures
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

from omrs import backup_store as backup
from omrs.common import questions_root
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs.ledger import verify_ledger
from omrs.vault_lifecycle import (VaultBusy, VaultChanged, advance_generation, exclusive,
                                  generation, lease, maintenance_dir, open_sqlite, task)


class LifecycleTests(unittest.TestCase):
    def test_out_of_order_nested_connection_close_keeps_barrier(self):
        with tempfile.TemporaryDirectory() as vault:
            a = open_sqlite(vault, os.path.join(vault, 'a.db'))
            b = open_sqlite(vault, os.path.join(vault, 'b.db'))
            a.close()
            def maintain():
                with exclusive(vault, timeout=.05):
                    return True
            with concurrent.futures.ThreadPoolExecutor() as pool:
                with self.assertRaises(VaultBusy):
                    pool.submit(maintain).result(timeout=1)
                b.close()
                self.assertTrue(pool.submit(maintain).result(timeout=1))

    def test_task_rejects_old_generation_and_shared_upgrade(self):
        with tempfile.TemporaryDirectory() as vault:
            with lease(vault):
                with self.assertRaises(VaultBusy):
                    with exclusive(vault):
                        pass
            with task(vault):
                with exclusive(vault):
                    advance_generation(vault)
                with self.assertRaises(VaultChanged):
                    with lease(vault):
                        pass
            with lease(vault):
                pass

    def test_barrier_coordinates_independent_process(self):
        with tempfile.TemporaryDirectory() as vault:
            with lease(vault):
                child = subprocess.run([sys.executable, '-c',
                    'from omrs.vault_lifecycle import exclusive,VaultBusy; import sys\n'
                    'try:\n with exclusive(sys.argv[1],timeout=.1): pass\n'
                    'except VaultBusy: sys.exit(23)', vault], capture_output=True)
                self.assertEqual(child.returncode, 23, child.stderr)


class BackupRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-restore-test-')
        self.vault = str(Path(self.temp.name) / 'current')
        self.source = str(Path(self.temp.name) / 'source')
        os.makedirs(self.vault)
        os.makedirs(self.source)
        create_question(self.vault, '数学', '旧库', 5, question_text='old')
        create_question(self.source, '数学', '新库', 5, question_text='new')
        self.archive, _, _, self.frozen = backup.create_backup(self.source)
        self.addCleanup(lambda: os.path.exists(self.archive) and os.unlink(self.archive))
        self.addCleanup(self.temp.cleanup)

    def prepare(self):
        return backup.prepare_import(self.vault, self.archive)['restore_id']

    def test_snapshot_target_connect_failure_closes_source(self):
        opened = []
        connect = sqlite3.connect
        def fail_target(path, **kwargs):
            if opened:
                raise OSError('目标空间不足')
            db = connect(path, **kwargs)
            opened.append(db)
            return db
        with mock.patch.object(backup.sqlite3, 'connect', side_effect=fail_target):
            with self.assertRaises(OSError):
                backup._snapshot(Path(questions_root(self.source)) / '.omrs/ledger.db',
                                 Path(self.temp.name) / 'snapshot.db')
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute('SELECT 1')

    def test_backup_requires_guard_for_every_database(self):
        with self.assertRaisesRegex(ValueError, '数据库集合'):
            backup._capture_guarded(self.source, self.temp.name, {})

    def test_legacy_empty_inbox_placeholder_roundtrip_keeps_real_store(self):
        data = Path(questions_root(self.source)) / '.omrs'
        placeholder = data / 'inbox.db'
        placeholder.write_bytes(b'')
        actual = data / 'inbox' / 'inbox.db'
        actual.parent.mkdir()
        with contextlib.closing(sqlite3.connect(actual)) as db, db:
            db.execute('CREATE TABLE evidence(value TEXT)')
            db.execute("INSERT INTO evidence VALUES('实际收件箱数据')")
        archive, _, _, _ = backup.create_backup(self.source)
        try:
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(zipped.read('错题/.omrs/inbox.db'), b'')
                manifest = json.loads(zipped.read('错题/.omrs/backup_manifest.json'))
                files = {item['path']: item for item in manifest['files']}
                self.assertNotIn('sqlite_snapshot', files['错题/.omrs/inbox.db'])
                self.assertEqual(files['错题/.omrs/inbox/inbox.db']['sqlite_snapshot'], 'backup')
            prepared = backup.prepare_import(self.vault, archive)
            self.assertTrue(prepared['preview']['manifest_verified'])
            backup.restore(self.vault, prepared['restore_id'], True)
            restored = Path(questions_root(self.vault)) / '.omrs'
            self.assertEqual((restored / 'inbox.db').read_bytes(), b'')
            with contextlib.closing(sqlite3.connect(restored / 'inbox' / 'inbox.db')) as db:
                self.assertEqual(db.execute('SELECT value FROM evidence').fetchone()[0], '实际收件箱数据')
            self.assertTrue(verify_ledger(self.vault)['valid'])
        finally:
            os.unlink(archive)

    def test_placeholder_exception_does_not_accept_broken_active_or_nonempty_database(self):
        data = Path(questions_root(self.source)) / '.omrs'
        for relative, content in [('inbox/inbox.db', b''), ('inbox.db', '损坏数据库'.encode())]:
            with self.subTest(relative=relative):
                path = data / relative
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(content)
                try:
                    with self.assertRaisesRegex(ValueError, '数据库文件格式'):
                        backup.create_backup(self.source)
                finally:
                    path.unlink()

    def test_directory_only_zip_cannot_bypass_file_limit(self):
        path = Path(self.temp.name) / 'directories.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('错题/a/', '')
            archive.writestr('错题/b/', '')
        with zipfile.ZipFile(path) as archive, mock.patch.object(backup, 'MAX_FILES', 1):
            with self.assertRaisesRegex(ValueError, '数量'):
                backup._safe_names(archive, 1024**3)

    def category(self):
        return mastery_rows(self.vault)[0]['Category']

    def test_online_snapshot_includes_independent_wal_stores(self):
        data = Path(questions_root(self.source)) / '.omrs'
        connections = []
        try:
            for name in ['inbox/inbox.db', 'annotate/annotate.db', 'drafts/drafts.db', 'agent.db', 'runtime.db']:
                path = data / name
                path.parent.mkdir(parents=True, exist_ok=True)
                db = sqlite3.connect(path)
                connections.append(db)
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA wal_autocheckpoint=0')
                db.execute('CREATE TABLE snapshot_evidence(value TEXT)')
                db.execute("INSERT INTO snapshot_evidence VALUES('committed in WAL')")
                db.commit()
                self.assertTrue(Path(str(path)+'-wal').is_file())
            archive, _, _, _ = backup.create_backup(self.source)
            try:
                with zipfile.ZipFile(archive) as zipped:
                    manifest = json.loads(zipped.read('错题/.omrs/backup_manifest.json'))
                    self.assertEqual(manifest['format_version'], 2)
                    self.assertFalse(any(n.endswith(('-wal', '-shm')) for n in zipped.namelist()))
                    for name in ['inbox/inbox.db', 'annotate/annotate.db', 'drafts/drafts.db', 'agent.db', 'runtime.db']:
                        output = Path(self.temp.name) / ('proof-'+name.replace('/','-'))
                        output.write_bytes(zipped.read('错题/.omrs/'+name))
                        with contextlib.closing(sqlite3.connect(output)) as db:
                            self.assertEqual(db.execute('SELECT value FROM snapshot_evidence').fetchone()[0], 'committed in WAL')
            finally:
                os.unlink(archive)
        finally:
            for db in connections:
                db.close()

    def test_every_precommit_journal_failure_restores_old_library(self):
        for phase in ['prepared','old_moved','new_installed','committed']:
            with self.subTest(phase=phase):
                identity = self.prepare()
                original = backup.atomic_json
                def fail(path, value):
                    if path.endswith('restore-journal.json') and value.get('phase') == phase:
                        raise OSError('injected before '+phase)
                    return original(path, value)
                with mock.patch.object(backup, 'atomic_json', side_effect=fail):
                    with self.assertRaises(OSError):
                        backup.restore(self.vault, identity, True)
                self.assertEqual(self.category(), '旧库')
                self.assertTrue(verify_ledger(self.vault)['valid'])
                self.assertFalse(Path(maintenance_dir(self.vault), 'restore-journal.json').exists())

    def test_subprocess_interruption_obeys_commit_marker(self):
        code = ('import os,sys\nfrom omrs import backup_store as b\n'
                'real=b.atomic_json\n'
                'def stop(path,value):\n real(path,value)\n'
                ' if path.endswith("restore-journal.json") and value.get("phase")==sys.argv[3]: os._exit(71)\n'
                'b.atomic_json=stop\nb.restore(sys.argv[1],sys.argv[2],True)\n')
        for phase in ['prepared','old_moved','new_installed','committed']:
            with self.subTest(phase=phase):
                identity = self.prepare()
                child = subprocess.run([sys.executable,'-c',code,self.vault,identity,phase],capture_output=True)
                self.assertEqual(child.returncode,71,child.stderr)
                self.assertTrue(backup.recover_restore(self.vault))
                self.assertEqual(self.category(), '新库' if phase == 'committed' else '旧库')
                self.assertTrue(verify_ledger(self.vault)['valid'])

    def test_rename_and_directory_fsync_failure_roll_back(self):
        for step in ['old_rename','new_rename','fsync']:
            with self.subTest(step=step):
                identity = self.prepare()
                original_replace, original_sync = backup.os.replace, backup.fsync_dir
                fired = [False]
                def rename(source, destination):
                    relevant = ((step == 'old_rename' and str(source) == questions_root(self.vault)) or
                                (step == 'new_rename' and str(destination) == questions_root(self.vault)))
                    if relevant and not fired[0]:
                        fired[0] = True
                        raise OSError('injected rename')
                    return original_replace(source,destination)
                def sync(path):
                    if step == 'fsync' and str(path) == self.vault and not fired[0]:
                        fired[0] = True
                        raise OSError('injected fsync')
                    return original_sync(path)
                with mock.patch.object(backup.os,'replace',side_effect=rename), mock.patch.object(backup,'fsync_dir',side_effect=sync):
                    with self.assertRaises(OSError):
                        backup.restore(self.vault,identity,True)
                self.assertTrue(fired[0])
                self.assertEqual(self.category(),'旧库')

    def test_process_kill_between_rename_and_journal_update_is_recoverable(self):
        code = ('import os,sys\nfrom omrs import backup_store as b\nreal=b.os.replace\n'
                'def stop(source,dest):\n real(source,dest)\n'
                ' if str(source)==sys.argv[3] or str(dest)==sys.argv[4]: os._exit(73)\n'
                'b.os.replace=stop\nb.restore(sys.argv[1],sys.argv[2],True)\n')
        for which in ['old','new']:
            identity = self.prepare()
            target = questions_root(self.vault)
            child = subprocess.run([sys.executable,'-c',code,self.vault,identity,
                                    target if which=='old' else '',target if which=='new' else ''],capture_output=True)
            self.assertEqual(child.returncode,73,child.stderr)
            backup.recover_restore(self.vault)
            self.assertEqual(self.category(),'旧库')

    def test_prechecked_tree_mutation_and_bad_manifest_refused(self):
        identity = self.prepare()
        operation = Path(maintenance_dir(self.vault)) / identity
        question = next((operation/'staging/错题').rglob('新库1.md'))
        question.write_text('tampered', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '预检'):
            backup.restore(self.vault, identity, True)
        self.assertEqual(self.category(),'旧库')
        bad = Path(self.temp.name)/'bad.zip'
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(bad,'w') as target:
            for item in source.infolist():
                target.writestr(item, b'bad' if item.filename.endswith('新库1.md') else source.read(item))
        with self.assertRaisesRegex(ValueError,'哈希'):
            backup.prepare_import(self.vault,str(bad))

    def test_restore_inside_request_task_rebinds_only_maintenance_work(self):
        identity = self.prepare()
        with task(self.vault):
            result = backup.restore(self.vault,identity,True)
            self.assertTrue(result['restored'])
            with self.assertRaises(VaultChanged):
                with lease(self.vault):
                    pass
        self.assertEqual(self.category(),'新库')

    def test_postcommit_cleanup_failure_retains_new_library_and_is_recoverable(self):
        identity = self.prepare()
        real = backup._recover_locked
        with mock.patch.object(backup,'_recover_locked',side_effect=OSError('cleanup blocked')):
            result = backup.restore(self.vault,identity,True)
        self.assertTrue(result['cleanup_pending'])
        self.assertEqual(self.category(),'新库')
        self.assertTrue(backup.recover_restore(self.vault))
        self.assertTrue(backup.restore(self.vault,identity,True)['reused'])


if __name__ == '__main__':
    unittest.main()

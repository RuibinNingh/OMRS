"""独立 MCP Key 的跨进程生命周期、损坏数据与持久化安全。"""
import datetime
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from omrs.common import omrs_data_dir
from omrs.mcp import keys


def _create_worker(vault, index, start, output):
    start.wait(10)
    try:
        made = keys.create_key(vault, f"进程-{index}", ["omrs:read"])
        identity = keys.verify_key(vault, made["secret"])
        output.put({"key_id": made["key_id"], "verified": identity["key_id"]})
    except Exception as exc:
        output.put({"error": type(exc).__name__ + ":" + str(exc)})


def _verify_with_paused_save(vault, secret, entered, release, output):
    save = keys._save

    def paused_save(path, data):
        entered.set()
        if not release.wait(10):
            raise RuntimeError("测试等待超时")
        save(path, data)

    try:
        with mock.patch.object(keys, "_save", side_effect=paused_save):
            row = keys.verify_key(vault, secret)
        output.put({"verified": row["key_id"] if row else None})
    except Exception as exc:
        output.put({"error": type(exc).__name__ + ":" + str(exc)})


def _revoke_worker(vault, key_id, entered, finished, output):
    entered.set()
    try:
        result = keys.revoke_key(vault, key_id)
        output.put({"revoked": bool(result["revoked_at"])})
    except Exception as exc:
        output.put({"error": type(exc).__name__ + ":" + str(exc)})
    finally:
        finished.set()


class MCPKeyPersistenceTests(unittest.TestCase):
    def _path(self, vault):
        return Path(omrs_data_dir(vault)) / "mcp_keys.json"

    def _stop(self, processes):
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    def test_concurrent_process_create_and_verify_preserve_all_keys(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as vault:
            start, output = context.Event(), context.Queue()
            workers = [context.Process(target=_create_worker, args=(vault, index, start, output))
                       for index in range(8)]
            try:
                for worker in workers:
                    worker.start()
                start.set()
                results = [output.get(timeout=15) for _ in workers]
                for row in results:
                    self.assertNotIn("error", row)
                    self.assertEqual(row["key_id"], row["verified"])
                self._stop(workers)
                self.assertTrue(all(worker.exitcode == 0 for worker in workers))
                self.assertEqual({row["key_id"] for row in keys.list_keys(vault)},
                                 {row["key_id"] for row in results})
                self.assertEqual(len(keys.list_keys(vault)), 8)
            finally:
                self._stop(workers)
                output.close(); output.join_thread()

    def test_verification_save_cannot_overwrite_concurrent_process_revocation(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as vault:
            made = keys.create_key(vault, "验证与吊销竞态")
            entered, release = context.Event(), context.Event()
            revoke_started, revoke_finished = context.Event(), context.Event()
            output = context.Queue()
            verifier = context.Process(target=_verify_with_paused_save,
                args=(vault, made["secret"], entered, release, output))
            revoker = context.Process(target=_revoke_worker,
                args=(vault, made["key_id"], revoke_started, revoke_finished, output))
            workers = [verifier]
            try:
                verifier.start()
                self.assertTrue(entered.wait(10), "验证进程未进入使用时间写入")
                revoker.start(); workers.append(revoker)
                self.assertTrue(revoke_started.wait(10), "吊销进程未开始")
                # 验证已经读到旧记录，吊销必须等跨进程锁，而不是先写入后
                # 被验证进程的旧快照覆盖。事件控制避免依赖负载碰运气。
                self.assertFalse(revoke_finished.wait(0.25))
                release.set()
                results = [output.get(timeout=15) for _ in workers]
                self._stop(workers)
                self.assertTrue(all(worker.exitcode == 0 for worker in workers))
                self.assertTrue(all("error" not in row for row in results), results)
                self.assertIn({"revoked": True}, results)
                self.assertIsNone(keys.verify_key(vault, made["secret"]))
                for _ in range(5):
                    self.assertIsNone(keys.verify_key(vault, made["secret"]))
                self.assertTrue(keys.key_for_id(vault, made["key_id"])["revoked_at"])
            finally:
                release.set()
                self._stop(workers)
                output.close(); output.join_thread()

    @unittest.skipIf(os.name == "nt", "Windows 使用其文件权限模型")
    def test_file_permissions_secret_digest_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as vault:
            made = keys.create_key(vault, "权限与摘要")
            path = self._path(vault)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(Path(str(path) + ".lock").stat().st_mode), 0o600)
            content = path.read_text()
            self.assertNotIn(made["secret"], content)
            self.assertEqual(json.loads(content)["keys"][0]["secret_sha256"],
                             hashlib.sha256(made["secret"].encode()).hexdigest())
            os.chmod(path, 0o644)
            keys.verify_key(vault, made["secret"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertFalse(Path(str(path) + ".tmp").exists())

    def test_corrupt_records_do_not_break_other_valid_key_or_authorize(self):
        with tempfile.TemporaryDirectory() as vault:
            made = keys.create_key(vault, "仍有效")
            path = self._path(vault)
            data = json.loads(path.read_text())
            data["keys"] = [None, "broken", 123, {}, {"secret_sha256": "not-a-digest"}] + data["keys"]
            path.write_text(json.dumps(data))
            self.assertEqual(keys.verify_key(vault, made["secret"])["key_id"], made["key_id"])
            self.assertIsNone(keys.verify_key(vault, "omrs_mcp_invalid"))
            path.write_text("{ broken JSON")
            self.assertIsNone(keys.verify_key(vault, made["secret"]))
            self.assertEqual(keys.list_keys(vault), [])

    def test_invalid_matching_record_identity_or_scope_or_expiry_is_rejected(self):
        with tempfile.TemporaryDirectory() as vault:
            made = keys.create_key(vault)
            path = self._path(vault)
            valid = json.loads(path.read_text())["keys"][0]
            expired = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)).isoformat()
            for changes in ({"key_id": None}, {"key_id": 123}, {"key_id": ""},
                            {"scopes": []}, {"scopes": ["omrs:admin"]}, {"scopes": "omrs:read"},
                            {"expires_at": "broken"}, {"expires_at": expired}):
                with self.subTest(changes=changes):
                    path.write_text(json.dumps({"keys": [{**valid, **changes}]}))
                    self.assertIsNone(keys.verify_key(vault, made["secret"]))


if __name__ == "__main__":
    unittest.main()

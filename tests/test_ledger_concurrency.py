"""A1：Ledger 追加与计数原子化（BEGIN IMMEDIATE + busy_timeout）。"""
import multiprocessing
import os
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from omrs.ledger import append_commit, connect, reserve_operation_id, verify_ledger  # noqa: E402


def _proc_append(vault, n, tag):
    for i in range(n):
        append_commit(vault, "system", "system.test", f"{tag}-{i}", {"i": i, "tag": tag})


class LedgerConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="omrs-lc-")
        os.makedirs(os.path.join(self.vault, "错题"))
        append_commit(self.vault, "system", "system.genesis", "genesis", {})

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def _count(self):
        with connect(self.vault) as db:
            return db.execute("SELECT COUNT(*) FROM commits").fetchone()[0]

    def test_threads_keep_chain_valid(self):
        errors = []

        def work(tag):
            try:
                for i in range(50):
                    append_commit(self.vault, "system", "system.test", f"{tag}-{i}", {"i": i, "tag": tag})
            except Exception as exc:  # pragma: no cover - 失败时报告
                errors.append(exc)
        threads = [threading.Thread(target=work, args=(f"t{k}",)) for k in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(self._count(), 201)
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_processes_keep_chain_valid(self):
        ctx = multiprocessing.get_context("spawn")
        procs = [ctx.Process(target=_proc_append, args=(self.vault, 30, f"p{k}")) for k in range(2)]
        [p.start() for p in procs]
        [p.join(60) for p in procs]
        self.assertEqual([p.exitcode for p in procs], [0, 0])
        self.assertEqual(self._count(), 61)
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_reserved_ids_unique(self):
        out, lock = [], threading.Lock()

        def work():
            ids = [reserve_operation_id(self.vault) for _ in range(25)]
            with lock:
                out.extend(ids)
        threads = [threading.Thread(target=work) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(out), 100)
        self.assertEqual(len(set(out)), 100)


if __name__ == "__main__":
    unittest.main()

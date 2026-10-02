"""助手分页、持久事件与运行缓存的行为门禁。"""
import json
import tempfile
import time
import unittest
from unittest.mock import patch

from omrs.agent.runtime import AgentRuntime, Run
from omrs.agent.store import AgentStore


class AgentPaginationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.vault = self.directory.name
        self.runtime = AgentRuntime(self.vault)
        self.store = self.runtime.store
        self.store.create_conversation("conv", "测试")

    def test_event_cursor_survives_tail_eviction_completion_and_restart(self):
        self.store.create_run("run", "conv", "test")
        run = Run("run", "conv", "test", self.store)
        self.runtime.runs[run.id] = run
        for index in range(1300):
            run.emit("delta", {"kind": "text", "n": 1, "text": str(index) + "中" * 700})
        self.assertLessEqual(len(run.events), 1000)
        self.assertLessEqual(run.tail_bytes, 1024 * 1024)
        first = self.runtime.events("run", 0, limit=200)
        self.assertEqual([row["i"] for row in first["events"]], list(range(200)))
        self.assertEqual(first["next"], 200)
        self.assertTrue(first["has_more"])
        self.store.save_run("run", status="done", ended=True)
        self.runtime.runs.clear()
        restarted = AgentRuntime(self.vault)
        cursor, seen = first["next"], list(first["events"])
        while True:
            page = restarted.events("run", cursor, limit=500)
            seen.extend(page["events"])
            cursor = page["next"]
            if not page["has_more"]:
                self.assertTrue(page["done"])
                break
        self.assertEqual([row["i"] for row in seen], list(range(1300)))
        self.assertEqual(cursor, 1300)
        self.assertEqual(len(seen[-1]["data"]["text"]), len("1299") + 700)

    def test_thousand_completed_runs_page_without_loading_full_history(self):
        rows = [(f"run_{i:04d}", "conv", "done", "test", f"2026-10-01T00:{i // 60:02d}:{i % 60:02d}Z") for i in range(1000)]
        self.store._exec("INSERT INTO runs(id,conversation_id,status,model,started_at) VALUES(?,?,?,?,?)", rows, many=True)
        with patch.object(self.store, "runs", side_effect=AssertionError("不得全读运行")), patch.object(self.store, "messages", side_effect=AssertionError("不得全读消息")):
            listed = self.runtime.list_conversations()
            self.assertEqual(listed["conversations"][0]["runs"], 1000)
            page = self.runtime.conversation("conv")
            self.assertEqual(len(page["items"]), 20)
            self.assertTrue(page["has_more"])
            ids = {item["item_key"] for item in page["items"]}
            while page["has_more"]:
                page = self.runtime.conversation("conv", limit=50, cursor=page["next_cursor"])
                current = {item["item_key"] for item in page["items"]}
                self.assertFalse(ids & current)
                ids |= current
        self.assertEqual(len(ids), 1000)
        self.assertEqual(self.runtime.runs, {})

    def test_list_keyset_pagination_has_no_duplicates(self):
        for index in range(70):
            self.store.create_conversation(f"c{index:03d}", str(index))
        cursor, identities = None, []
        while True:
            page = self.runtime.list_conversations(limit=30,cursor=cursor)
            identities.extend(row["id"] for row in page["conversations"])
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]
        self.assertEqual(len(identities), 71)
        self.assertEqual(len(set(identities)), 71)
        with self.assertRaises(ValueError):
            self.runtime.list_conversations(cursor="not-a-cursor")

    def test_legacy_events_migrate_without_changing_payload(self):
        self.store.create_run("legacy", "conv", "test")
        events = [{"i": i,"t": i,"type": "delta","data": {"text": str(i)}} for i in range(4)]
        self.store._exec("UPDATE runs SET events_json=?,status='done' WHERE id='legacy'", (json.dumps(events),))
        migrated = AgentStore(self.vault)
        self.assertEqual(migrated.event_page("legacy")["events"], events)
        self.assertEqual(migrated._all("SELECT events_json FROM runs WHERE id='legacy'")[0]["events_json"], "[]")
        self.assertEqual(AgentStore(self.vault).event_page("legacy")["events"], events)


if __name__ == "__main__":
    unittest.main()

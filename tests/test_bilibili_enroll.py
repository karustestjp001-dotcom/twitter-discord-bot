import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import bilibili_enroll as enroll
import bilibili_monitor as monitor


class EnrollmentTests(unittest.TestCase):
    def test_plan_has_nine_unique_routable_sources(self):
        plan = json.loads((Path(__file__).resolve().parents[1] / "repairs/2026-10-19-enroll.json").read_text(encoding="utf-8"))
        self.assertEqual(len(plan["items"]), 9)
        self.assertEqual(len({i["thread_key"] for i in plan["items"]}), 9)
        for item in plan["items"]:
            self.assertIn(item["bvid"], monitor.WATCH_VIDEOS)
            self.assertEqual(monitor.THREAD_KEY_OVERRIDES[item["bvid"]], item["thread_key"])
            self.assertNotIn(item["thread_key"], monitor.COMPLETED_THREADS)

    def test_create_readback_and_retry_reuse_thread(self):
        plan = {"id": "batch", "forum_id": "forum", "guild_id": "guild", "bot_id": "bot"}
        item = {"thread_key": "show", "episodes": [1]}
        info = {"bvid": "BVtest", "title": "Test", "owner": "UP", "owner_mid": "1", "aid": "1",
                "pubdate": 100, "page_count": 1, "pages": [{"cid": "1", "page": 1, "episode_no": 1}]}
        thread = {"id": "thread", "parent_id": "forum", "name": "Bilibili 更新 - Test"}
        message = {"id": "thread", "channel_id": "thread", "content": "content", "author": {"id": "bot"}}
        calls = []

        def request(session, method, path, payload=None):
            calls.append((method, path))
            return message if "/messages/" in path else thread

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(monitor, "STATE_FILE", str(Path(directory) / "state.json")), \
             patch.object(monitor, "THREAD_TITLES", {"show": "Test"}), \
             patch.object(enroll, "discord_request", side_effect=request):
            state, threads = {"videos": {}, "threads": {}}, {}
            enroll.enroll_one(Mock(), state, threads, plan, item, info, "content")
            enroll.enroll_one(Mock(), state, threads, plan, item, info, "content")
            self.assertEqual(sum(method == "POST" for method, _ in calls), 1)
            self.assertEqual(len(monitor.load_state()["delivery_receipts"]), 1)
            self.assertEqual(state["threads"]["show"]["thread_id"], "thread")

    def test_readback_failure_preserves_route_without_seeding_seen(self):
        thread = {"id": "thread", "parent_id": "forum", "name": "Bilibili 更新 - Test"}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(monitor, "STATE_FILE", str(Path(directory) / "state.json")), \
             patch.object(monitor, "THREAD_TITLES", {"show": "Test"}), \
             patch.object(enroll, "discord_request", side_effect=[thread, RuntimeError("GET failed")]):
            state = {"videos": {}, "threads": {}}
            with self.assertRaises(RuntimeError):
                enroll.enroll_one(Mock(), state, {}, {"forum_id": "forum"},
                                 {"thread_key": "show"}, {"bvid": "BVtest"}, "content")
            saved = monitor.load_state()
            self.assertEqual(saved["threads"]["show"]["thread_id"], "thread")
            self.assertEqual(saved["videos"], {})


if __name__ == "__main__":
    unittest.main()

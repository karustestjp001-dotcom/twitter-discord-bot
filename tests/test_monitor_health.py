import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import bilibili_monitor as monitor


class HealthAlertTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(monitor, "STATE_FILE", str(Path(directory.name) / "state.json"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sources = {"show": {"video:BVtest", "upload:123:show"}}
        patcher = patch.object(monitor, "get_active_source_ids_by_thread", return_value=self.sources)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = {"videos": {}, "threads": {"show": {"thread_id": "123", "title": "Test"}},
                      "weekly_health": {"show": {"last_episode_notification_at":
                          (datetime.now(monitor.TIMEZONE) - timedelta(days=1)).isoformat()}}}

    @patch.object(monitor, "send_discord_message", return_value={"message_id": "1", "thread_id": "123"})
    def test_source_failure_alerts_before_seven_days_and_deduplicates(self, send):
        checked = {"show": {"upload:123:show"}}
        failures = {"video:BVtest": "Bilibili API error for BVtest: -404"}
        monitor.check_weekly_update_health("webhook", self.state, checked, failures)
        self.assertIn("來源查詢失敗", send.call_args.args[1]["content"])
        self.assertIn("已刪除或無法存取", send.call_args.args[1]["content"])
        self.assertEqual(send.call_args.args[2], "123")
        persisted = monitor.load_state()
        monitor.check_weekly_update_health("webhook", persisted, checked, failures)
        send.assert_called_once()

    @patch.object(monitor, "send_discord_message", return_value={"message_id": "1", "thread_id": "123"})
    def test_source_recovery_rearms_only_the_recovered_source(self, send):
        monitor.check_weekly_update_health("webhook", self.state, {})
        monitor.check_weekly_update_health("webhook", self.state, {"show": {"video:BVtest"}})
        self.assertEqual(send.call_count, 1)
        monitor.check_weekly_update_health("webhook", self.state, {})
        self.assertEqual(send.call_count, 2)
        content = send.call_args.args[1]["content"]
        self.assertIn("BVtest", content)
        self.assertNotIn("UP 123", content)

    @patch.object(monitor, "send_discord_message", return_value={"message_id": "1", "thread_id": "123"})
    def test_seven_day_alert_still_sends_when_sources_are_healthy(self, send):
        self.state["weekly_health"]["show"]["last_episode_notification_at"] = (
            datetime.now(monitor.TIMEZONE) - timedelta(days=8)).isoformat()
        checked = {"show": self.sources["show"]}
        monitor.check_weekly_update_health("webhook", self.state, checked)
        monitor.check_weekly_update_health("webhook", self.state, checked)
        send.assert_called_once()
        self.assertIn("已超過 7 天", send.call_args.args[1]["content"])

    @patch.object(monitor, "send_discord_message", return_value={"message_id": "1", "thread_id": "123"})
    def test_simultaneous_source_failure_and_seven_days_use_one_message(self, send):
        self.state["weekly_health"]["show"]["last_episode_notification_at"] = (
            datetime.now(monitor.TIMEZONE) - timedelta(days=8)).isoformat()
        monitor.check_weekly_update_health("webhook", self.state, {})
        monitor.check_weekly_update_health("webhook", self.state, {})
        send.assert_called_once()
        self.assertIn("已超過 7 天", send.call_args.args[1]["content"])
        self.assertIn("來源查詢失敗", send.call_args.args[1]["content"])

    @patch.object(monitor, "send_discord_message")
    def test_failed_delivery_is_retried_without_suppressing_other_threads(self, send):
        self.sources["second"] = {"video:BVsecond"}
        self.state["threads"]["second"] = {"thread_id": "456", "title": "Second"}
        self.state["weekly_health"]["second"] = dict(self.state["weekly_health"]["show"])
        send.side_effect = [RuntimeError("Discord unavailable"), {"message_id": "1", "thread_id": "123"}]
        with self.assertRaises(RuntimeError):
            monitor.check_weekly_update_health("webhook", self.state, {})
        self.assertEqual(send.call_count, 2)
        send.side_effect = None
        send.return_value = {"message_id": "2", "thread_id": "456"}
        monitor.check_weekly_update_health("webhook", self.state, {})
        self.assertEqual(send.call_count, 3)

    @patch.object(monitor.time, "sleep")
    @patch.object(monitor, "send_discord_message")
    def test_failure_recovered_by_scan_retry_does_not_alert(self, send, sleep):
        self.sources["show"] = {"upload:123:show"}
        with patch.dict(monitor.os.environ, {monitor.WEBHOOK_ENV: "webhook", "BILIBILI_FORCE": "1"}), \
             patch.object(monitor, "WATCH_VIDEOS", []), \
             patch.object(monitor, "UPLOAD_MONITORS", [{"mid": "123", "thread_key": "show"}]), \
             patch.object(monitor, "ANIME1_MONITORS", []), \
             patch.object(monitor, "BANGUMI_MONITORS", []), \
             patch.object(monitor, "YOUTUBE_MONITORS", []), \
             patch.object(monitor, "load_state", return_value=self.state), \
             patch.object(monitor, "check_upload_monitor", side_effect=[RuntimeError("412"), True]):
            monitor.main()
        send.assert_not_called()
        self.assertTrue(self.state["last_check_complete"])

    def test_error_details_distinguish_deleted_sources_from_rate_limiting(self):
        self.assertIn("已刪除或無法存取", monitor.describe_source_failure("video:BVtest", "API -404"))
        self.assertIn("限流", monitor.describe_source_failure("upload:123:show", "412 Client Error"))
        self.assertNotIn("刪除", monitor.describe_source_failure("upload:123:show", "412 Client Error"))
        self.assertNotIn("刪除", monitor.describe_source_failure("video:BV1404abcd", "Timeout for BV1404abcd"))


class NewBvidTests(unittest.TestCase):
    def test_all_nine_rules_detect_standalone_bvid_and_keep_original_thread(self):
        root = Path(__file__).resolve().parents[1]
        plan = json.loads((root / "repairs/2026-10-19-enroll.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(monitor, "STATE_FILE", str(Path(directory) / "state.json")):
            for index, item in enumerate(plan["items"]):
                with self.subTest(thread_key=item["thread_key"]):
                    key = item["thread_key"]
                    rule = next(r for r in monitor.UPLOAD_MONITORS if r["thread_key"] == key)
                    count = max(item["episodes"])
                    pages = [{"cid": str(n), "page": n, "part": f"第{n}话", "episode_no": n,
                              "episode_no_explicit": True, "duration": 1500}
                             for n in range(1, count + 1)]
                    old = {"bvid": item["bvid"], "aid": "1", "title": rule["keywords"][0] + " 全12集",
                           "owner_mid": rule["mid"], "owner": rule["name"], "pubdate": 100,
                           "page_count": count, "pages": pages}
                    bvid = f"BVstandalone{index}"
                    self.assertNotIn(bvid, monitor.WATCH_VIDEOS)
                    new_page = {"cid": "999", "page": 1, "part": "(1)", "episode_no": 1,
                                "episode_no_explicit": True, "duration": 1500}
                    new = {**old, "bvid": bvid, "title": rule["keywords"][0] + f" 第{count + 1}话",
                           "pubdate": 200, "page_count": 1, "pages": [new_page]}
                    state = {"videos": {item["bvid"]: monitor.make_snapshot(old, key)},
                             "threads": {key: {"thread_id": "123", "title": monitor.THREAD_TITLES[key]}}}
                    cache = {monitor.upload_cache_key(rule): [{"bvid": bvid, "title": new["title"],
                              "upMid": rule["mid"], "pubdate": 200, "duration": 1500}]}
                    response = Mock(status_code=200)
                    response.json.return_value = {"id": "456", "channel_id": "123"}
                    with patch.object(monitor, "get_video_info", return_value=new), \
                         patch.object(monitor.requests, "post", return_value=response) as post:
                        monitor.check_upload_monitor(Mock(), "https://discord.invalid/test", state, rule, cache)
                        monitor.check_upload_monitor(Mock(), "https://discord.invalid/test", state, rule, cache)
                    post.assert_called_once()
                    payload = post.call_args.kwargs["json"]
                    self.assertNotIn("thread_name", payload)
                    self.assertIn(f"第{count + 1}集", payload["content"])
                    self.assertIn(f"https://www.vxbilibili.com/video/{bvid}/?p=1", payload["content"])
                    self.assertEqual(state["threads"][key]["thread_id"], "123")


if __name__ == "__main__":
    unittest.main()

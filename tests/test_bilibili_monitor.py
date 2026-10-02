import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# The production workflow installs requests.  These unit tests only exercise
# pure routing/health logic, so a minimal module keeps them dependency-free.
requests_stub = types.ModuleType("requests")
requests_stub.post = lambda *args, **kwargs: None
requests_stub.Session = lambda: types.SimpleNamespace(headers={})
sys.modules.setdefault("requests", requests_stub)

zoneinfo_stub = types.ModuleType("zoneinfo")
zoneinfo_stub.ZoneInfo = lambda _name: timezone(timedelta(hours=8))
sys.modules.setdefault("zoneinfo", zoneinfo_stub)

import bilibili_monitor as monitor
import config_bilibili as config


class WeeklyHealthTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(monitor.TIMEZONE)
        self.state = {
            "threads": {
                "show": {
                    "thread_id": "thread-1",
                    "title": "測試作品",
                }
            },
            "weekly_health": {
                "show": {
                    "last_episode_notification_at": (
                        self.now - timedelta(days=8)
                    ).isoformat(timespec="seconds")
                }
            },
        }

    @patch("bilibili_monitor.get_active_source_ids_by_thread")
    @patch("bilibili_monitor.requests.post")
    def test_failed_source_check_cannot_send_weekly_alert(self, post, source_ids):
        source_ids.return_value = {"show": {"video:BV1test"}}

        monitor.check_weekly_update_health(
            "https://discord.invalid/webhook",
            self.state,
            {"show": set()},
        )

        post.assert_not_called()
        self.assertNotIn("alerted_for", self.state["weekly_health"]["show"])

    @patch("bilibili_monitor.get_active_source_ids_by_thread")
    @patch("bilibili_monitor.requests.post")
    def test_completed_source_check_can_send_weekly_alert(self, post, source_ids):
        source_ids.return_value = {"show": {"video:BV1test"}}
        post.return_value.status_code = 204
        post.return_value.text = ""

        monitor.check_weekly_update_health(
            "https://discord.invalid/webhook",
            self.state,
            {"show": {"video:BV1test"}},
        )

        post.assert_called_once()
        self.assertIn("alerted_for", self.state["weekly_health"]["show"])


class DuplicatePreventionTests(unittest.TestCase):
    def test_unseen_fixed_bvid_has_no_synthetic_new_pages(self):
        info = {"pages": [{"cid": "101", "page": 1, "part": "第1集"}]}

        self.assertEqual(monitor.detect_new_pages(None, info), [])

    def test_dead_bvids_are_not_active_fixed_sources(self):
        self.assertNotIn("BV1smN26sEqQ", config.WATCH_VIDEOS)
        self.assertNotIn("BV1N3MW6aEoQ", config.WATCH_VIDEOS)


class DailyRetryTests(unittest.TestCase):
    def test_missing_cookie_blocks_retries_for_the_rest_of_the_day(self):
        state = {
            "last_checked_date": monitor.today_taipei(),
            "last_check_complete": False,
            "last_check_blocked": "missing_bilibili_cookie",
        }

        self.assertTrue(
            monitor.should_skip_daily_check(
                state,
                monitor.today_taipei(),
                force=False,
                bilibili_sources_available=False,
            )
        )

    def test_missing_cookie_skips_bilibili_calls_and_records_blocker(self):
        state = {"videos": {}, "threads": {}}
        saved_states = []

        with (
            patch.dict(
                os.environ,
                {
                    monitor.WEBHOOK_ENV: "https://discord.invalid/webhook",
                    "BILIBILI_COOKIE": "",
                },
                clear=False,
            ),
            patch.object(monitor, "WATCH_VIDEOS", ["BV1test"]),
            patch.object(
                monitor,
                "UPLOAD_MONITORS",
                [{"mid": "1", "thread_key": "show", "name": "test", "keywords": ["test"]}],
            ),
            patch.object(monitor, "BANGUMI_MONITORS", []),
            patch.object(monitor, "ANIME1_MONITORS", []),
            patch.object(monitor, "YOUTUBE_MONITORS", []),
            patch.object(monitor, "load_state", return_value=state),
            patch.object(monitor, "save_state", side_effect=saved_states.append),
            patch.object(monitor, "get_video_info") as get_video_info,
            patch.object(monitor, "check_upload_monitor") as check_upload_monitor,
            patch.object(monitor, "check_weekly_update_health", return_value=True),
        ):
            monitor.main()

        get_video_info.assert_not_called()
        check_upload_monitor.assert_not_called()
        self.assertEqual(saved_states[-1]["last_check_blocked"], "missing_bilibili_cookie")


if __name__ == "__main__":
    unittest.main()

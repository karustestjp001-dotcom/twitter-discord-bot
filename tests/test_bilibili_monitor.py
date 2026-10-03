import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import bilibili_monitor as monitor
from bilibili_backfill import prepare_item


def video_info(pages=1):
    return {
        "bvid": "BVtest", "aid": "1", "title": "Test 第1集", "owner": "Test UP",
        "owner_mid": "123", "pubdate": 100, "page_count": pages,
        "pages": [{"cid": str(n), "page": n, "part": f"第{n}集", "episode_no": n}
                  for n in range(1, pages + 1)],
    }


class MonitorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state.json"
        patcher = patch.object(monitor, "STATE_FILE", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = {"videos": {}, "threads": {"show": {"thread_id": "123", "title": "Test"}}}

    def test_partial_run_retries_without_cookie(self):
        state = {"last_checked_date": monitor.today_taipei(), "last_check_complete": False,
                 "last_check_blocked": "missing_bilibili_cookie"}
        self.assertFalse(monitor.should_skip_daily_check(state, monitor.today_taipei(), False, False))
        state["last_check_complete"] = True
        self.assertTrue(monitor.should_skip_daily_check(state, monitor.today_taipei(), False))
        self.assertFalse(monitor.should_skip_daily_check(state, monitor.today_taipei(), True))

    def test_no_cookie_still_runs_public_video_and_up_checks(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {monitor.WEBHOOK_ENV: "https://discord.invalid/x",
                                                       "BILIBILI_COOKIE": "", "BILIBILI_FORCE": "1"}))
            for name, value in {
                "WATCH_VIDEOS": ["BVtest"], "THREAD_KEY_OVERRIDES": {"BVtest": "show"},
                "UPLOAD_MONITORS": [{"mid": "123", "thread_key": "show"}],
                "BANGUMI_MONITORS": [], "ANIME1_MONITORS": [], "YOUTUBE_MONITORS": [],
                "COMPLETED_THREADS": {},
            }.items():
                stack.enter_context(patch.object(monitor, name, value))
            stack.enter_context(patch.object(monitor, "load_state", return_value=self.state))
            video = stack.enter_context(patch.object(monitor, "get_video_info", return_value=video_info()))
            uploads = stack.enter_context(patch.object(monitor, "check_upload_monitor", return_value=True))
            stack.enter_context(patch.object(monitor, "check_weekly_update_health", return_value=True))
            monitor.main()
        video.assert_called_once()
        uploads.assert_called_once()
        self.assertTrue(self.state["last_check_complete"])
        self.assertNotIn("last_check_blocked", self.state)

    def test_later_shared_up_recovery_rechecks_failed_earlier_rule(self):
        calls = []

        def check(session, webhook, state, rule, cache):
            calls.append(rule["thread_key"])
            if len(calls) == 1:
                raise RuntimeError("temporary block")
            cache["123"] = []
            return True

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {monitor.WEBHOOK_ENV: "test", "BILIBILI_FORCE": "1"}))
            for name, value in {"WATCH_VIDEOS": [], "BANGUMI_MONITORS": [], "ANIME1_MONITORS": [],
                                "YOUTUBE_MONITORS": [], "COMPLETED_THREADS": {},
                                "UPLOAD_MONITORS": [{"mid": "123", "thread_key": "one"},
                                                    {"mid": "123", "thread_key": "two"}]}.items():
                stack.enter_context(patch.object(monitor, name, value))
            stack.enter_context(patch.object(monitor, "check_upload_monitor", side_effect=check))
            stack.enter_context(patch.object(monitor, "check_weekly_update_health", return_value=True))
            stack.enter_context(patch.object(monitor, "load_state", return_value=self.state))
            monitor.main()
        self.assertEqual(calls, ["one", "two", "one"])
        self.assertTrue(self.state["last_check_complete"])
        self.assertEqual(self.state["last_check_failures"], {})

    def test_cookie_only_goes_to_bilibili(self):
        session = monitor.make_source_session("SESSDATA=test-only; other=value")
        bili = session.prepare_request(requests.Request("GET", "https://api.bilibili.com/x"))
        external = session.prepare_request(requests.Request("GET", "https://www.youtube.com/feeds/videos.xml"))
        self.assertIn("SESSDATA=test-only", bili.headers["Cookie"])
        self.assertNotIn("Cookie", external.headers)

    def test_episode_number_formats_and_clip_filter(self):
        for title, expected in [("S01E10", 10), ("EP08", 8), ("第9話", 9), ("(13)", 13), ("06", 6)]:
            self.assertEqual(monitor.extract_episode_no(title), expected)
        for title in ["EP08 抢先看片段", "EP09 预告", "S01E10 Trailer"]:
            self.assertFalse(monitor.is_episode_title(title))
        self.assertTrue(monitor.is_episode_title("柯蒂斯总统 S01E10 中英字幕"))

    def test_api_412_uses_public_html_without_login(self):
        data = {"bvid": "BVtest", "aid": 1, "title": "Test 第2集", "owner": {"mid": 123},
                "pages": [{"cid": 2, "page": 1, "part": "第2集"},
                          {"cid": 3, "page": 2, "part": "感谢观看，关注不迷路"}]}
        session = Mock()
        session.get.side_effect = [Mock(status_code=412), Mock(text="window.__INITIAL_STATE__=" + json.dumps({"videoData": data}) + ";")]
        info = monitor.get_video_info(session, "BVtest")
        self.assertEqual(info["page_count"], 1)
        self.assertEqual(info["pages"][0]["episode_no"], 2)

    def test_html_mismatch_cannot_be_posted(self):
        session = Mock()
        session.get.return_value.text = 'window.__INITIAL_STATE__={"videoData":{"bvid":"wrong","pages":[{}]}};'
        with self.assertRaises(RuntimeError):
            monitor.get_public_video_data(session, "BVtest")

    def test_single_episode_title_beats_generic_part_number(self):
        session = Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = {"code": 0, "data": {
            "title": "Test S01E10", "pages": [{"cid": 1, "page": 1, "part": "(1)"}]}}
        self.assertEqual(monitor.get_video_info(session, "BVtest")["pages"][0]["episode_no"], 10)

    def test_pagelist_recovers_blocked_view_with_verified_archive_identity(self):
        session = Mock()
        pagelist = Mock()
        pagelist.json.return_value = {"code": 0, "data": [{"cid": 99, "page": 1, "part": "(12)"}]}
        session.get.side_effect = [Mock(status_code=412), pagelist]
        source = {"bvid": "BVtest", "title": "Test 第12话", "owner_mid": "123", "metadata_source": "archive"}
        info = monitor.get_video_info(session, "BVtest", source)
        self.assertEqual(info["owner_mid"], "123")
        self.assertEqual(info["pages"][0]["episode_no"], 12)
        self.assertEqual(info["metadata_source"], "archive")

    def test_pagelist_does_not_resurrect_deleted_source(self):
        session = Mock()
        session.get.return_value.json.return_value = {"code": -404}
        with self.assertRaises(RuntimeError):
            monitor.get_pagelist_video_data(session, "BVtest", {"bvid": "BVtest", "title": "Test"})

    @patch.object(monitor.time, "sleep")
    def test_rate_limited_upload_gets_one_bounded_retry(self, sleep):
        session = Mock()
        success = Mock(status_code=200)
        success.json.return_value = {"code": 0, "data": {"archives": []}}
        session.get.side_effect = [Mock(status_code=412), success]
        monitor.find_new_upload_archives(session, {"mid": "123", "thread_key": "show", "keywords": ["Test"]}, {}, {})
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(3)

    def test_corrupt_state_fails_closed(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            monitor.load_state()

    @patch.object(monitor, "send_discord_message")
    @patch.object(monitor, "get_active_source_ids_by_thread", return_value={"show": {"video:BVtest"}})
    def test_failed_source_sends_accurate_deduplicated_alert(self, sources, send):
        send.return_value = {"message_id": "1", "thread_id": "123"}
        self.state["weekly_health"] = {"show": {"last_episode_notification_at":
            (datetime.now(monitor.TIMEZONE) - timedelta(days=8)).isoformat()}}
        monitor.check_weekly_update_health("webhook", self.state, {})
        content = send.call_args.args[1]["content"]
        self.assertIn("來源查詢失敗", content)
        self.assertNotIn("仍未找到新內容", content)
        monitor.check_weekly_update_health("webhook", self.state, {})
        send.assert_called_once()

    @patch.object(monitor, "send_discord_message")
    def test_large_collection_sends_every_page_once_with_receipts(self, send):
        send.return_value = {"message_id": "1", "thread_id": "123"}
        info = video_info(13)
        monitor.post_to_discord("webhook", info, info["pages"], self.state, "show")
        self.assertEqual(send.call_count, 2)
        self.assertEqual(len(self.state["delivery_receipts"]), 13)
        monitor.post_to_discord("webhook", info, info["pages"], self.state, "show")
        self.assertEqual(send.call_count, 2)
        for call in send.call_args_list:
            self.assertLessEqual(len(call.args[1]["content"]), 2000)

    @patch.object(monitor, "send_discord_message")
    def test_partial_chunk_delivery_is_persisted(self, send):
        send.side_effect = [{"message_id": "1", "thread_id": "123"}, RuntimeError("failed")]
        info = video_info(13)
        with self.assertRaises(RuntimeError):
            monitor.post_to_discord("webhook", info, info["pages"], self.state, "show")
        persisted = monitor.load_state()
        self.assertEqual(len(persisted["delivery_receipts"]), 10)
        send.side_effect = None
        send.return_value = {"message_id": "2", "thread_id": "123"}
        monitor.post_to_discord("webhook", info, info["pages"], persisted, "show")
        self.assertNotIn("- 第1集：", send.call_args.args[1]["content"])
        self.assertIn("第13集", send.call_args.args[1]["content"])

    @patch.object(monitor.requests, "post")
    def test_receipt_requires_correct_thread_and_message_id(self, post):
        post.return_value = Mock(status_code=204)
        with self.assertRaises(RuntimeError):
            monitor.send_discord_message("https://discord.invalid/x", {}, "123")
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"id": "1", "channel_id": "999"}
        with self.assertRaises(RuntimeError):
            monitor.send_discord_message("https://discord.invalid/x", {}, "123")

    def test_changed_cid_same_page_is_not_new_episode(self):
        old = video_info()
        old["seen_cids"] = ["99"]
        self.assertEqual(monitor.detect_new_pages(old, video_info()), [])

    def test_older_unseen_upload_is_not_hidden_by_newer_episode(self):
        videos = {"old": {"thread_key": "show", "pubdate": 100}, "new": {"thread_key": "show", "pubdate": 300}}
        cache = {"123": [{"bvid": "missing", "title": "Test 第9集", "pubdate": 200},
                         {"bvid": "clip", "title": "Test 第9集 预告", "pubdate": 400}]}
        config = {"mid": "123", "thread_key": "show", "keywords": ["Test"]}
        matches = monitor.find_new_upload_archives(Mock(), config, videos, cache)
        self.assertEqual([a["bvid"] for a in matches], ["missing"])

    @patch.object(monitor, "post_to_discord")
    @patch.object(monitor, "get_video_info", return_value=video_info(2))
    def test_known_up_collection_is_revisited_for_new_parts(self, get_info, post):
        self.state["videos"]["BVtest"] = monitor.make_snapshot(video_info(), "show")
        config = {"mid": "123", "thread_key": "show", "keywords": ["Test"]}
        cache = {"123": [{"bvid": "BVtest", "title": "Test", "pubdate": 100}]}
        monitor.check_upload_monitor(Mock(), "webhook", self.state, config, cache)
        self.assertEqual([p["page"] for p in post.call_args.args[2]], [2])

    def test_cross_bvid_duplicate_episodes_and_trailers(self):
        old = monitor.make_snapshot(video_info(), "show")
        old["title"] = "Test EP08 预告"
        old["pages"] = [{"episode_no": 8}]
        videos = {"clip": old, "ep": monitor.make_snapshot(video_info(), "show")}
        pages = [{"episode_no": 1}, {"episode_no": 8}, {"episode_no": 9}]
        self.assertEqual(monitor.select_unseen_episodes(videos, "show", pages), pages[1:])

    @patch.object(monitor, "get_video_info")
    def test_backfill_rejects_wrong_title_author_and_missing_episode(self, get_info):
        item = {"thread_key": "show", "bvid": "BVtest", "owner_mid": "123",
                "title_keyword": "Test", "episodes": [1]}
        get_info.return_value = video_info()
        prepare_item(Mock(), self.state, item)
        for key, value in [("owner_mid", "wrong"), ("title_keyword", "wrong"), ("episodes", [2])]:
            with self.assertRaises(ValueError):
                prepare_item(Mock(), self.state, {**item, key: value})

    @patch.object(monitor, "get_anime1_telegram_entries")
    @patch.object(monitor, "post_anime1_to_discord")
    def test_anime1_partial_success_retains_seen_id(self, post, entries):
        entries.return_value = [{"id": "2", "title": "Test [2]"}, {"id": "3", "title": "Test [3]"}]
        self.state["anime1"] = {"show": {"source_url": "source", "seen_post_ids": ["1"]}}
        config = {"thread_key": "show", "url": "source", "feed_url": "feed"}
        post.side_effect = [None, RuntimeError("failed")]
        with self.assertRaises(RuntimeError):
            monitor.check_anime1_monitor(Mock(), "webhook", self.state, config)
        self.assertIn("2", monitor.load_state()["anime1"]["show"]["seen_post_ids"])
        self.assertNotIn("3", monitor.load_state()["anime1"]["show"]["seen_post_ids"])

    def test_completed_shows_do_not_trigger_seven_day_alert(self):
        for key in monitor.COMPLETED_THREADS:
            self.assertNotIn(key, monitor.get_active_source_ids_by_thread())

    def test_reviewed_metadata_requires_matching_identity_and_fresh_timestamp(self):
        item = {"thread_key": "show", "bvid": "BVtest", "owner_mid": "123",
                "title_keyword": "Test", "episodes": [1], "verified_info": video_info(),
                "verified_at": datetime.now(timezone.utc).isoformat()}
        prepare_item(Mock(), self.state, item, reviewed=True)
        item["verified_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        with self.assertRaises(ValueError):
            prepare_item(Mock(), self.state, item, reviewed=True)


if __name__ == "__main__":
    unittest.main()

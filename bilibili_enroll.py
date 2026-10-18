"""Enroll reviewed sources through the existing C-tan bot, never a user account.

The caller checks the bridge is running and supplies its token in the process
environment. Normal GitHub monitoring continues using WEBHOOK_BILIBILI.
"""

import argparse
import json
import os
import time
from datetime import datetime

import requests

import bilibili_monitor as monitor


def discord_request(session, method, path, payload=None):
    for attempt in range(3):
        response = session.request(method, "https://discord.com/api/v10" + path,
                                   json=payload, timeout=20)
        if response.status_code == 429 and attempt < 2:
            time.sleep(min(float(response.json().get("retry_after", 1)), 30))
            continue
        if not response.ok:
            raise RuntimeError(f"Discord {method} {path}: HTTP {response.status_code}")
        return response.json()
    raise RuntimeError("Discord rate limit did not recover")


def list_forum_threads(session, plan):
    active = discord_request(session, "GET", f"/guilds/{plan['guild_id']}/threads/active")
    threads = {t["id"]: t for t in active["threads"] if t["parent_id"] == plan["forum_id"]}
    before = ""
    while True:
        page = discord_request(session, "GET", f"/channels/{plan['forum_id']}/threads/archived/public?limit=100{before}")
        for thread in page["threads"]:
            threads[thread["id"]] = thread
        if not page.get("has_more"):
            return threads
        if not page["threads"]:
            raise RuntimeError("Incomplete archived-thread listing")
        from urllib.parse import quote
        before = "&before=" + quote(page["threads"][-1]["thread_metadata"]["archive_timestamp"])


def prepare_enrollment(session, item):
    key = item["thread_key"]
    if monitor.THREAD_KEY_OVERRIDES.get(item["bvid"]) != key:
        raise ValueError("Enrollment routing mismatch")
    rule = next(r for r in monitor.UPLOAD_MONITORS if r["thread_key"] == key)
    info = monitor.filter_monitored_pages(monitor.get_video_info(session, item["bvid"]), rule)
    if [p["episode_no"] for p in info["pages"]] != item["episodes"]:
        raise ValueError(f"Episode list changed for {key}; review before sending")
    title = monitor.THREAD_TITLES[key]
    lines = ["Bilibili 追番串建立喵", f"追蹤：{title}", f"UP：{info['owner']}", "目前已更新："]
    for index, page in enumerate(info["pages"]):
        url = monitor.format_bilibili_page_url(
            f"https://www.vxbilibili.com/video/{info['bvid']}/", page["page"], bool(index))
        lines.append(f"- 第{page['episode_no']}集：{url}")
    content = "\n".join(lines)
    if len(content) > 1900:
        raise ValueError("Enrollment message is too long")
    return info, content


def enroll_one(session, state, threads, plan, item, info, content):
    key = item["thread_key"]
    title = monitor.THREAD_TITLES[key]
    name = monitor.truncate_thread_name(f"{monitor.FORUM_THREAD_PREFIX} - {title}")
    entry = state.setdefault("threads", {}).get(key)
    if entry:
        thread_id = entry["thread_id"]
    else:
        matches = [t for t in threads.values() if t["name"] == name]
        if len(matches) > 1:
            raise RuntimeError(f"Duplicate existing threads for {key}; manual review required")
        if matches:
            thread_id = matches[0]["id"]
        else:
            created = discord_request(session, "POST", f"/channels/{plan['forum_id']}/threads", {
                "name": name, "auto_archive_duration": 10080,
                "message": {"content": content, "allowed_mentions": {"parse": []}},
            })
            thread_id = created["id"]
            threads[thread_id] = created
        state["threads"][key] = {
            "thread_id": thread_id, "title": title, "bvid": info["bvid"],
            "created_at": datetime.now(monitor.TIMEZONE).isoformat(timespec="seconds"),
        }
        # Persist routing before readback so a failed GET cannot create a second thread.
        monitor.save_state(state)

    thread = discord_request(session, "GET", f"/channels/{thread_id}")
    message = discord_request(session, "GET", f"/channels/{thread_id}/messages/{thread_id}")
    if (thread.get("parent_id") != plan["forum_id"] or thread.get("name") != name
            or message.get("channel_id") != thread_id or message.get("content") != content
            or message.get("author", {}).get("id") != plan["bot_id"]):
        raise RuntimeError(f"Discord readback mismatch for {key}")
    receipt = {"message_id": message["id"], "thread_id": thread_id,
               "verified_at": datetime.now(monitor.TIMEZONE).isoformat(timespec="seconds"),
               "sender": "C-tan"}
    for page in info["pages"]:
        state.setdefault("delivery_receipts", {})[f"bilibili:{info['bvid']}:{page['page']}"] = receipt
    state.setdefault("videos", {})[info["bvid"]] = monitor.make_snapshot(info, key)
    batch = state.setdefault("enrollment_batches", {}).setdefault(plan["id"], {})
    if key not in batch:
        monitor.record_episode_notification(state, key)
    batch[key] = {**receipt, "episodes": item["episodes"], "bvid": info["bvid"]}
    monitor.save_state(state)
    print(f"[VERIFIED] {key}: https://discord.com/channels/{plan['guild_id']}/{thread_id}/{message['id']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    with open(args.plan, encoding="utf-8") as handle:
        plan = json.load(handle)
    source_session = monitor.make_source_session()
    prepared = [(item, *prepare_enrollment(source_session, item)) for item in plan["items"]]
    if not args.send:
        for item, info, content in prepared:
            print(f"[READY] {item['thread_key']} {info['bvid']} {item['episodes']}\n{content}")
        return
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Existing C-tan bot token is required; never put it in the plan")
    session = requests.Session()
    session.headers["Authorization"] = f"Bot {token}"
    identity = discord_request(session, "GET", "/users/@me")
    forum = discord_request(session, "GET", f"/channels/{plan['forum_id']}")
    if identity["id"] != plan["bot_id"] or forum.get("type") != 15 or forum.get("guild_id") != plan["guild_id"]:
        raise RuntimeError("Unexpected bot identity or forum destination")
    threads = list_forum_threads(session, plan)
    state = monitor.load_state()
    for item, info, content in prepared:
        enroll_one(session, state, threads, plan, item, info, content)


if __name__ == "__main__":
    main()

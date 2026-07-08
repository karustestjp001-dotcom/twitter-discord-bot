"""
Daily Bilibili video update monitor.

This watches known BVIDs and detects updates to multi-part videos by comparing
the video page list returned by Bilibili's public view API.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

from config_bilibili import FORUM_THREAD_PREFIX, THREAD_KEY_OVERRIDES, THREAD_TITLES, WATCH_VIDEOS, WEBHOOK_ENV


STATE_FILE = "bilibili_seen.json"
TIMEZONE = ZoneInfo("Asia/Taipei")
REQUEST_TIMEOUT = 20
NON_EPISODE_PART_KEYWORDS = (
    "感谢观看",
    "感謝觀看",
    "关注",
    "關注",
    "追番",
    "每周更新",
    "周更",
    "点个",
    "點個",
)


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"videos": {}}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        try:
            state = json.load(f)
        except Exception:
            return {"videos": {}}

    if "videos" not in state or not isinstance(state["videos"], dict):
        state["videos"] = {}
    if "threads" not in state or not isinstance(state["threads"], dict):
        state["threads"] = {}
    return state


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def today_taipei() -> str:
    return datetime.now(TIMEZONE).date().isoformat()


def get_video_info(session: requests.Session, bvid: str) -> dict:
    resp = session.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili API error for {bvid}: {payload.get('code')} {payload.get('message')}")

    data = payload["data"]
    pages = []
    for page in data.get("pages") or []:
        part = page.get("part") or f"P{page.get('page')}"
        if not is_episode_part(part):
            continue

        pages.append(
            {
                "cid": str(page.get("cid", "")),
                "page": int(page.get("page") or 0),
                "part": part,
                "episode_no": len(pages) + 1,
            }
        )

    return {
        "bvid": bvid,
        "aid": str(data.get("aid", "")),
        "title": data.get("title") or bvid,
        "owner": (data.get("owner") or {}).get("name") or "",
        "owner_mid": str((data.get("owner") or {}).get("mid") or ""),
        "pubdate": int(data.get("pubdate") or 0),
        "page_count": len(pages) or 1,
        "pages": pages,
    }


def make_snapshot(info: dict, thread_key: str) -> dict:
    return {
        "title": info["title"],
        "owner": info["owner"],
        "owner_mid": info["owner_mid"],
        "aid": info["aid"],
        "thread_key": thread_key,
        "pubdate": info["pubdate"],
        "page_count": info["page_count"],
        "seen_cids": [page["cid"] for page in info["pages"] if page["cid"]],
        "pages": info["pages"],
        "last_seen_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
    }


def truncate_thread_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if len(cleaned) <= 90:
        return cleaned
    return cleaned[:87] + "..."


def is_episode_part(part: str) -> bool:
    compact = "".join(str(part).split())
    if not compact:
        return False
    return not any(keyword in compact for keyword in NON_EPISODE_PART_KEYWORDS)


def append_query(url: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def get_thread_key(info: dict) -> str:
    return THREAD_KEY_OVERRIDES.get(info["bvid"], info["bvid"])


def get_thread_title(info: dict, thread_key: str) -> str:
    if thread_key in THREAD_TITLES:
        return THREAD_TITLES[thread_key]

    title = info["title"]
    title = re.sub(r"[【『《「\[]", "", title)
    title = re.sub(r"[】』》」\]]", "", title)
    title = re.sub(r"第\s*\d+\s*[~-]\s*\d+\s*[话話集]", "", title)
    title = re.sub(r"第\s*\d+\s*[话話集]", "", title)
    title = re.sub(r"更至\s*\d+(?:\s*-\s*\d+)?\s*[集话話]?", "", title)
    title = re.sub(r"（.*?）|\\(.*?\\)", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title or info["title"]


def format_bilibili_page_url(video_url: str, page_no: int | str) -> str:
    url = f"{video_url}?p={page_no}"
    if str(page_no) == "1":
        return url
    return f"<{url}>"


def post_to_discord(
    webhook_url: str,
    info: dict,
    new_pages: list[dict],
    state: dict,
    thread_key: str,
    bootstrap: bool = False,
) -> None:
    video_url = f"https://www.bilibili.com/video/{info['bvid']}"
    thread_title = get_thread_title(info, thread_key)
    lines = [
        "Bilibili 追番串建立喵" if bootstrap else "Bilibili 影片更新喵",
        f"追蹤：{thread_title}",
        f"原標題：{info['title']}",
    ]
    if info["owner"]:
        lines.append(f"UP：{info['owner']}")

    if new_pages:
        lines.append("")
        lines.append(f"新增 {len(new_pages)} 個分P：")
        for page in new_pages[:10]:
            page_no = page.get("page") or ""
            episode_no = page.get("episode_no") or page_no
            part = page.get("part") or f"P{page_no}"
            page_url = format_bilibili_page_url(video_url, page_no)
            lines.append(f"- 第{episode_no}集：P{page_no} {part} {page_url}")
    else:
        lines.append(video_url)

    payload = {
        "content": "\n".join(lines),
    }
    post_url = append_query(webhook_url, {"wait": "true"})

    thread_id = (state.setdefault("threads", {}).get(thread_key) or {}).get("thread_id")
    if thread_id:
        post_url = append_query(webhook_url, {"thread_id": thread_id, "wait": "true"})
    else:
        payload["thread_name"] = truncate_thread_name(f"{FORUM_THREAD_PREFIX} - {thread_title}")

    resp = requests.post(post_url, json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Discord webhook error {resp.status_code}: {resp.text[:300]}")

    if not thread_id and resp.text:
        message = resp.json()
        channel_id = message.get("channel_id")
        if channel_id:
            state["threads"][thread_key] = {
                "thread_id": channel_id,
                "title": thread_title,
                "bvid": info["bvid"],
                "created_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
            }


def detect_new_pages(old: dict | None, info: dict) -> list[dict]:
    if not old:
        return []

    old_cids = set(old.get("seen_cids") or [])
    if not old_cids:
        old_count = int(old.get("page_count") or 0)
        return [page for page in info["pages"] if page.get("page", 0) > old_count]

    return [page for page in info["pages"] if page.get("cid") and page["cid"] not in old_cids]


def has_existing_video_for_thread(videos: dict, current_bvid: str, thread_key: str) -> bool:
    for bvid, snapshot in videos.items():
        if bvid != current_bvid and snapshot.get("thread_key") == thread_key:
            return True
    return False


def main() -> None:
    force = os.environ.get("BILIBILI_FORCE") == "1"
    bootstrap_threads = os.environ.get("BILIBILI_BOOTSTRAP_THREADS") == "1"
    webhook_url = os.environ.get(WEBHOOK_ENV)
    if not webhook_url:
        print(f"[WARN] Missing {WEBHOOK_ENV}; skip Bilibili monitor")
        return

    state = load_state()
    state.setdefault("threads", {})
    today = today_taipei()
    if state.get("last_checked_date") == today and not force:
        print(f"[OK] Bilibili already checked today ({today}); skip")
        return

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }
    )

    cookie = os.environ.get("BILIBILI_COOKIE")
    if cookie:
        session.headers.update({"Cookie": cookie})

    videos = state.setdefault("videos", {})
    success_count = 0

    for bvid in WATCH_VIDEOS:
        old = videos.get(bvid)
        try:
            info = get_video_info(session, bvid)
            thread_key = get_thread_key(info)
            new_pages = detect_new_pages(old, info)
            if not old and has_existing_video_for_thread(videos, bvid, thread_key):
                new_pages = info["pages"]
            if bootstrap_threads and not state["threads"].get(thread_key):
                print(f"[THREAD] {bvid} create Discord thread")
                post_to_discord(webhook_url, info, info["pages"], state, thread_key, bootstrap=True)
            elif new_pages:
                print(f"[NEW] {bvid} has {len(new_pages)} new pages")
                post_to_discord(webhook_url, info, new_pages, state, thread_key)
            elif old:
                print(f"[NOOP] {bvid} no new pages")
            else:
                print(f"[INIT] {bvid} first seen")

            videos[bvid] = make_snapshot(info, thread_key)
            success_count += 1
        except Exception as exc:
            print(f"[WARN] {bvid} check failed: {repr(exc)}")

    if success_count:
        state["last_checked_date"] = today
        state["last_checked_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
        save_state(state)
        print(f"[OK] Bilibili check done: {success_count}/{len(WATCH_VIDEOS)}")
    else:
        print("[ERROR] Bilibili all checks failed; state not updated")


if __name__ == "__main__":
    main()

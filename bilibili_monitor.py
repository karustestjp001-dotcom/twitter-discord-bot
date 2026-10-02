"""
Daily Bilibili video update monitor.

This watches known BVIDs and detects updates to multi-part videos by comparing
the video page list returned by Bilibili's public view API.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

from config_bilibili import (
    ANIME1_MONITORS,
    BANGUMI_MONITORS,
    COMPLETED_THREADS,
    FORUM_THREAD_PREFIX,
    THREAD_KEY_OVERRIDES,
    THREAD_TITLES,
    UPLOAD_MONITORS,
    WATCH_VIDEOS,
    WEBHOOK_ENV,
    YOUTUBE_MONITORS,
)


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
NON_EPISODE_TITLE_KEYWORDS = (
    "预告", "預告", "片段", "抢先看", "搶先看", "解说", "解說", "彩蛋",
    "trailer", "preview", "reaction",
)
UPLOAD_SEARCH_PAGE_SIZE = 30
WEEKLY_UPDATE_TIMEOUT = timedelta(days=7)
ANIME1_ENTRY_RE = re.compile(
    r'<h2 class="entry-title"><a href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<time[^>]+datetime="([^"]+)"',
    re.DOTALL,
)
ANIME1_POST_URL_RE = re.compile(r"^https?://anime1\.me/(\d+)(?:[/?#].*)?$")


class Anime1TelegramParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[dict] = []
        self._current: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return

        href = dict(attrs).get("href") or ""
        match = ANIME1_POST_URL_RE.match(href)
        if match:
            post_id = match.group(1)
            self._current = {
                "id": post_id,
                "url": f"https://anime1.me/{post_id}",
                "text": [],
            }

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current is None:
            return

        title = "".join(self._current.pop("text")).strip()
        title = re.sub(r"\s*已更新\s*$", "", title).strip()
        episode_match = re.search(r"\[(\d+)\]", title)
        if title and episode_match:
            self.entries.append(
                {
                    **self._current,
                    "title": title,
                    "episode_no": int(episode_match.group(1)),
                    "published_at": "",
                }
            )
        self._current = None


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"videos": {}}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    if not isinstance(state, dict):
        raise ValueError("Invalid monitor state; refusing to reset delivery history")

    if "videos" not in state or not isinstance(state["videos"], dict):
        state["videos"] = {}
    if "threads" not in state or not isinstance(state["threads"], dict):
        state["threads"] = {}
    return state


def save_state(state: dict) -> None:
    temporary = STATE_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(temporary, STATE_FILE)


def today_taipei() -> str:
    return datetime.now(TIMEZONE).date().isoformat()


def should_skip_daily_check(
    state: dict,
    today: str,
    force: bool,
    bilibili_sources_available: bool = True,
) -> bool:
    if force or state.get("last_checked_date") != today:
        return False

    if state.get("last_check_complete") is True:
        return True

    return False


def make_source_session(cookie: str = "") -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    # A raw Cookie header on a shared session would leak to Anime1/YouTube.
    jar = SimpleCookie()
    jar.load(cookie)
    for name, value in jar.items():
        session.cookies.set(name, value.value, domain=".bilibili.com", path="/")
    return session


def get_public_video_data(session: requests.Session, bvid: str) -> dict:
    resp = session.get(f"https://www.bilibili.com/video/{bvid}/", timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    marker = re.search(r"window\.__INITIAL_STATE__\s*=\s*", resp.text)
    if not marker:
        raise RuntimeError(f"Public video page has no metadata: {bvid}")
    initial, _ = json.JSONDecoder().raw_decode(resp.text[marker.end():])
    data = initial.get("videoData") or {}
    if data.get("bvid") != bvid or not data.get("pages"):
        raise RuntimeError(f"Public video page is missing or mismatched: {bvid}")
    return data


def get_video_info(session: requests.Session, bvid: str) -> dict:
    resp = session.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code in (403, 412, 429):
        print(f"[FALLBACK] {bvid}: public HTML metadata (API {resp.status_code})")
        data = get_public_video_data(session, bvid)
    else:
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") in (-352, -412, -403):
            data = get_public_video_data(session, bvid)
        elif payload.get("code") != 0:
            raise RuntimeError(f"Bilibili API error for {bvid}: {payload.get('code')}")
        else:
            data = payload["data"]
    title = data.get("title") or bvid
    raw_pages = data.get("pages") or []
    pages = []
    for page in raw_pages:
        part = page.get("part") or f"P{page.get('page')}"
        if not is_episode_part(part) or not is_episode_title(title):
            continue

        episode_no = extract_episode_no(part)
        if len(raw_pages) == 1:
            episode_no = extract_episode_no(title) or episode_no

        pages.append(
            {
                "cid": str(page.get("cid", "")),
                "page": int(page.get("page") or 0),
                "part": part,
                "episode_no": episode_no or len(pages) + 1,
            }
        )

    return {
        "bvid": bvid,
        "aid": str(data.get("aid", "")),
        "title": title,
        "owner": (data.get("owner") or {}).get("name") or "",
        "owner_mid": str((data.get("owner") or {}).get("mid") or ""),
        "pubdate": int(data.get("pubdate") or 0),
        "page_count": len(pages),
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


def extract_episode_no(text: str) -> int | None:
    text = str(text).strip()
    match = re.fullmatch(r"[（(]?\s*(\d{1,3})\s*[）)]?", text)
    if match:
        return int(match.group(1))
    match = re.search(r"\bS\d{1,2}E(\d{1,3})\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"第\s*(\d+)\s*[话話集幕]", str(text))
    if match:
        return int(match.group(1))

    match = re.search(r"\b[Ee][Pp]?\s*(\d{1,3})\b", str(text))
    if match:
        return int(match.group(1))

    return None


def is_episode_title(title: str) -> bool:
    return not any(word in title.casefold() for word in NON_EPISODE_TITLE_KEYWORDS)


def send_discord_message(webhook_url: str, payload: dict, thread_id: str | None) -> dict:
    params = {"wait": "true"}
    if thread_id:
        params["thread_id"] = thread_id
    try:
        resp = requests.post(
            append_query(webhook_url, params),
            json={**payload, "allowed_mentions": {"parse": []}},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise RuntimeError("Discord delivery uncertain; check receipts before retrying") from None
    if resp.status_code != 200:
        raise RuntimeError(f"Discord delivery failed: HTTP {resp.status_code}")
    message = resp.json()
    if not message.get("id") or not message.get("channel_id"):
        raise RuntimeError("Discord response has no message receipt")
    if thread_id and str(message["channel_id"]) != str(thread_id):
        raise RuntimeError("Discord receipt belongs to a different thread")
    return {"message_id": str(message["id"]), "thread_id": str(message["channel_id"])}


def append_query(url: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def record_episode_notification(state: dict, thread_key: str) -> None:
    health = state.setdefault("weekly_health", {}).setdefault(thread_key, {})
    health["last_episode_notification_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    health.pop("alerted_for", None)
    health.pop("alerted_at", None)


def get_active_thread_keys() -> set[str]:
    return set(get_active_source_ids_by_thread())


def get_active_source_ids_by_thread() -> dict[str, set[str]]:
    source_ids: dict[str, set[str]] = {}

    def add(thread_key: str, source_id: str) -> None:
        if thread_key not in COMPLETED_THREADS:
            source_ids.setdefault(thread_key, set()).add(source_id)

    for bvid in WATCH_VIDEOS:
        add(THREAD_KEY_OVERRIDES.get(bvid, bvid), f"video:{bvid}")
    for monitor in UPLOAD_MONITORS:
        add(monitor["thread_key"], f"upload:{monitor['mid']}:{monitor['thread_key']}")
    for monitor in ANIME1_MONITORS:
        add(
            monitor["thread_key"],
            f"anime1:{monitor.get('feed_url') or monitor['url']}:{monitor['thread_key']}",
        )
    for monitor in BANGUMI_MONITORS:
        add(monitor["thread_key"], f"bangumi:{monitor['season_id']}")
    for monitor in YOUTUBE_MONITORS:
        add(monitor["thread_key"], f"youtube:{monitor['channel_id']}")

    return source_ids


def check_weekly_update_health(
    webhook_url: str,
    state: dict,
    checked_source_ids: dict[str, set[str]],
) -> bool:
    now = datetime.now(TIMEZONE)
    health_state = state.setdefault("weekly_health", {})
    threads = state.setdefault("threads", {})
    source_ids_by_thread = get_active_source_ids_by_thread()

    for thread_key in sorted(source_ids_by_thread):
        thread = threads.get(thread_key) or {}
        thread_id = thread.get("thread_id")
        if not thread_id:
            continue

        expected_source_ids = source_ids_by_thread[thread_key]
        missing_source_ids = expected_source_ids - checked_source_ids.get(thread_key, set())
        health = health_state.setdefault(thread_key, {})
        last_notification_text = health.get("last_episode_notification_at")
        if not last_notification_text:
            health["last_episode_notification_at"] = now.isoformat(timespec="seconds")
            continue

        try:
            last_notification = datetime.fromisoformat(last_notification_text)
            if last_notification.tzinfo is None:
                last_notification = last_notification.replace(tzinfo=TIMEZONE)
        except (TypeError, ValueError):
            health["last_episode_notification_at"] = now.isoformat(timespec="seconds")
            health.pop("alerted_for", None)
            continue

        if now - last_notification < WEEKLY_UPDATE_TIMEOUT:
            continue
        if health.get("alerted_for") == last_notification_text:
            continue

        title = thread.get("title") or thread_key
        status_text = (
            "已超過 7 天沒有發片通知；本次部分來源查詢失敗，無法確認是否有新集數。"
            if missing_source_ids else
            "已超過 7 天沒有偵測到下一集。今日已重新檢查設定來源，仍未找到新內容。"
        )
        payload = {
            "content": "\n".join(
                [
                    "追番監控異常提醒喵",
                    f"追蹤：{title}",
                    f"最近一次發片通知：{last_notification.astimezone(TIMEZONE).strftime('%Y-%m-%d %H:%M')}",
                    status_text,
                    "可能原因：來源刪文、改用新網址、官方延期，或日本重大節日停播。",
                    "請人工確認來源狀態。",
                ]
            )
        }
        receipt = send_discord_message(webhook_url, payload, thread_id)
        health["alerted_for"] = last_notification_text
        health["alerted_at"] = now.isoformat(timespec="seconds")
        health["alert_receipt"] = receipt
        health["source_check_complete"] = not missing_source_ids
        save_state(state)
        print(f"[ALERT] {title} has no episode notification for 7 days")

    return True


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


def format_bilibili_page_url(
    video_url: str,
    page_no: int | str,
    suppress_embed: bool = False,
) -> str:
    url = f"{video_url}?p={page_no}"
    return f"<{url}>" if suppress_embed else url


def post_to_discord(
    webhook_url: str,
    info: dict,
    new_pages: list[dict],
    state: dict,
    thread_key: str,
    bootstrap: bool = False,
) -> None:
    if not new_pages:
        raise ValueError("Refusing to announce a video without verified episode pages")
    video_url = f"https://www.vxbilibili.com/video/{info['bvid']}/"
    thread_title = get_thread_title(info, thread_key)
    header = [
        "Bilibili 追番串建立喵" if bootstrap else "Bilibili 影片更新喵",
        f"追蹤：{thread_title}",
        f"原標題：{info['title']}",
    ]
    if info["owner"]:
        header.append(f"UP：{info['owner']}")
    header = "\n".join(header)[:600] + "\n"
    receipts = state.setdefault("delivery_receipts", {})
    pending = [p for p in new_pages if f"bilibili:{info['bvid']}:{p['page']}" not in receipts]
    thread_id = (state.setdefault("threads", {}).get(thread_key) or {}).get("thread_id")
    while pending:
        chunk, lines = [], [header]
        for page in pending:
            number = page["page"]
            url = format_bilibili_page_url(video_url, number, suppress_embed=bool(chunk))
            line = f"- 第{page.get('episode_no') or number}集：P{number} {str(page.get('part') or '')[:160]} {url}"
            if chunk and (len(chunk) >= 10 or len("\n".join(lines + [line])) > 1900):
                break
            chunk.append(page)
            lines.append(line)
        payload = {"content": "\n".join(lines)}
        if not thread_id:
            payload["thread_name"] = truncate_thread_name(f"{FORUM_THREAD_PREFIX} - {thread_title}")
        receipt = send_discord_message(webhook_url, payload, thread_id)
        if not thread_id:
            thread_id = receipt["thread_id"]
            state["threads"][thread_key] = {
                "thread_id": thread_id,
                "title": thread_title,
                "bvid": info["bvid"],
                "created_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
            }
        for page in chunk:
            receipts[f"bilibili:{info['bvid']}:{page['page']}"] = receipt
        record_episode_notification(state, thread_key)
        save_state(state)
        print(f"[DELIVERED] {thread_key} pages {[p['page'] for p in chunk]} message={receipt['message_id']}")
        pending = pending[len(chunk):]


def detect_new_pages(old: dict | None, info: dict) -> list[dict]:
    if not old:
        return []

    old_cids = set(old.get("seen_cids") or [])
    old_pages = old.get("pages") or []
    old_page_numbers = {
        int(page.get("page") or 0)
        for page in old_pages
        if int(page.get("page") or 0) > 0
    }

    if not old_cids and not old_page_numbers:
        old_count = int(old.get("page_count") or 0)
        return [page for page in info["pages"] if page.get("page", 0) > old_count]

    # Bilibili can replace a part's CID without adding an episode.  A changed
    # CID for an already-seen P must not be announced as a new release.
    return [
        page
        for page in info["pages"]
        if page.get("cid")
        and page["cid"] not in old_cids
        and page.get("page") not in old_page_numbers
    ]


def get_latest_pubdate_for_thread(videos: dict, thread_key: str) -> int:
    pubdates = []
    for snapshot in videos.values():
        if snapshot.get("thread_key") != thread_key:
            continue

        try:
            pubdates.append(int(snapshot.get("pubdate") or 0))
        except (TypeError, ValueError):
            pass

    return max(pubdates, default=0)


def find_new_upload_archives(
    session: requests.Session,
    monitor: dict,
    videos: dict,
    archive_cache: dict[str, list[dict]],
) -> list[dict]:
    keywords = monitor.get("keywords") or []
    if not keywords:
        return []

    mid = str(monitor["mid"])
    if mid not in archive_cache:
        resp = session.get(
            "https://api.bilibili.com/x/series/recArchivesByKeywords",
            params={
                "mid": mid,
                "keywords": "",
                "ps": UPLOAD_SEARCH_PAGE_SIZE,
                "pn": 1,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(
                f"Bilibili upload search error for {monitor.get('name')}: "
                f"{payload.get('code')} {payload.get('message')}"
            )
        archive_cache[mid] = ((payload.get("data") or {}).get("archives") or [])

    thread_key = monitor["thread_key"]
    baseline = min(
        (int(s.get("pubdate") or 0) for s in videos.values()
         if s.get("thread_key") == thread_key and s.get("pubdate")),
        default=0,
    )
    if not baseline:
        return []

    matches = []
    for archive in archive_cache[mid]:
        bvid = archive.get("bvid")
        title = archive.get("title") or ""
        pubdate = int(archive.get("pubdate") or 0)
        if not bvid or pubdate < baseline:
            continue
        if not any(keyword.casefold() in title.casefold() for keyword in keywords):
            continue
        if not is_episode_title(title):
            continue
        if monitor.get("require_episode_number") and extract_episode_no(title) is None:
            continue

        matches.append(archive)

    return sorted(matches, key=lambda archive: int(archive.get("pubdate") or 0))


def check_upload_monitor(
    session: requests.Session,
    webhook_url: str,
    state: dict,
    monitor: dict,
    archive_cache: dict[str, list[dict]],
) -> bool:
    videos = state.setdefault("videos", {})
    new_archives = find_new_upload_archives(session, monitor, videos, archive_cache)
    if not new_archives:
        print(f"[NOOP] {monitor.get('name')} upload search: {monitor.get('thread_key')} no new videos")
        return True

    failures = []
    for archive in new_archives:
        bvid = archive["bvid"]
        thread_key = monitor["thread_key"]
        try:
            info = get_video_info(session, bvid)
            if info["owner_mid"] != str(monitor["mid"]):
                raise RuntimeError(f"Uploader mismatch for {bvid}")
            if not any(k.casefold() in info["title"].casefold() for k in monitor["keywords"]):
                raise RuntimeError(f"Title mismatch for {bvid}")
        except Exception as exc:
            failures.append(bvid)
            print(f"[WARN] upload {bvid}: {exc}")
            continue
        pages_to_post = info["pages"][:1] if monitor.get("first_page_only") else info["pages"]
        if monitor.get("first_page_only") and pages_to_post and extract_episode_no(info["title"]):
            pages_to_post[0]["episode_no"] = extract_episode_no(info["title"])
        if bvid in videos:
            added = {p["page"] for p in detect_new_pages(videos[bvid], info)}
            pages_to_post = [p for p in pages_to_post if p["page"] in added]
        pages_to_post = select_unseen_episodes(videos, thread_key, pages_to_post)
        print(f"[NEW] {monitor.get('name')} uploaded {bvid} for {thread_key}")
        if pages_to_post:
            post_to_discord(webhook_url, info, pages_to_post, state, thread_key)
        videos[bvid] = make_snapshot(info, thread_key)
        save_state(state)

    if failures:
        raise RuntimeError(f"Upload metadata unavailable: {', '.join(failures)}")
    return True


def select_unseen_episodes(videos: dict, thread_key: str, pages: list[dict]) -> list[dict]:
    seen = set()
    for old in videos.values():
        if old.get("thread_key") != thread_key or not is_episode_title(old.get("title", "")):
            continue
        for page in old.get("pages") or []:
            number = page.get("episode_no") or extract_episode_no(page.get("part", ""))
            if number:
                seen.add(int(number))
    return [page for page in pages if int(page.get("episode_no") or 0) not in seen]


def get_bangumi_episodes(session: requests.Session, season_id: str) -> list[dict]:
    resp = session.get(
        "https://api.bilibili.com/pgc/view/web/season",
        params={"season_id": season_id},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"Bilibili Bangumi season error {season_id}: "
            f"{payload.get('code')} {payload.get('message')}"
        )

    episodes = []
    for episode in (payload.get("result") or {}).get("episodes") or []:
        bvid = episode.get("bvid")
        badge = str(episode.get("badge") or "")
        if not bvid or "预告" in badge:
            continue

        episodes.append(
            {
                "bvid": bvid,
                "episode_no": episode.get("title"),
                "long_title": episode.get("long_title") or "",
                "pubdate": int(episode.get("pub_time") or 0),
            }
        )

    return sorted(episodes, key=lambda episode: episode["pubdate"])


def check_bangumi_monitor(
    session: requests.Session,
    webhook_url: str,
    state: dict,
    monitor: dict,
) -> bool:
    videos = state.setdefault("videos", {})
    thread_key = monitor["thread_key"]
    episodes = get_bangumi_episodes(session, monitor["season_id"])
    if not episodes:
        raise RuntimeError(f"Bangumi season {monitor['season_id']} returned no released episodes")

    monitor_state = state.setdefault("bangumi", {}).setdefault(thread_key, {})
    latest_seen_pubdate = max(
        get_latest_pubdate_for_thread(videos, thread_key),
        int(monitor_state.get("last_seen_pubdate") or 0),
    )
    if not latest_seen_pubdate:
        monitor_state["last_seen_pubdate"] = max(episode["pubdate"] for episode in episodes)
        monitor_state["last_checked_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
        print(f"[INIT] Bangumi {monitor.get('name')} saved {len(episodes)} existing episodes")
        return True

    new_episodes = [
        episode
        for episode in episodes
        if episode["bvid"] not in videos
        and episode["pubdate"] > latest_seen_pubdate
    ]
    for episode in new_episodes:
        info = get_video_info(session, episode["bvid"])
        if not info["pages"]:
            raise RuntimeError(f"Bangumi episode {episode['bvid']} has no playable pages")

        page = dict(info["pages"][0])
        page["episode_no"] = episode["episode_no"]
        page["part"] = episode["long_title"] or page["part"]
        print(f"[NEW] Bangumi {monitor.get('name')} episode {episode['episode_no']}")
        post_to_discord(webhook_url, info, [page], state, thread_key)
        videos[episode["bvid"]] = make_snapshot(info, thread_key)

    monitor_state.pop("seen_bvids", None)
    monitor_state["last_seen_pubdate"] = max(episode["pubdate"] for episode in episodes)
    monitor_state["last_checked_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    print(
        f"[NOOP] Bangumi {monitor.get('name')} no new episodes"
        if not new_episodes
        else f"[OK] Bangumi {monitor.get('name')} posted {len(new_episodes)} episodes"
    )
    return True


def get_anime1_entries(session: requests.Session, source_url: str) -> list[dict]:
    resp = session.get(source_url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    entries = []
    for url, raw_title, published_at in ANIME1_ENTRY_RE.findall(resp.text):
        entry_url = unescape(url).strip()
        post_id = entry_url.rstrip("/").rsplit("/", 1)[-1]
        if not post_id.isdigit():
            continue

        title = re.sub(r"<[^>]+>", "", unescape(raw_title)).strip()
        episode_match = re.search(r"\[(\d+)\]", title)
        entries.append(
            {
                "id": post_id,
                "title": title,
                "episode_no": int(episode_match.group(1)) if episode_match else None,
                "url": entry_url,
                "published_at": published_at,
            }
        )

    return entries


def get_anime1_telegram_entries(
    session: requests.Session,
    source_url: str,
    title_keywords: list[str],
) -> list[dict]:
    resp = session.get(source_url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    parser = Anime1TelegramParser()
    parser.feed(resp.text)
    entries = []
    seen_ids = set()
    for entry in parser.entries:
        if entry["id"] in seen_ids:
            continue
        if not any(keyword in entry["title"] for keyword in title_keywords):
            continue
        seen_ids.add(entry["id"])
        entries.append(entry)
    return entries


def post_anime1_to_discord(
    webhook_url: str,
    entry: dict,
    state: dict,
    monitor: dict,
) -> None:
    thread_key = monitor["thread_key"]
    thread = (state.setdefault("threads", {}).get(thread_key) or {})
    thread_id = thread.get("thread_id")
    if not thread_id:
        raise RuntimeError(f"Missing Discord thread for Anime1 monitor: {thread_key}")

    episode_no = entry.get("episode_no")
    episode_text = f"第{episode_no}集" if episode_no is not None else entry["title"]
    label = monitor["label"]
    payload = {
        "content": "\n".join(
            [
                "Anime1 影片更新喵",
                f"追蹤：{thread.get('title') or thread_key}",
                f"版本：{label}",
                f"原標題：{entry['title']}",
                "",
                f"- {episode_text}：{label} {entry['url']}",
            ]
        )
    }
    key = f"anime1:{thread_key}:{entry['id']}"
    receipts = state.setdefault("delivery_receipts", {})
    if key in receipts:
        return
    receipts[key] = send_discord_message(webhook_url, payload, thread_id)
    record_episode_notification(state, thread_key)
    save_state(state)


def check_anime1_monitor(
    session: requests.Session,
    webhook_url: str,
    state: dict,
    monitor: dict,
) -> bool:
    anime1_state = state.setdefault("anime1", {})
    state_key = monitor["thread_key"]
    old = anime1_state.get(state_key)
    feed_url = monitor.get("feed_url")
    if feed_url:
        entries = get_anime1_telegram_entries(
            session,
            feed_url,
            monitor.get("title_keywords") or [],
        )
        if not entries and old and old.get("source_url") == monitor["url"]:
            old["last_checked_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
            print(f"[NOOP] Anime1 {state_key} no matching recent feed entries")
            return True
    else:
        entries = get_anime1_entries(session, monitor["url"])

    if not entries:
        raise RuntimeError("Anime1 source returned no episode entries")

    current_ids = [entry["id"] for entry in entries]
    if not old or old.get("source_url") != monitor["url"]:
        anime1_state[state_key] = {
            "source_url": monitor["url"],
            "seen_post_ids": current_ids,
            "last_checked_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        }
        print(f"[INIT] Anime1 {state_key} saved {len(current_ids)} existing episodes")
        return True

    seen_post_ids = set(old.get("seen_post_ids") or [])
    new_entries = [entry for entry in entries if entry["id"] not in seen_post_ids]
    for entry in sorted(new_entries, key=lambda item: int(item["id"])):
        print(f"[NEW] Anime1 {entry['title']} for {state_key}")
        post_anime1_to_discord(webhook_url, entry, state, monitor)
        seen_post_ids.add(entry["id"])
        old["seen_post_ids"] = sorted(seen_post_ids, key=int, reverse=True)
        save_state(state)

    old["seen_post_ids"] = sorted(
        seen_post_ids | set(current_ids),
        key=int,
        reverse=True,
    )[:200]
    old["last_checked_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    print(f"[NOOP] Anime1 {state_key} no new episodes" if not new_entries else f"[OK] Anime1 posted {len(new_entries)} episodes")
    return True


def get_youtube_entries(session: requests.Session, channel_id: str) -> list[dict]:
    resp = session.get(
        "https://www.youtube.com/feeds/videos.xml",
        params={"channel_id": channel_id},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise RuntimeError(f"YouTube RSS parse error for {channel_id}: {exc}") from exc

    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    entries = []
    for item in root.findall("atom:entry", namespaces):
        video_id = item.findtext("yt:videoId", namespaces=namespaces)
        title = item.findtext("atom:title", namespaces=namespaces) or ""
        published_at = item.findtext("atom:published", namespaces=namespaces) or ""
        if not video_id:
            continue

        entries.append(
            {
                "id": video_id,
                "title": title,
                "episode_no": extract_episode_no(title),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": published_at,
            }
        )

    return entries


def post_youtube_to_discord(
    webhook_url: str,
    entry: dict,
    state: dict,
    monitor: dict,
) -> None:
    thread_key = monitor["thread_key"]
    thread = (state.setdefault("threads", {}).get(thread_key) or {})
    thread_id = thread.get("thread_id")
    if not thread_id:
        raise RuntimeError(f"Missing Discord thread for YouTube monitor: {thread_key}")

    episode_label = entry.get("episode_label")
    if not episode_label:
        episode_no = entry.get("episode_no")
        episode_label = f"第{episode_no}集" if episode_no is not None else entry["title"]
    payload = {
        "content": "\n".join(
            [
                "YouTube 影片更新喵",
                f"追蹤：{thread.get('title') or thread_key}",
                "來源：YouTube",
                f"原標題：{entry['title']}",
                "",
                f"- {episode_label}：{entry['url']}",
            ]
        )
    }
    key = f"youtube:{thread_key}:{entry['id']}"
    receipts = state.setdefault("delivery_receipts", {})
    if key in receipts:
        return
    receipts[key] = send_discord_message(webhook_url, payload, thread_id)
    record_episode_notification(state, thread_key)
    save_state(state)


def check_youtube_monitor(
    session: requests.Session,
    webhook_url: str,
    state: dict,
    monitor: dict,
) -> bool:
    keywords = monitor.get("keywords") or []
    entries = [
        entry
        for entry in get_youtube_entries(session, monitor["channel_id"])
        if any(keyword in entry["title"] for keyword in keywords)
    ]

    youtube_state = state.setdefault("youtube", {})
    state_key = monitor["thread_key"]
    old = youtube_state.get(state_key)
    current_ids = [entry["id"] for entry in entries]
    if not old or old.get("channel_id") != monitor["channel_id"]:
        youtube_state[state_key] = {
            "channel_id": monitor["channel_id"],
            "seen_video_ids": current_ids,
            "last_checked_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        }
        print(f"[INIT] YouTube {state_key} saved {len(current_ids)} existing videos")
        return True

    seen_video_ids = set(old.get("seen_video_ids") or [])
    new_entries = [entry for entry in entries if entry["id"] not in seen_video_ids]
    for entry in sorted(new_entries, key=lambda item: item["published_at"]):
        print(f"[NEW] YouTube {entry['title']} for {state_key}")
        post_youtube_to_discord(webhook_url, entry, state, monitor)
        seen_video_ids.add(entry["id"])
        old["seen_video_ids"] = sorted(seen_video_ids)
        save_state(state)

    old["seen_video_ids"] = sorted(seen_video_ids | set(current_ids))[-100:]
    old["last_checked_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    print(f"[NOOP] YouTube {state_key} no new videos" if not new_entries else f"[OK] YouTube posted {len(new_entries)} videos")
    return True


def check_fixed_video(session, webhook_url, state, bvid, bootstrap_threads=False) -> bool:
    videos = state.setdefault("videos", {})
    old = videos.get(bvid)
    info = get_video_info(session, bvid)
    if not info["pages"]:
        raise RuntimeError(f"No episode pages for {bvid}")
    thread_key = get_thread_key(info)
    new_pages = detect_new_pages(old, info)
    if bootstrap_threads and not state["threads"].get(thread_key):
        post_to_discord(webhook_url, info, info["pages"], state, thread_key, bootstrap=True)
    elif new_pages:
        post_to_discord(webhook_url, info, new_pages, state, thread_key)
    else:
        print(f"[NOOP] {bvid}: {'no new pages' if old else 'baseline saved'}")
    videos[bvid] = make_snapshot(info, thread_key)
    return True


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
    cookie = os.environ.get("BILIBILI_COOKIE")
    if should_skip_daily_check(state, today, force):
        print(f"[OK] Bilibili already checked today ({today}); skip")
        return

    session = make_source_session(cookie or "")
    if not cookie:
        print("[INFO] Using public Bilibili sources; login Cookie is optional")
    success_count = 0
    expected_count = sum(len(ids) for ids in get_active_source_ids_by_thread().values())
    checked_source_ids: dict[str, set[str]] = {}
    failures = {}

    def run_check(thread_key, source_id, check, *args):
        nonlocal success_count
        if thread_key in COMPLETED_THREADS:
            return
        try:
            if check(session, webhook_url, state, *args):
                checked_source_ids.setdefault(thread_key, set()).add(source_id)
                success_count += 1
        except Exception as exc:
            failures[source_id] = str(exc)
            print(f"[WARN] {source_id}: {exc}")
        finally:
            save_state(state)

    for bvid in WATCH_VIDEOS:
        run_check(THREAD_KEY_OVERRIDES.get(bvid, bvid), f"video:{bvid}",
                  check_fixed_video, bvid, bootstrap_threads)
    for monitor in BANGUMI_MONITORS:
        run_check(monitor["thread_key"], f"bangumi:{monitor['season_id']}",
                  check_bangumi_monitor, monitor)
    upload_archive_cache = {}
    for monitor in UPLOAD_MONITORS:
        run_check(monitor["thread_key"], f"upload:{monitor['mid']}:{monitor['thread_key']}",
                  check_upload_monitor, monitor, upload_archive_cache)
    for monitor in ANIME1_MONITORS:
        run_check(monitor["thread_key"],
                  f"anime1:{monitor.get('feed_url') or monitor['url']}:{monitor['thread_key']}",
                  check_anime1_monitor, monitor)
    for monitor in YOUTUBE_MONITORS:
        run_check(monitor["thread_key"], f"youtube:{monitor['channel_id']}",
                  check_youtube_monitor, monitor)

    health_success = False
    try:
        health_success = check_weekly_update_health(webhook_url, state, checked_source_ids)
    except Exception as exc:
        failures["weekly_health"] = str(exc)
        print(f"[WARN] weekly update health check failed: {repr(exc)}")

    state["last_checked_date"] = today
    state["last_check_complete"] = success_count == expected_count and health_success
    state.pop("last_check_blocked", None)
    state["last_check_failures"] = failures
    state["last_checked_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    save_state(state)
    print(f"[SUMMARY] Checked {success_count}/{expected_count}; failures={len(failures)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

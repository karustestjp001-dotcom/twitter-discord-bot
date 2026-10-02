"""Replay a reviewed repair plan. Dry-run by default; never infer episode URLs."""

import argparse
import json
import os
from pathlib import Path

import requests

import bilibili_monitor as monitor


def verify_receipt(webhook, receipt, bvid):
    url = monitor.append_query(
        f"{webhook.rstrip('/')}/messages/{receipt['message_id']}",
        {"thread_id": receipt["thread_id"]},
    )
    try:
        response = requests.get(url, timeout=monitor.REQUEST_TIMEOUT)
    except requests.RequestException:
        raise RuntimeError("Discord receipt readback failed") from None
    if response.status_code != 200:
        raise RuntimeError(f"Discord receipt readback HTTP {response.status_code}")
    message = response.json()
    if (str(message.get("channel_id")) != receipt["thread_id"]
            or str(message.get("id")) != receipt["message_id"]
            or f"www.vxbilibili.com/video/{bvid}/" not in message.get("content", "")):
        raise RuntimeError("Discord receipt content mismatch")
    print(f"[VERIFIED] Discord message={receipt['message_id']} thread={receipt['thread_id']}")


def prepare_item(session, state, item):
    key = item["thread_key"]
    if not (state.get("threads", {}).get(key) or {}).get("thread_id"):
        raise ValueError(f"Missing existing Discord thread: {key}")
    info = monitor.get_video_info(session, item["bvid"])
    if item["title_keyword"] not in info["title"] or info["owner_mid"] != item["owner_mid"]:
        raise ValueError(f"Repair source identity changed: {item['bvid']}")
    requested = set(item["episodes"])
    pages = [p for p in info["pages"] if p["episode_no"] in requested]
    if {p["episode_no"] for p in pages} != requested or len(pages) != len(requested):
        raise ValueError(f"Missing or ambiguous episode pages: {item['bvid']}")
    return info, pages


def run(plan_path, send=False):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    state = monitor.load_state()
    session = monitor.make_source_session(os.environ.get("BILIBILI_COOKIE", ""))
    webhook = os.environ.get(monitor.WEBHOOK_ENV)
    if send and not webhook:
        raise ValueError("Missing Discord webhook environment variable")
    # Verify every source before sending the first item.
    prepared = [(item, *prepare_item(session, state, item)) for item in plan["items"]]
    for item, info, pages in prepared:
        print(f"[PLAN] {item['thread_key']} {info['bvid']} episodes {[p['episode_no'] for p in pages]}")
        if not send:
            continue
        monitor.post_to_discord(webhook, info, pages, state, item["thread_key"])
        receipts = {state["delivery_receipts"][f"bilibili:{info['bvid']}:{p['page']}"]["message_id"]:
                    state["delivery_receipts"][f"bilibili:{info['bvid']}:{p['page']}"] for p in pages}
        for receipt in receipts.values():
            verify_receipt(webhook, receipt, info["bvid"])
        state.setdefault("videos", {})[info["bvid"]] = monitor.make_snapshot(info, item["thread_key"])
        state.setdefault("repair_batches", {}).setdefault(plan["id"], {})[item["thread_key"]] = {
            "bvid": info["bvid"],
            "episodes": item["episodes"],
            "receipts": [state["delivery_receipts"][f"bilibili:{info['bvid']}:{p['page']}"] for p in pages],
        }
        monitor.save_state(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    run(args.plan, args.send)

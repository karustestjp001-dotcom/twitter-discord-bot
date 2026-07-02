"""
main.py - Twitter → Discord 自動轉發機器人

功能：
- 使用 twikit 以 cookie 登入 Twitter/X
- 掃描 config.py 中所有帳號的最新推文
- 過濾：只轉發含有圖片或影片的原創推文（跳過轉推）
- 將連結轉換為 fixupx.com 格式（Discord 可直接播放）
- 發送至對應的 Discord Webhook
- 記錄最後看到的推文 ID，避免重複發送
"""

import asyncio
import json
import os
import time

import requests
from twikit import Client

from config import CHANNELS

COOKIES_FILE = "cookies.json"
LAST_SEEN_FILE = "last_seen.json"
REQUEST_DELAY = 3      # 每個帳號之間的間隔（秒），避免被限速
DISCORD_DELAY = 0.5    # Discord 發文間隔（秒）
TWEETS_PER_USER = 15   # 每個帳號最多抓幾則推文


# ── 工具函式 ────────────────────────────────────────────────

def load_last_seen() -> dict:
    """讀取上次執行時記錄的最新推文 ID"""
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_last_seen(data: dict):
    """將最新推文 ID 存回檔案"""
    with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_new_tweet(tweet_id: str, last_id: str) -> bool:
    """比較推文 ID（Snowflake ID，數字越大越新）"""
    try:
        return int(tweet_id) > int(last_id)
    except ValueError:
        return False


def should_post(tweet) -> bool:
    """
    判斷是否要轉發這則推文：
    - 必須是原創推文（非轉推）
    - 必須含有圖片或影片
    """
    # 跳過轉推
    if getattr(tweet, "retweeted_tweet", None):
        return False
    # 必須有 media（圖片/影片/GIF）
    return bool(getattr(tweet, "media", None))


def post_to_discord(webhook_url: str, username: str, tweet_id: str, channel_name: str):
    """將推文連結以 fixupx.com 格式發送到 Discord"""
    link = f"https://fixupx.com/{username}/status/{tweet_id}"
    payload = {"content": link}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            print(f"  ✅ [{channel_name}] 發送成功：{link}")
        else:
            print(f"  ❌ [{channel_name}] Discord 錯誤 {resp.status_code}：{resp.text[:200]}")
    except requests.RequestException as e:
        print(f"  ❌ [{channel_name}] 發送失敗：{e}")

    time.sleep(DISCORD_DELAY)


# ── 主程式 ──────────────────────────────────────────────────

async def main():
    # 初始化 twikit client
    client = Client("en-US")

    # 優先使用已儲存的 cookies（避免每次重新登入觸發驗證）
    if os.path.exists(COOKIES_FILE):
        print("📂 使用已儲存的 cookies 登入...")
        client.load_cookies(COOKIES_FILE)
    else:
        print("🔑 首次登入，使用帳號密碼...")
        await client.login(
            auth_info_1=os.environ["TWITTER_USERNAME"],
            auth_info_2=os.environ["TWITTER_EMAIL"],
            password=os.environ["TWITTER_PASSWORD"],
        )
        client.save_cookies(COOKIES_FILE)
        print("✅ 登入成功，cookies 已儲存")

    # 讀取上次的進度
    last_seen = load_last_seen()

    # 整合各頻道帳號：username -> [{"webhook": ..., "name": ...}, ...]
    # 如果同一帳號在多個頻道，會分別發到各頻道
    account_channels: dict[str, list] = {}
    for channel in CHANNELS:
        webhook_url = os.environ.get(channel["webhook_env"])
        if not webhook_url:
            print(f"⚠️  找不到 Webhook：{channel['webhook_env']}，跳過頻道 {channel['name']}")
            continue
        for raw_name in channel["accounts"]:
            key = raw_name.lower()
            if key not in account_channels:
                account_channels[key] = []
            account_channels[key].append(
                {"webhook": webhook_url, "name": channel["name"], "original": raw_name}
            )

    total = len(account_channels)
    print(f"\n🔍 開始掃描 {total} 個帳號...\n")

    for idx, (username_key, channels) in enumerate(account_channels.items(), 1):
        original_name = channels[0]["original"]  # 用原始大小寫查詢
        print(f"[{idx}/{total}] 查詢 @{original_name} ...")

        try:
            # 用帳號名稱取得 user 物件
            user = await client.get_user_by_screen_name(original_name)
            tweets = await client.get_user_tweets(user.id, "Tweets", count=TWEETS_PER_USER)

            last_id = last_seen.get(username_key, "0")
            is_first_run = last_id == "0"

            if is_first_run:
                # 第一次執行：只記錄位置，不發送（避免一次性洗版）
                if tweets:
                    last_seen[username_key] = str(tweets[0].id)
                    print(f"  📌 首次執行，記錄至推文 ID {tweets[0].id}（不發送歷史貼文）")
            else:
                # 找出比上次更新的推文
                new_media_tweets = []
                newest_id = last_id

                for tweet in tweets:
                    tweet_id = str(tweet.id)
                    if not is_new_tweet(tweet_id, last_id):
                        break  # 推文按時間倒序，遇到舊的就停
                    if int(tweet_id) > int(newest_id):
                        newest_id = tweet_id
                    if should_post(tweet):
                        new_media_tweets.append(tweet)

                if new_media_tweets:
                    print(f"  🆕 發現 {len(new_media_tweets)} 則新圖文推文，準備發送...")
                    # 從舊到新發送（不要倒序洗版）
                    for tweet in reversed(new_media_tweets):
                        for ch in channels:
                            post_to_discord(ch["webhook"], original_name, str(tweet.id), ch["name"])
                else:
                    print(f"  ➖ 無新圖文推文")

                # 更新進度（記最新的推文 ID，無論是否含媒體）
                if tweets and is_new_tweet(str(tweets[0].id), last_seen.get(username_key, "0")):
                    last_seen[username_key] = str(tweets[0].id)

        except Exception as e:
            print(f"  ⚠️  @{original_name} 發生錯誤：{e}")
            time.sleep(5)
            continue

        time.sleep(REQUEST_DELAY)

    # 儲存進度
    save_last_seen(last_seen)
    print("\n✅ 掃描完成，進度已儲存！")


if __name__ == "__main__":
    asyncio.run(main())

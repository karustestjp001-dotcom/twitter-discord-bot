"""
main.py - Twitter → Discord 自動轉發機器人

功能：
- 使用 twikit 以 cookie 登入 Twitter/X
- 載入 Monkeypatch 修正官方 twikit 的漏洞
- 掃描 config.py 中所有帳號的最新推文
- 過濾：只轉發含有圖片或影片的原創推文（跳過轉推）
- 將連結轉換為 fixupx.com 格式（Discord 可直接播放）
- 發送至對應的 Discord Webhook
- 記錄最後看到的推文 ID，避免重複發送
"""

# ==============================================================================
# Monkeypatch twikit 以修正 KEY_BYTE indices 與 User KeyError 的 Bug
# 這樣在 GitHub Actions 標準環境中執行時，不需要手動去修改第三方套件檔案
# ==============================================================================
import twikit.x_client_transaction.transaction as tx

async def patched_get_indices(self, home_page_response, session, headers):
    key_byte_indices = []
    try:
        response = self.validate_response(
            home_page_response) or self.home_page_response
        on_demand_file = tx.ON_DEMAND_FILE_REGEX.search(str(response))
        if on_demand_file:
            on_demand_file_url = f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{on_demand_file.group(1)}a.js"
            on_demand_file_response = await session.request(method="GET", url=on_demand_file_url, headers=headers)
            key_byte_indices_match = tx.INDICES_REGEX.finditer(
                str(on_demand_file_response.text))
            for item in key_byte_indices_match:
                key_byte_indices.append(item.group(2))
    except Exception:
        pass
    if not key_byte_indices:
        # Fallback 預設值
        return 2, [12, 14, 7]
    key_byte_indices = list(map(int, key_byte_indices))
    return key_byte_indices[0], key_byte_indices[1:]

tx.ClientTransaction.get_indices = patched_get_indices

import twikit.user as tu
original_user_init = tu.User.__init__

def patched_user_init(self, client, data):
    if 'legacy' in data:
        legacy = data['legacy']
        defaults = {
            'pinned_tweet_ids_str': [],
            'verified': False,
            'possibly_sensitive': False,
            'can_dm': False,
            'can_media_tag': False,
            'want_retweets': False,
            'default_profile': False,
            'default_profile_image': False,
            'has_custom_timelines': False,
            'followers_count': 0,
            'fast_followers_count': 0,
            'normal_followers_count': 0,
            'friends_count': 0,
            'favourites_count': 0,
            'listed_count': 0,
            'media_count': 0,
            'statuses_count': 0,
            'is_translator': False,
            'translator_type': 'none',
            'withheld_in_countries': []
        }
        for k, v in defaults.items():
            if k not in legacy:
                legacy[k] = v
        
        if 'entities' not in legacy:
            legacy['entities'] = {}
        if 'description' not in legacy['entities']:
            legacy['entities']['description'] = {'urls': []}
        elif 'urls' not in legacy['entities']['description']:
            legacy['entities']['description']['urls'] = []
            
        if 'url' not in legacy['entities']:
            legacy['entities']['url'] = {'urls': []}
            
    if 'is_blue_verified' not in data:
        data['is_blue_verified'] = False
        
    original_user_init(self, client, data)

tu.User.__init__ = patched_user_init
# ==============================================================================

import asyncio
import json
import os
import time

import requests
from twikit import Client

from config import CHANNELS

COOKIES_FILE = "cookies.json"
LAST_SEEN_FILE = "last_seen.json"
REQUEST_DELAY = 5      # 每個帳號之間的間隔（秒），調高一點以避免被 Twitter Rate Limit
DISCORD_DELAY = 1.0    # Discord 發文間隔（秒）
TWEETS_PER_USER = 10   # 每個帳號最多抓幾則推文


# ── 工具函式 ────────────────────────────────────────────────

def load_last_seen() -> dict:
    """讀取上次執行時記錄的最新推文 ID"""
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
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
        resp = requests.post(webhook_url, json=payload, timeout=15)
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

    # 載入 cookies
    if os.path.exists(COOKIES_FILE):
        print("📂 載入 cookies.json...")
        client.load_cookies(COOKIES_FILE)
        print("✅ 載入成功")
    else:
        print("❌ 錯誤：找不到 cookies.json，請確認是否有成功建立！")
        return

    # 讀取上次的進度
    last_seen = load_last_seen()

    # 整合各頻道帳號：username -> [{"webhook": ..., "name": ...}, ...]
    account_channels = {}
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

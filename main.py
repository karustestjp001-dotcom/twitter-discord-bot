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
USER_IDS_FILE = "user_ids.json"
REQUEST_DELAY = 8      # 每個帳號之間的間隔（秒），調至 8 秒更安全，符合 Twitter 頻率限制
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


def load_user_ids() -> dict:
    """讀取已快取的作者 ID"""
    if os.path.exists(USER_IDS_FILE):
        with open(USER_IDS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save_user_ids(data: dict):
    """儲存作者 ID 快取"""
    with open(USER_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_new_tweet(tweet_id: str, last_id: str) -> bool:
    """比較推文 ID（Snowflake ID，數字越大越新）"""
    try:
        return int(tweet_id) > int(last_id)
    except ValueError:
        return False


def should_post(tweet, media_type="any") -> bool:
    """
    判斷是否要轉發這則推文：
    - 必須是原創推文（非轉推）
    - 必須含有合適的圖片或影片
    """
    # 跳過轉推
    if getattr(tweet, "retweeted_tweet", None):
        return False
        
    media_list = getattr(tweet, "media", None)
    if not media_list:
        return False
        
    if media_type == "video":
        return any(getattr(m, "type", "") == "video" for m in media_list)
    elif media_type == "photo":
        return any(getattr(m, "type", "") == "photo" for m in media_list)
        
    return True


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
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            try:
                cookies_data = json.load(f)
                if isinstance(cookies_data, list):
                    cookies_pool = cookies_data
                else:
                    cookies_pool = [cookies_data]
            except Exception as e:
                print(f"❌ 錯誤：無法解析 cookies.json：{e}")
                return
        cookie_index = 0
        client.set_cookies(cookies_pool[cookie_index])
        print(f"✅ 成功載入 Cookie 池，共 {len(cookies_pool)} 組帳號。目前使用第 1 組。")
    else:
        print("❌ 錯誤：找不到 cookies.json，請確認是否有成功建立！")
        return

    # 讀取上次的進度與快取的 ID
    last_seen = load_last_seen()
    user_ids = load_user_ids()
    user_ids_updated = False

    # 整合各頻道帳號：username -> [{"webhook": ..., "name": ...}, ...]
    account_channels = {}
    for channel in CHANNELS:
        webhook_url = os.environ.get(channel["webhook_env"])
        if not webhook_url:
            print(f"⚠️  找不到 Webhook：{channel['webhook_env']}，跳過頻道 {channel['name']}")
            continue
        for raw_item in channel["accounts"]:
            if isinstance(raw_item, dict):
                original = raw_item["username"]
                media_type = raw_item.get("media_type", "any")
            else:
                original = raw_item
                media_type = "any"
                
            key = original.lower()
            if key not in account_channels:
                account_channels[key] = []
            account_channels[key].append(
                {
                    "webhook": webhook_url,
                    "name": channel["name"],
                    "original": original,
                    "media_type": media_type
                }
            )

    total = len(account_channels)
    print(f"\n🔍 開始掃描 {total} 個帳號...\n")

    consecutive_429s = 0

    stop_scanning = False

    for idx, (username_key, channels) in enumerate(account_channels.items(), 1):
        if stop_scanning:
            break

        original_name = channels[0]["original"]  # 用原始大小寫查詢
        print(f"[{idx}/{total}] 查詢 @{original_name} ...")

        success = False
        retry_count = 0
        while not success and retry_count < 3:
            try:
                # 優先從快取中讀取 ID，避免呼叫 get_user_by_screen_name API
                user_id = user_ids.get(username_key)
                if not user_id:
                    # 快取沒有才查
                    user = await client.get_user_by_screen_name(original_name)
                    user_id = str(user.id)
                    user_ids[username_key] = user_id
                    user_ids_updated = True
                    print(f"  🆕 快取未命中，解析新 ID: {user_id}")
                    time.sleep(2.0) # 查 ID 後額外延遲，避免限制
                
                tweets = await client.get_user_tweets(user_id, "Tweets", count=TWEETS_PER_USER)
                success = True
                
                # 成功執行，重設連續 429 計數
                consecutive_429s = 0

                last_id = last_seen.get(username_key, "0")
                is_first_run = last_id == "0"

                if is_first_run:
                    # 第一次執行：只記錄位置，不發送（避免一次性洗版）
                    if tweets:
                        last_seen[username_key] = str(tweets[0].id)
                        print(f"  📌 首次執行，記錄至推文 ID {tweets[0].id}（不發送歷史貼文）")
                else:
                    # 找出需要發送到各頻道的推文
                    channel_posts = {i: [] for i in range(len(channels))}
                    newest_id = last_id

                    for tweet in tweets:
                        tweet_id = str(tweet.id)
                        if not is_new_tweet(tweet_id, last_id):
                            break  # 推文按時間倒序，遇到舊的就停
                        if int(tweet_id) > int(newest_id):
                            newest_id = tweet_id
                        
                        for c_idx, ch in enumerate(channels):
                            if should_post(tweet, ch.get("media_type", "any")):
                                channel_posts[c_idx].append(tweet)

                    # 發送推文
                    has_posted = False
                    for c_idx, ch in enumerate(channels):
                        to_post = channel_posts[c_idx]
                        if to_post:
                            has_posted = True
                            print(f"  🆕 發現 {len(to_post)} 則新圖文推文，將發送至 [{ch['name']}]...")
                            for tweet in reversed(to_post):
                                post_to_discord(ch["webhook"], original_name, str(tweet.id), ch["name"])
                    
                    if not has_posted:
                        print(f"  ➖ 無新圖文推文")

                    # 更新進度（記最新的推文 ID，無論是否含媒體）
                    if tweets and is_new_tweet(str(tweets[0].id), last_seen.get(username_key, "0")):
                        last_seen[username_key] = str(tweets[0].id)

            except Exception as e:
                print(f"  ⚠️  @{original_name} 發生錯誤：{e}")
                if any(x in str(e) for x in ["429", "401", "403", "Rate limit", "authenticate", "Forbidden"]):
                    consecutive_429s += 1
                    
                    # 1. 優先嘗試切換帳號
                    if cookie_index + 1 < len(cookies_pool):
                        cookie_index += 1
                        print(f"  🔄 [帳號輪替] 偵測到限速或登入失效，正在切換到第 {cookie_index + 1} 組備用帳號...")
                        client.set_cookies(cookies_pool[cookie_index], clear_cookies=True)
                        time.sleep(5)  # 稍等 5 秒後重試
                        retry_count += 1
                        continue
                    
                    # 2. 如果無備用帳號可用且連續失敗次數過高，終止掃描
                    if consecutive_429s >= 3:
                        print("  🚨 所有帳號皆已失效或被限速，終止本次掃描。")
                        stop_scanning = True
                        break
                    
                    # 3. 否則暫停等待
                    print("  ⏳ 偵測到限制且無備用帳號，暫停 120 秒後繼續...")
                    time.sleep(120)
                    retry_count += 1
                else:
                    time.sleep(5)
                    retry_count += 1

        time.sleep(REQUEST_DELAY)

    # 儲存進度與快取
    save_last_seen(last_seen)
    if user_ids_updated:
        save_user_ids(user_ids)
        print("💾 已將新解析的 ID 儲存至 user_ids.json")
    print("\n✅ 掃描完成，進度已儲存！")



if __name__ == "__main__":
    asyncio.run(main())

"""
setup_cookies.py - 從瀏覽器匯出的 Cookie 轉換工具

使用方法：
1. 安裝 Cookie-Editor 瀏覽器擴充功能
2. 在瀏覽器登入 x.com（用備用帳號）
3. 點擊 Cookie-Editor → Export → Export as JSON
4. 執行此腳本，貼上複製的 JSON 內容
"""

import sys
import json
import base64

sys.stdout.reconfigure(encoding="utf-8")


def main():
    print("=" * 55)
    print("  Twitter Cookie 轉換工具")
    print("=" * 55)
    print()
    print("請把從 Cookie-Editor 匯出的 JSON 貼在下方")
    print("（貼完後按 Enter，再輸入一行只有 END 的字，然後按 Enter）")
    print()

    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)

    raw = "\n".join(lines)

    try:
        cookies_list = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f">>> JSON 格式錯誤：{e}")
        return

    # Cookie-Editor 匯出格式是 [{name, value, ...}, ...]
    # twikit 需要的格式是 {name: value, ...}
    if isinstance(cookies_list, list):
        cookies_dict = {c["name"]: c["value"] for c in cookies_list if "name" in c and "value" in c}
    elif isinstance(cookies_list, dict):
        cookies_dict = cookies_list
    else:
        print(">>> 無法識別的格式")
        return

    # 確認關鍵 cookie 存在
    required = ["auth_token", "ct0"]
    missing = [k for k in required if k not in cookies_dict]
    if missing:
        print(f">>> 警告：缺少重要 cookie：{missing}")
        print(">>> 請確認你有在 x.com 登入狀態下匯出")
        return

    # 儲存為 cookies.json
    with open("cookies.json", "w", encoding="utf-8") as f:
        json.dump(cookies_dict, f, indent=2)

    print()
    print(">>> cookies.json 已儲存！")

    # 產生 base64（給 GitHub Secrets 用）
    with open("cookies.json", "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    print()
    print("=" * 55)
    print("  [完成] 把以下內容複製到 GitHub Secrets")
    print("  Secret 名稱：TWITTER_COOKIES")
    print("=" * 55)
    print()
    print(encoded)
    print()
    print("=" * 55)


if __name__ == "__main__":
    main()

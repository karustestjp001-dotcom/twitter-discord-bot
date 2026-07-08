# Twitter → Discord 自動轉發機器人

監控指定 Twitter/X 帳號，自動將含有圖片或影片的新貼文轉發到 Discord 對應頻道。
連結自動轉換為 `fixupx.com` 格式，可在 Discord 中直接播放。

---

## 部署步驟（照順序做）

### 第一步：在你的電腦上產生 Twitter Cookies

> 需要先安裝 Python：https://www.python.org/downloads/

```bash
# 安裝套件
pip install twikit

# 執行設定腳本
python setup_cookies.py
```

依照提示輸入 Twitter 備用帳號的帳號名稱、Email、密碼。
腳本會產生一段很長的文字（base64 編碼），**複製它**。

---

### 第二步：建立 GitHub Repository

1. 前往 https://github.com → 右上角 **+** → **New repository**
2. Repository name：`twitter-discord-bot`（或任何名字）
3. 選 **Public**（免費無限制）
4. 點 **Create repository**

---

### 第三步：上傳程式碼

```bash
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/你的帳號/twitter-discord-bot.git
git push -u origin main
```

---

### 第四步：設定 GitHub Secrets

前往你的 repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

依序新增以下 Secrets：

| Secret 名稱 | 值 |
|---|---|
| `TWITTER_COOKIES` | 剛才複製的那段 base64 文字 |
| `WEBHOOK_ILLUSTRATORS` | （你的 illustrators Webhook URL）|
| `WEBHOOK_VRC` | （你的 VRC Webhook URL）|
| `WEBHOOK_VIDEO_CREATORS` | （你的 video-creators Webhook URL）|
| `WEBHOOK_3D_MODELERS` | （你的 3d-modelers Webhook URL）|
| `WEBHOOK_GRAPHIC_DESIGN` | （你的 graphic-design Webhook URL）|
| `WEBHOOK_PHOTOGRAPHY` | （你的 photography Webhook URL）|
| `WEBHOOK_AI_CREATORS` | （你的 ai-creators Webhook URL）|

---

### 第五步：手動測試

1. 前往 repo → **Actions** 分頁
2. 左側選 **Twitter Monitor**
3. 右側點 **Run workflow** → **Run workflow**
4. 等待約 1-3 分鐘，查看執行結果

> ⚠️ **第一次執行不會發任何貼文** — 這是正常的！  
> 程式會記錄目前位置，從**第二次執行開始**才會發送新貼文。

---

### 第六步：確認自動排程

目前建議使用 Cloudflare Cron 作為主要排程器，定時呼叫 GitHub `workflow_dispatch`。
GitHub Actions 內建 `schedule` 只保留為低頻備援，避免 GitHub 排程尖峰時漏跑。
Twitter 與 Bilibili 已拆成兩條 workflow，避免其中一邊失敗拖累另一邊。

Cloudflare Worker 設定檔位於 `cloudflare-dispatcher/`：

```bash
cd cloudflare-dispatcher
npm install
npx wrangler login
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put TRIGGER_SECRET
npx wrangler deploy
```

需要建立 GitHub fine-grained personal access token，權限至少包含：

| 權限 | 設定 |
|---|---|
| Repository access | 只選此 repo |
| Actions | Read and write |
| Contents | Read-only |

部署後 Cloudflare Cron 會在每小時第 7 與第 37 分鐘觸發 GitHub workflows。

---

## 注意事項

- **避免 60 天休眠**：GitHub 如果 60 天內 repo 沒有任何活動，會暫停排程。  
  你可以偶爾手動觸發一次 workflow，或在 Actions 頁面重新啟用。

- **Cookies 過期**：Twitter 的 Cookie 通常可使用數週到數個月。  
  如果機器人停止運作，重新執行 `setup_cookies.py` 並更新 `TWITTER_COOKIES` Secret 即可。

- **新增監控帳號**：編輯 `config.py`，加入帳號名稱後 push 到 GitHub 即可。

---

## 檔案說明

| 檔案 | 說明 |
|---|---|
| `config.py` | 監控帳號清單與頻道設定 |
| `main.py` | 主程式邏輯 |
| `setup_cookies.py` | 一次性 Cookie 產生腳本（只在本機執行）|
| `last_seen.json` | 記錄每個帳號最後處理的推文 ID（自動更新）|
| `requirements.txt` | Python 套件需求 |
| `.github/workflows/twitter-monitor.yml` | Twitter GitHub Actions 排程設定 |
| `.github/workflows/bilibili-monitor.yml` | Bilibili GitHub Actions 排程設定 |
| `cloudflare-dispatcher/` | Cloudflare Cron 外部喚醒器 |

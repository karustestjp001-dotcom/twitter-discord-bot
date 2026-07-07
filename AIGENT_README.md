# Twitter-Discord Bot 交接與狀態分析手冊 (For AI Agents)

本文件整理「Twitter/X -> Discord 媒體轉發機器人」目前架構、排程方式、限速處理、已修過的重複發文問題，以及所有重要檔案的絕對路徑。

給下一個 AI 代理時，請優先讀本文件，再讀 `main.py`、`config.py`、`.github/workflows/monitor.yml`、`cloudflare-dispatcher/src/index.ts`。

---

## 專案位置

本地專案根目錄：

```text
C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\
```

GitHub Repo：

```text
https://github.com/karustestjp001-dotcom/twitter-discord-bot
```

---

## 重要檔案

- `C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\main.py`
  - 主控核心程式。
  - 負責 twikit 抓 X/Twitter、Monkeypatch、Cookie 輪替、推文過濾、Discord 發送、更新進度。

- `C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\config.py`
  - Discord 頻道與監控帳號清單。
  - 目前 8 個頻道、91 個 unique accounts。
  - 頻道包含：`illustrators`、`VRC`、`video-creators`、`3d-modelers`、`graphic-design`、`defying-fate`、`photography`、`ai-creators`。

- `C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\.github\workflows\monitor.yml`
  - GitHub Actions workflow。
  - 由 Cloudflare Cron 主要觸發 `workflow_dispatch`。
  - GitHub 原生 `schedule` 僅保留為低頻備援：`23 */6 * * *`。

- `C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\cloudflare-dispatcher\`
  - Cloudflare Worker 外部喚醒器。
  - `wrangler.jsonc` 設定 Cron：`7,37 * * * *`。
  - Worker URL：

```text
https://twitter-discord-bot-dispatcher.asf55bot.workers.dev
```

- `C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\last_seen.json`
  - 記錄每個帳號最後處理過的 tweet ID，防止重複發文。

- `C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\user_ids.json`
  - X/Twitter username -> user id 快取，避免每次都查 screen name。

- `C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\cookies.json`
  - 本機 Cookie 池檔案。
  - GitHub Actions 端由 Secret `TWITTER_COOKIES` 還原。

---

## 目前排程架構

目前不是只靠 GitHub Actions `schedule`。GitHub schedule 曾經長時間漏跑，所以已改成：

```text
Cloudflare Cron
  -> 呼叫 GitHub API workflow_dispatch
  -> GitHub Actions 跑 main.py
  -> 發 Discord
  -> 更新 last_seen.json / user_ids.json 並 push 回 repo
```

Cloudflare Cron：

```text
7,37 * * * *
```

也就是每小時第 7 分與第 37 分觸發一次。

GitHub Actions 備援 schedule：

```text
23 */6 * * *
```

這只是低頻備援，不是主要排程。

---

## Cloudflare Worker 狀態

Worker 專案：

```text
C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\cloudflare-dispatcher\
```

主要檔案：

```text
cloudflare-dispatcher\src\index.ts
cloudflare-dispatcher\wrangler.jsonc
cloudflare-dispatcher\README.md
```

Cloudflare Secrets：

- `GITHUB_TOKEN`
  - 用來呼叫 GitHub workflow_dispatch。
  - 曾遇過 pipe 寫入 secret 帶 newline 導致 GitHub `401 Bad credentials`，後來已用無換行方式重寫成功。

- `TRIGGER_SECRET`
  - 手動呼叫 `/dispatch` 的保護密碼。
  - 本機備份在：

```text
C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\cloudflare-dispatcher\.trigger_secret.local.txt
```

此檔已加入 `.gitignore`，不要 commit。

健康檢查：

```powershell
curl.exe --http1.1 -4 -i https://twitter-discord-bot-dispatcher.asf55bot.workers.dev/health
```

手動觸發：

```powershell
$secret = Get-Content -LiteralPath '.trigger_secret.local.txt' -Raw
curl.exe --http1.1 -4 -i -X POST -H "Authorization: Bearer $secret" https://twitter-discord-bot-dispatcher.asf55bot.workers.dev/dispatch
```

成功時會回：

```json
{"ok":true,"status":204,"message":"workflow dispatched"}
```

---

## GitHub Secrets

主要 Secrets：

- `TWITTER_COOKIES`
- `WEBHOOK_ILLUSTRATORS`
- `WEBHOOK_VRC`
- `WEBHOOK_VIDEO_CREATORS`
- `WEBHOOK_3D_MODELERS`
- `WEBHOOK_GRAPHIC_DESIGN`
- `WEBHOOK_DEFYING_FATE`
- `WEBHOOK_PHOTOGRAPHY`
- `WEBHOOK_AI_CREATORS`

注意：Webhook URL 不應寫入 repo，請只放 GitHub Secrets。

---

## 推文過濾規則

`main.py` 的預設規則：

- 跳過轉推。
- 必須有媒體。
- `media_type = "any"` 時，圖片或影片都會轉發。
- `media_type = "video"` 時，只轉發含影片。
- `media_type = "photo"` 時，只轉發含圖片。

`config.py` 的帳號可以是字串：

```python
"V_DefyingFate"
```

也可以是 dict：

```python
{"username": "iiiichimarU_03", "media_type": "video"}
```

---

## X/Twitter 限速與 Cookie 輪替

已知 X/Twitter 不只會回 `429`，也可能用 `401`、`403` 作為軟封鎖或登入失效訊號。

`main.py` 已將以下錯誤視為阻擋訊號：

- `429`
- `401`
- `403`
- `Rate limit`
- `authenticate`
- `Forbidden`

遇到後會切換 Cookie 池中的下一個帳號。

Cookie 池目前設計為多帳號輪替；本機 `cookies.json` 和 GitHub Secret `TWITTER_COOKIES` 要保持同步。

---

## 已修過的重要問題

### 1. GitHub Actions schedule 漏跑

原本只用 GitHub schedule，每 30 分鐘一次，但 GitHub 可能延遲甚至跳過排程。

修法：

- 新增 Cloudflare Worker 外部喚醒器。
- Cloudflare Cron 每小時第 7、37 分觸發 GitHub workflow_dispatch。
- GitHub schedule 改成每 6 小時低頻備援。

### 2. 重複發文

曾出現同一篇 `gracile_jp/status/2073096710830907689` 重複發送。

真正原因：

- 前一個 run 還在跑時，下一個 run 被 Cloudflare 觸發並排隊。
- 排隊 run 使用排隊當下的舊 commit / 舊 `last_seen.json`。
- 它開始跑時沒有先拉最新 state，所以再次發同一篇。
- 發完後 `git push` 被遠端 state commit 擋住，導致進度沒保存。

修法已在 `.github/workflows/monitor.yml`：

```yaml
- name: Sync latest state
  run: git pull --ff-only origin main
```

以及 save progress：

```bash
git push || (git pull --rebase origin main && git push)
```

另有：

```yaml
concurrency:
  group: twitter-monitor
  cancel-in-progress: false
```

用來避免同時執行造成更嚴重的狀態競爭。

### 3. Base64 Secret 貼上損毀

`TWITTER_COOKIES` 若手動複製貼上可能帶入 Windows 換行或空白，導致 GitHub Actions 還原 `cookies.json` 失敗。

建議用 PowerShell / GitHub CLI 直接寫 secret，不要手動貼很長的 base64。

---

## 最近新增過的帳號/頻道

- `EOR79`
  - 加到 `illustrators`
  - 加到 `graphic-design`

- `V_DefyingFate`
  - 新增獨立頻道 `defying-fate`
  - Webhook Secret：`WEBHOOK_DEFYING_FATE`
  - 規則：含圖片或影片都轉發。

- `vrcbiyaareal`
  - 加到 VRC。

- `Blue_HIBIKI`
  - 加到 VRC。

---

## 常用指令

查看最近 run：

```powershell
gh run list --repo karustestjp001-dotcom/twitter-discord-bot --workflow "Twitter Monitor" --limit 10
```

手動觸發 GitHub Actions：

```powershell
gh workflow run monitor.yml --repo karustestjp001-dotcom/twitter-discord-bot -f source=manual
```

部署 Cloudflare Worker：

```powershell
cd C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\cloudflare-dispatcher
npx.cmd wrangler deploy
```

檢查 Cloudflare Worker：

```powershell
cd C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\cloudflare-dispatcher
npm run check
```

Python 語法檢查：

```powershell
python -m py_compile main.py config.py
```

---

## 給下一個 AI 的接手提醒

1. 先讀本文件。
2. 再讀 `main.py`、`config.py`、`.github/workflows/monitor.yml`、`cloudflare-dispatcher/src/index.ts`。
3. 不要把 Discord webhook 或 token 寫進 repo。
4. 修改帳號清單後，通常只需要改 `config.py`。
5. 新增頻道時，需要同時：
   - 在 `config.py` 新增 channel。
   - 在 `.github/workflows/monitor.yml` 的 `Run monitor env` 加入對應 Secret。
   - 用 `gh secret set` 設定 Webhook。
6. 如果發現重複發文，優先查：
   - GitHub run 是否重疊或排隊。
   - `last_seen.json` 是否成功 push。
   - `Save progress` 是否有 `rejected/fetch first`。
7. 如果長時間沒發文，優先查：
   - Cloudflare Worker Cron 是否仍部署。
   - GitHub workflow_dispatch 是否有被觸發。
   - X/Twitter 是否大量 `429/401/403`。


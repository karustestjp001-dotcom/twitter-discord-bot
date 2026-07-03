# Twitter-Discord Bot 交接與狀態分析手冊 (For AI Agents)

本文件整理了「Twitter → Discord 媒體轉發機器人」的系統架構、遇到的問題、已完成的修復方案，以及所有相關檔案的絕對路徑，以便其他 AI 代理 (AIGent) 能夠以最快速度接手並理解目前狀態。

---

## 📂 檔案與路徑對照表 (File Paths)

所有本地專案檔案均位於：
`C:\Users\asf55\.gemini\antigravity\scratch\twitter-discord-bot\`

* 🖥️ **主控核心程式**：[main.py](file:///C:/Users/asf55/.gemini/antigravity/scratch/twitter-discord-bot/main.py)  
  *包含 Twitter API 串接、Monkeypatch 核心、帳號輪替池、推文過濾與發送邏輯。*
* ⚙️ **頻道與監控清單**：[config.py](file:///C:/Users/asf55/.gemini/antigravity/scratch/twitter-discord-bot/config.py)  
  *定義 7 個 Discord Webhooks、86 位創作者的名單以及個別的過濾條件。*
* ⏰ **工作流配置**：[.github/workflows/monitor.yml](file:///C:/Users/asf55/.gemini/antigravity/scratch/twitter-discord-bot/.github/workflows/monitor.yml)  
  *排程設定（目前為 30 分鐘執行一次）、GitHub Secrets 還原 Cookie 以及進度提交邏輯。*
* 📌 **讀取進度快取**：[last_seen.json](file:///C:/Users/asf55/.gemini/antigravity/scratch/twitter-discord-bot/last_seen.json)  
  *記錄每位創作者已發送的最新推文 ID（防重複發送）。*
* 🔑 **使用者 ID 快取**：[user_ids.json](file:///C:/Users/asf55/.gemini/antigravity/scratch/twitter-discord-bot/user_ids.json)  
  *記錄 Twitter 使用者名稱對應的內部 ID，避免每次執行都需打 API 查詢。*

---

## 🛠️ 核心問題與解決方案分析 (Issues & Fixes)

### 1. ⚠️ GitHub Actions 排程器延遲與漏跑問題
* **現象**：設定每小時執行一次，但常出現長達 8 小時完全沒有被觸發的狀況。
* **原因**：GitHub 對於免費/公開專案的排程（`schedule`）優先級較低，高峰期極易延遲或跳過。
* **修復**：將排程頻率提高至 **每 30 分鐘執行一次** (`cron: '*/30 * * * *'`)，縮短漏跑產生的空窗期。

### 2. ⚠️ X 平台（Twitter）的多樣化限制與阻擋
* **現象**：僅用單一小號掃描 80+ 個創作者時，容易中斷並報錯。
* **原因**：X 平台對頻繁存取除回傳 `429` (Rate limit exceeded) 外，還會故意回傳 `401` (Could not authenticate you) 或 `403` (Forbidden) 進行軟鎖定。
* **修復**：
  1. **三小號 Cookie 輪替池**：在 `cookies.json` 中整合 3 組小號（`@0xRenNaiMaid`、`@SuisaJP`、`@OOasf89614`）。
  2. **全面容錯輪替**：在 `main.py` 的異常處理中，將 `401`, `403`, `429` 錯誤全部視為阻擋信號。一旦觸發，立即登出並切換至下一個小號 Cookie，從斷點繼續執行。

### 3. ⚠️ GitHub Secrets 還原時的 Base64 格式損毀
* **現象**：手動複製三帳號 Cookie 的 Base64 字串貼入 Secrets 後，Actions 還原時報 `base64: invalid input` 錯誤。
* **原因**：複製貼上引入了 Windows 換行符號 `\r\n` 與額外空白，損毀了 Base64 的編碼結構。
* **修復**：改用 PowerShell 讀取本地 `cookies.json` 做二進位轉換，並使用 GitHub CLI 進行程式化寫入，徹底解決換行符號問題。

### 4. ⚠️ 頻道與帳號的細緻媒體過濾需求
* **現象**：特定的創作者需要實現特殊過濾（如 `@iiiichimarU_03` 僅在發送影片時才轉發）。
* **修復**：
  1. 擴充 `config.py` 中的 `accounts` 格式，除支援一般字串外，亦支援字典格式如 `{"username": "iiiichimarU_03", "media_type": "video"}`。
  2. 重構 `main.py` 的發送迴圈，每個頻道對應的創作者都會單獨匹配過濾條件（如 `video` 或 `photo`），不符者直接過濾，且不影響其他頻道 or 創作者的正常發送。

---

## 📈 目前驗證狀態

* 最新一次手動觸發執行 ([Run 28640429320](https://github.com/karustestjp001-dotcom/twitter-discord-bot/actions/runs/28640429320)) **執行成功 (Success)**。
* 成功測試將 `@rako_bear_` (Photography頻道) 及 `@p1ct0a1` (AI 創作頻道) 的貼文發送至 Discord。
* 輪替機制與 30 分鐘自動排程皆已上線，運作完全正常。

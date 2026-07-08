# Cloudflare Dispatcher

這個 Worker 只負責定時呼叫 GitHub API，觸發 `Twitter Monitor` 與 `Bilibili Monitor` workflows。

## 需要的 GitHub Token

建立 Fine-grained personal access token：

- Repository access：只選 `karustestjp001-dotcom/twitter-discord-bot`
- Permissions：
  - Actions：Read and write
  - Contents：Read-only

## 部署

```bash
cd cloudflare-dispatcher
npm install
npx wrangler login
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put TRIGGER_SECRET
npx wrangler deploy
```

`GITHUB_TOKEN` 貼上 GitHub fine-grained token。

`TRIGGER_SECRET` 可自行輸入一段長隨機字串，用於手動測試 `/dispatch`。

如果要在觸發 GitHub 失敗時發 Discord 警告，可以額外設定：

```bash
npx wrangler secret put DISCORD_HEALTH_WEBHOOK
```

## 測試

部署後可以先確認健康檢查：

```bash
curl https://twitter-discord-bot-dispatcher.<你的子網域>.workers.dev/health
```

手動觸發：

```bash
curl -X POST "https://twitter-discord-bot-dispatcher.<你的子網域>.workers.dev/dispatch?token=<TRIGGER_SECRET>"
```

Cron 會在每小時第 7 與第 37 分鐘觸發，並同時 dispatch `twitter-monitor.yml` 與 `bilibili-monitor.yml`。Cron 使用 UTC 計算小時，但分鐘不會因時區改變。

# Cloudflare Worker 定時觸發設定（約 10 分鐘）

> 1.10.2 起 GitHub 排程已能在美東 17:00 發布（提前做稿、準點更新），Worker 變成「選用」的第二重保險，不設也可以。

目的：每天美東 17:00（收盤後一小時）準時叫 GitHub 發布，不再受 GitHub 排程延遲影響。

## 1. 建立 GitHub 權杖（只給這個 repo）
GitHub 右上頭像 → Settings → Developer settings → Personal access tokens → **Fine-grained tokens → Generate new token**
- Repository access：**Only select repositories** → 選 TechStockMarket-daily
- Permissions → Repository permissions → **Contents：Read and write**（這是觸發 repository_dispatch 需要的權限）
- 期限自訂（到期前要換新，建議 1 年）→ Generate → 複製權杖（只會顯示一次，**不要貼到聊天裡**）

## 2. 建立 Worker
Cloudflare 後台 → Workers & Pages → Create → **Create Worker** → 名稱 `techstockmarket-trigger` → Deploy
→ Edit code → 把 `worker/worker.js` 全部內容貼上取代 → Deploy。

## 3. 存權杖
Worker → Settings → Variables and Secrets → Add → 類型 **Secret**，名稱 `GITHUB_TOKEN`，值貼剛才的權杖 → Deploy。
（要測試用：另加變數 `TEST_KEY`，值自訂一串；測完可刪。）

## 4. 加排程
Worker → Settings → Triggers → **Add Cron Trigger**，加兩條：
- `0 21 * * *`
- `0 22 * * *`
（一條對應夏令、一條對應冬令；Worker 會自己判斷美東是不是 17 點，不是就不做事。）

## 5. 測試
瀏覽器開 `https://<你的worker網址>/?run=1&key=<TEST_KEY>`：顯示 `OK dispatched` 後，到 GitHub → Actions 會看到新的 Publish 在跑。
（要先確認那天是否已發過；已發過會被「已發布」檢查跳過，不會重複。）

## 疑難
- 顯示 HTTP 401/403/404：權杖權限或 repo 名稱不對（REPO 變數預設 wave2gate/TechStockMarket-daily）。
- Worker 失靈時，GitHub 的備援排程（每天 UTC 23:17）仍會發布，只是可能晚一些。

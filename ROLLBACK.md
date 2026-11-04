# 回溯（萬一搞亂了）

## 方法 A：在 GitHub 網頁上還原單一檔案（最簡單）
1. repo → 點該檔案 → 右上 **History**。
2. 找到想回去的那次提交 → 點 `<>`（Browse files）→ 回到那個版本的檔案 → 右上 **⋯ → Raw/Download** 存下來。
3. 回到 repo 原位置 → **Add file → Upload files** 覆蓋上傳（或 ✏️ 編輯貼上舊內容）→ Commit。

## 方法 B：整套退回 v1.5.1
1. 解壓你備份的 `TechStockMarket-daily_v1.5.1_last-good.zip`。
2. 把裡面 `scripts/` 的檔案與 `.github/workflows/` 兩個 yml 重新上傳覆蓋。
3. 新增的檔案（`market.py numcheck.py frame.py guard.py episode.py`）留著不會影響舊程式，可不刪。
4. **不要**上傳／覆蓋 `feed.xml`、`episodes_queue.json`（那是線上資料）。
5. 停掉 Cloudflare Worker：Workers → 你的 Worker → Settings → Triggers → 刪除 Cron（或整個 Worker 刪掉）。
   舊版 publish.yml 的排程是 `0 1 * * *`，還原後會恢復舊的發布時間。

## 方法 C：用 GitHub 標籤
上傳 v1.6.0 並確認一切正常後：repo 右側 **Releases → Create a new release**，Tag 填 `v1.6.0`，發布。
之後任何時間可從 Releases 下載該版本原始碼 zip。建議在上傳 v1.6.0 **之前**，也替現在的 v1.5.1 建一個 `v1.5.1` Release。

## 只想關掉某個新功能（不用回溯）
在 publish.yml 的 env 區加一行：
- `TWO_STAGE: "0"` → 不用兩階段，改一次寫完
- `AUDIT: "0"` → 不用 AI 審稿（仍會核對數字）
- `EPISODE_MODE: "daily"` → 強制當日更（臨時補發用，用完要拿掉）

## 手動補發／重做某一集
Actions → Publish Podcast Episodes → Run workflow（會強制重做該美東交易日的集數並原地更新）。

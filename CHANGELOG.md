# CHANGELOG — 美股科技收盤簡報（TechStockMarket-daily）

版本規則：整個 repo 的版本號以本檔最上方一段為準（`主版本.次版本.修補版本`）。
每次改版：① 只有「有改動的檔案」才需要升 `__version__`，沒動的檔案不必重傳
② 在本檔最上方新增一段 ③ 一起 commit。
Actions 日誌第一行會印出「版本：main x | analyzer x | publish x」，用來確認跑的是新程式碼；
出現 `?` 代表那個檔案還是舊版（沒有 `__version__`）。
各檔案目前版本：main 1.3.0 ／ publish 1.2.1（未改動）／ analyzer 1.3.1 ／ trial 1.3.0。

---

## [1.3.1] — 2026-10-28　提示詞加強（試跑後修正）
### 修正
- 試跑發現：Groq 出現買賣建議（「逢低加碼」「建議觀望」）與大陸／港式用詞（美聯儲、加息）；
  Cloudflare 只有 847 字，且照抄「對投資者的影響分析是」。
- `analyzer.py` 的提示詞新增 3 條規則：禁止買賣建議、每則至少兩句且不照抄套話、台灣用語表與數字念法。
  三家提供商共用同一份提示詞。

---

## [1.3.0] — 2026-10-28　改名 + Cloudflare Workers AI + 不發布試跑
### 新增
- **Cloudflare Workers AI** 加入提供商鏈（`analyzer.py`）：預設順序 Gemini → Groq → Cloudflare → OpenRouter → DeepSeek。
  走 OpenAI 相容端點，模型 `@cf/meta/llama-3.3-70b-instruct-fp8-fast`（備用 `llama-3.1-8b-instruct`），
  需 Secrets：`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`；可用 `CLOUDFLARE_MODEL` 指定模型。
- **不發布試跑**：`scripts/trial.py` + `.github/workflows/trial.yml`（手動 Run workflow）。只測 AI，
  不做 TTS、不上傳 R2、不改 feed、不 commit；結果與全文寫在該次 Run 的 Summary 頁。
### 變更
- **節目名改為「美股科技收盤簡報」**：`main.py` 預設名稱、新集標題（`{日期} 美股科技收盤簡報`）、
  開場白、`feed.xml` 的頻道 `<title>` 與 `<description>`。舊集標題不動。
  （`POD_TITLE` 不在 Secrets 裡，所以直接改程式預設值；日後設 `POD_TITLE` 可覆蓋。）
- `publish.yml` 增加 Cloudflare 兩個 Secrets 的傳入。

---

## [1.2.1] — 2026-10-19　說明欄全文試驗
### 新增
- **說明欄放全文，上限 4,000 字符（試驗值）**：`description` 改為「導語 → 全文連結 → 其餘內文 →
  AI 聲明」。標準開場白（歡迎收聽…）不放進說明欄，讓預覽區直接看到內容。
  超過上限時在句號處截斷並加上「（後文請見全文連結）」，不再硬切 300 字。
  上限可不改程式、在 workflow 的 `env:` 加 `DESC_MAX_CHARS: 3000` 之類調整。
- **R2 全文頁**：每集存一份 HTML（手機可讀、附音頻播放器與新聞原文連結）和一份 Markdown（方便日後貼到
  Substack），路徑 `t/zh-TW/YYYYMMDD.html` / `.md`。上傳失敗只警告，不影響集數發布，說明欄就不附連結。
- **`<content:encoded>`**：同樣內容的 HTML 版（含可點連結），與純文字 `<description>` 並存，
  用來觀察 Spotify 實際讀哪一個。缺少 `xmlns:content` 的 feed 會自動補上。
- 日誌多印一行：說明欄用了幾字符、有沒有被截斷、全文共幾字。
### 變更
- `episodes_queue.json` 歷史紀錄仍只留 300 字摘要，不存完整說明欄與 HTML，避免 repo 檔案越來越大。
- 升版規則改為「只有改動的檔案才升版」（見上方）。
### 觀察項目（試驗期 3–5 天，記在下方「試驗紀錄」）
1. Spotify 是否完整顯示、是否被折疊。 2. 連結能不能點。
3. 說明欄接近上限時，截斷後的樣子。 4. 若 Spotify 更早截斷就調小 `DESC_MAX_CHARS`；完整顯示就試著放寬。
### 已知取捨
- feed.xml 會變大（每集多約 5–9 KB，估算全年約 2–3 MB）。試驗期無影響，之後可改成只保留最近 N 集的全文。
- 舊集數的說明欄不回填（完整講稿當時沒有保存，無從補起）。

## [1.2.0] — 2026-10-16
### 修正
- **重複 guid 的根源**：`publish.py` 過去每次都直接插入新集數，同一天重跑就產生重複 item
  （例如 10/8 有 3 筆、10/7 有 2 筆）。現在同 guid 會「原地取代」，其餘重複自動移除。
- **非法 XML**：標題/描述/網址一律 XML 跳脫（10/9 那集的 `AT&T` 讓整份 feed 無法解析）。
- **Groq 模型**：v1.1.0 的 `llama-3.3-70b-versatile` 已於 2026-08-16 被 Groq 關閉。
  改為執行時查詢 `/models`，偏好 `openai/gpt-oss-120b` → `gpt-oss-20b` → `qwen/qwen3.8-27b`。
- feed.xml 不再每次多留一堆空白行。
### 新增
- 第四個提供商 **OpenRouter（`:free` 模型）**，需要 Secret `OPENROUTER_API_KEY`。
- 預設順序 Gemini → Groq → OpenRouter → DeepSeek（DeepSeek 為付費，放最後）；
  可用環境變數 `PROVIDER_ORDER` 調整，不必改程式。
- **當日防重複**：feed 已有今天的集數就跳過；手動 Run workflow 或 `FORCE_REBUILD=1` 才強制重做。
- DeepSeek 也改為查詢可用模型（`deepseek-chat` 舊名據報將退役）。
- 啟動時印出版本橫幅與各提供商的 Key 設定狀態。
- 本檔 CHANGELOG.md。

## [1.1.0] — 2026-10-16（已部署）
- `analyzer.py`：Gemini 改為查詢可用模型（`gemini-2.5-flash` / `2.5-flash-lite` 對此 key 回 404）；
  單一模型逾時/429/5xx 改為重試與換模型，不再整個中斷；金鑰改放 header，避免被印進公開日誌；
  `maxOutputTokens` 提高到 8192；失敗時印出 HTTP 狀態與回應內文。
- `main.py`：上傳 R2 前依 guid 去重、修正 `&`、驗證 XML；開啟 INFO 日誌。

## [1.0.0] — 基準版（2026-10-16 以前，當時未留紀錄）
- 流程：fetcher → analyzer（Gemini → Groq → DeepSeek）→ tts（Edge TTS）→ r2 → publish。
- 已知問題（後續版本處理）：Gemini 模型名稱 404、Groq 模型已下架（400）、feed 重複 guid、
  feed 含未跳脫的 `&`。

---

## 試驗紀錄（說明欄 4,000 字符）
| 日期 | 集數 | 說明欄字符數 | Spotify 完整顯示？ | 連結可點？ | 備註 |
|---|---|---|---|---|---|
| | | | | | |

## 待辦 / 未解決（每次改版更新）
- [ ] `fetcher.py`：Yahoo Finance RSS 404、Bloomberg NEF 403、WSJ Markets 0 則（來源網址需更換）。
- [ ] 確認 10/5、10/6、10/12、10/13 為何沒有集數。
- [ ] 檢視 `.github/workflows/publish.yml`：加入 `concurrency`、`OPENROUTER_API_KEY`；
      repo 內 `scripts/publish.yml` 可能是多餘的副本（GitHub 只執行 `.github/workflows/` 裡的）。
- [ ] README.md 目前被 CHANGELOG 內容覆蓋，可到 History 還原，再另建 CHANGELOG.md。
- [ ] 後續：UTC 22:30 發布點、更名、英文節目、AI 週輪替、Cloudflare 提供商、不發布的 API 試跑。

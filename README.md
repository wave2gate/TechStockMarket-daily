# CHANGELOG — 美股科技晨報（TechStockMarket-daily）

版本規則：全 repo 共用一個版本號 `主版本.次版本.修補版本`。
每次改版：① 改 `scripts/main.py`、`analyzer.py`、`publish.py` 裡的 `__version__`（三個要一致）
② 在本檔最上方新增一段 ③ 一起 commit。
Actions 日誌第一行會印出「版本：main x | analyzer x | publish x」，用來確認跑的是新程式碼；
出現 `?` 代表那個檔案還是舊版（沒有 `__version__`）。

---

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

## 待辦 / 未解決（每次改版更新）
- [ ] `fetcher.py`：Yahoo Finance RSS 404、Bloomberg NEF 403、WSJ Markets 0 則（來源網址需更換）。
- [ ] 確認 10/12、10/13 為何沒有集數（見排查步驟）。
- [ ] 確認 Spotify for Creators 為何停在 10/4。
- [ ] 檢視 `.github/workflows/publish.yml`：`env:` 是否有四個 API Key、是否需要 `concurrency`、
      「無變更可 commit」時是否會讓 job 變紅。
- [ ] repo 內 `scripts/publish.yml` 可能是多餘的副本（GitHub 只執行 `.github/workflows/` 裡的）。

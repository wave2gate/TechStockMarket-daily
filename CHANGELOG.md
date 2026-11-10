# CHANGELOG — 美股科技收盤簡報（TechStockMarket-daily）

版本規則：整個 repo 的版本號以本檔最上方一段為準（`主版本.次版本.修補版本`）。
每次改版：① 只有「有改動的檔案」才需要升 `__version__`，沒動的檔案不必重傳
② 在本檔最上方新增一段 ③ 一起 commit。
Actions 日誌第一行會印出「版本：main x | analyzer x | publish x」，用來確認跑的是新程式碼；
出現 `?` 代表那個檔案還是舊版（沒有 `__version__`）。
各檔案目前版本：main／episode／pipeline／topics／trial／version／updates 為 1.10.1、watchlist／prices 為 1.10.0、fetcher 為 1.9.1、numcheck 為 1.7.1、frame 為 1.8.2、tts 為 1.7.4（其餘 1.8.x 以各檔案內版本為準）、analyzer 為 1.7.0、其餘 1.6.x（publish.py 1.2.1、r2.py、tts.py 未改動）。

---

## [1.10.1] — 2026-11-10　依試跑 #19（v1.10.0，mp3 8:40）：修選稿規則，不加新功能
- 貴金屬單元誤收大盤新聞（最嚴重）：
  - topics：貴金屬／礦產細項改為「標題」必須提到金屬或礦業公司才算；Kitco 的大盤文章不再因來源提示被歸進來（Mining.com、Northern Miner 為礦業專門媒體不受限；新增 Mining.com 預設細項 M2）；標題含 theft／stolen／police（如銅線竊案）不算礦產。
  - pipeline：統稿提示不再要求「每一則筆記都要提到」，改為「每則筆記只能寫在它所屬主題的段落，不得搬到別段；明顯與主題無關的可略過」，防止大盤剩下的筆記被塞進最後一段。
- 選稿：
  - 素材每則加〔細項〕標籤，提示要求各細項盡量都有 1 則入選、離題素材一律略過、寧可少於名額。
  - 同一事件（標題至少共有 2 個有意義字詞）在送給 AI 前與筆記產出後各限制最多 2 則。
- numcheck 1.7.1：`$130m`、`$7bn`、`$2k` 這類小寫縮寫金額正確換成「130 million 美元」（原本變成「130 美元m」，導致 Mavria 那則被數字關卡誤刪）。
- fetcher 1.9.1：過濾壞掉的範本標題（含大括號，例如 `{PAGE_DESCRIPTION}`）；新增 `source_health()`，試跑 Summary 增加「來源可用性」（主網址失敗由備援補上／完全沒內容／正常但時間窗內無新文章）。
- episode：英文殘留置換新增 percent→%、miles→英里、單獨月份（April→4月，後面接數字的日期不動）、agentic／framework／metadata／offensive／security。
- 沒有改動：價格段落、更新紀錄機制、播報順序、各組 AI 分配、稿件長度規則。
- 測試：test_v1101.py（分類、數字、事件上限、英文置換、壞標題過濾、提示詞、各檔版本與 EXPECT 一致）與 test_v16／v18／v110 全數通過。
- 回滾：還原 topics、pipeline、episode、fetcher、numcheck、main、trial、version、updates 到 1.10.0 即可（見 ROLLBACK.md）。

## [1.10.0] — 2026-11-07　依試跑 #17（v1.9.0，mp3 7:23）：修問題＋價格動向進稿＋更新紀錄
- 修問題（原規劃的 1.9.1 併入）：
  - pipeline：筆記階段拒收「只有幾個中文字、沒有名稱或數字」的事實（例如把 Google News 主題標籤當成新聞），防止它後來被統稿拼出混合句；寫稿提示加上「背景或影響若只是重述事實就只講一次」。
  - topics：收緊關鍵詞——「gold」只認 gold price／gold miners 等明確用法（修正 Nokia "optical gold rush" 被分到貴金屬）；「launch」改為 rocket launch／launch vehicle；新增 quantum 歸 AI 晶片與算力；Duke Energy、natural gas generation、spending plan 歸發電與公用事業（修正被分到油氣）。
- prices：價格動向寫進日更集數的稿子（程式算、固定句型、不經 AI、中立、不含建議）：各分類代表 ETF 近 21 個交易日漲跌＋創 21 日新高／新低的 ETF 與觀察列表個股；完整表格在試跑摘要。先用 SPY 試連，連不上或最新日期不等於交易日就整段略過（休市日、週末集數不加）。環境變數 PRICES=0 可關閉。
- 新增 updates.py：給讀者看的版本更新紀錄，R2 文稿頁（HTML 與 MD）底部累積顯示；發版後 3 天內的日更集數口播最新一句。
- watchlist：新增 LEAD（口播用的代表 ETF）。
- trial：顯示價格動向狀態；版本警告改比對 EXPECT（含 main、episode）。
- 不變：fetcher 1.9.0、tts 1.7.4。

## [1.9.0] — 2026-11-07　依試跑 #16（v1.8.4，mp3 7:51）擴充
- 順序：電信移到電力前面；新增「貴金屬與關鍵礦產」放最後（細項：貴金屬、銅與關鍵礦產、鈾與核燃料）。總則數維持 34（大盤 5、AI 6、太空 3、資安 4、電信 5、電力 5、油氣 3、貴金屬礦產 3），時長目標約 8 分鐘。
- fetcher：新增來源 Mining.com、Kitco、Northern Miner、The Record、Microsoft Security（網址未驗證，看試跑「來源診斷」）；Google News 主題備援新增貴金屬、銅與關鍵礦產、鈾、重大駭客與加密貨幣盜竊、上市公司資安事件。
- topics：新增 M1–M3 關鍵詞；資安關鍵詞加入加密貨幣盜竊與重大資料外洩（不特別追北韓）；觀察列表改由 watchlist.py 提供。
- 新增 watchlist.py（觀察列表起始清單，含定投大盤 ETF、大盤權重股、各分類 ETF 與個股；你之後貼清單我再幫你整理）。
- 新增 prices.py：滾動 21 個交易日收盤高低點與各分類 ETF 近 21 日漲跌；**只在試跑顯示，未進節目稿**；資料來源（Yahoo 圖表介面→Stooq）尚未在雲端驗證。
- tts：估算係數再校正為 0.223／0.088（#16 實測 7:51）；trial 的「約幾分鐘」改用同一公式。

## [1.8.4] — 2026-11-06　依試跑 #15（v1.8.3，mp3 6:27）調整
- 新增 `version.py`：整個專案只在這裡改發布版本；R2 文稿頁與說明欄的標題變成「本集新聞統計（v1.8.4）」。
- trial：摘要最上面顯示發布版本，並對照 `version.py` 的 EXPECT，檔案漏傳或傳到舊版會出現警告。
- pipeline：各組挑選則數增加 macro 5→6、ai 6→7、power 5→6、oil 2→3、telecom 4→5（共 34 則，只增加真實新聞，不灌水），目標約 7:30。
- tts：估算係數微調為中文 0.215 秒／字、英數 0.085 秒／字（以 #15 實測 6:27 校正）。

## [1.8.3] — 2026-11-06　依試跑 #13（mp3 7:03）小修
- tts：時長估算改為「中文字 0.21 秒＋英數字 0.083 秒」（以實測 7:03 校正；舊公式把英文名多的稿子高估）。
- pipeline：每組挑新聞時，先保證每個細項（例如機櫃散熱 S3）至少 2 則、不同來源優先，再輪流補滿；資安組 pick 3→4。
- topics：Data Center Knowledge 來源提示 S3→B4（它多是電力／選址新聞，不全是散熱）。
- episode：漏譯的常見英文名詞（lawmakers、investors 等）後處理換成中文；稿中殘留的小寫英文單字列在試跑摘要供觀察。
- trial：版本號改為直接讀檔，不再因缺 boto3 顯示「main 載入失敗」。

## [1.8.2] — 2026-11-06　依第一次完整試跑（#12）修正
試跑結果：7.3 分鐘、AI 稿 1599 字，防幻覺關卡只刪 1 句（且那句其實有依據），303 則新聞抓取正常，三家 AI 分工正常。發現並修正：
- **統計表低估涵蓋數**：筆記是英文、稿子是中文，原本靠「字詞比對」找不到對應（例如油氣 3 則都有講卻顯示 0）。
  改法：統稿時每則筆記有編號 N1…Nk，AI 在句號前加【N編號】；程式以標記為準（比對在審稿刪句之後，被刪的句子標記一起消失，所以統計準確），標記在朗讀前一律移除；AI 漏標時才退回字詞比對。
- **分類誤判**：選舉相關股災新聞被分到「數據中心供電」、Tesla／SpaceX 市值新聞被分到太空。調整關鍵詞：移除泛用的 data center；新增市值／股災詞（market cap、selloff、rout…）與政策詞（moratorium、midterm、Democrat、lawmakers…）；電信新增 mobile network、Deutsche Telekom、Vodafone。
- 新增「其他（X）」：沒有任何關鍵詞也沒有來源預設的新聞（例如電動車消費新聞）不再進任何筆記組；Electrek 取消預設細項。
- **標題含 HTML**（FierceWireless 的 `<a href=…`）：標題一律去除標籤並還原字元。
- **稿子念出標題式主題名**（「首先來看大盤宏觀財報政策的最新動態」）：統稿用較口語的主題名，並要求自然轉場。
- **署名太長**：同一個模型負責的主題併成一句；Qwen 模型不再被寫成「Groq 平台上的開源模型」。
- 筆記規則新增：不要抄錄訂閱、廣告、作者介紹等無關文字（Canary Media 的電子報導語曾被抄進背景欄）。
- 已知小問題：AI 偶爾留下未翻譯的英文普通名詞（例如 lawmakers），先觀察；審稿員（Groq 備選模型）偶有誤刪有依據的句子，屬可接受的保守。
- 更動檔案：`fetcher.py` `topics.py` `pipeline.py` `episode.py` `frame.py` `trial.py` `ARCHITECTURE.md` `CHANGELOG.md`。

---

## [1.8.1] — 2026-11-06　新增「資訊安全與數據中心基礎設施」、架構文件
- **新分類區塊**（3 個細項）：S1 網路與通訊安全（駭客、勒索、漏洞、零信任）、S2 軟硬體與供應鏈安全、S3 數據中心機櫃、散熱與樓控／工控安全（含「駭客攻擊空調水冷導致熱當機」這類事件）。`B4` 改為只管「數據中心供電」，散熱相關關鍵詞移到 S3。
- **新來源**（未驗證）：Krebs on Security、BleepingComputer、The Hacker News、SecurityWeek、Dark Reading、CISA Advisories、Data Center Knowledge；Google News 4 組（資安事件、資安公司、機櫃與散熱、數據中心樓控與工控攻擊）。
- 筆記改為七組（新增資安組，Gemini 負責，失敗時 Groq 補做）；總筆記數約 28 則。統稿順序：大盤 → AI 與半導體 → 太空與下一代通訊 → 資安與數據中心基礎設施 → 電力 → 油氣 → 電信。
- `WATCHLIST` 先放 Palo Alto Networks、Cloudflare、Vertiv（只影響選材優先順序，稿子語氣不變、不構成買賣建議）。
- 試跑 Summary 第一行新增「各模組版本」，上傳後先看這行確認沒漏傳。
- 新增 `ARCHITECTURE.md`：流程圖、各檔案職責、版本規則、給 AI 的接手說明。
- 模型偏好確認：Gemini 首選 `gemini-flash-lite-latest`、Groq 首選 `openai/gpt-oss-120b`、Cloudflare 首選 `@cf/meta/llama-3.3-70b-instruct-fp8-fast`（程式原本即如此；若首選額度滿或暫時失敗，才會自動降級到備選，署名會如實反映）。
- 更動檔案：`topics.py` `fetcher.py` `pipeline.py` `trial.py` `ARCHITECTURE.md`（新）`CHANGELOG.md`。

---

## [1.8.0] — 2026-11-05　新聞分類、專題來源、R2 統計表（步驟①）
**依據讀者分析：積極型（AI／半導體／記憶體 HBM／太空與 6G、NGN）與保守長期型（電力電網／儲能／數據中心供電／油氣／電信供應鏈）。**
### 新增
- **`topics.py` 新聞分類**：用關鍵詞把每則新聞歸到 17 個細項（共通 3、AI 與半導體 4、太空與下一代通訊 3、電力與電網 4、油氣 1、電信 2）。由程式決定，不用 AI。
  關鍵詞表與 `WATCHLIST`（關注公司優先清單，目前留空，之後由你提供）都在這個檔案裡，可直接改。
- **新來源**（網址均未驗證，以試跑診斷為準）：Semiconductor Engineering、EE Times、SpaceNews、Via Satellite、POWER Magazine、Canary Media、Data Center Dynamics、EIA Today in Energy、OilPrice.com、Rigzone；
  另有 10 組 Google News 主題搜尋（記憶體／HBM、AI 晶片、晶圓製造、變壓器與電網設備、數據中心供電、油氣、6G／NGN、衛星、電信運營商、電信設備），只用標題。
  同一則新聞被多個來源收錄時自動去重。
- **R2 全文頁與說明欄的統計表**：每個細項「本集涵蓋幾則／今天抓到幾則」。涵蓋數由程式比對成稿（專有名詞與數字），只算真的進了稿子的，不口播。
- 試跑 Summary 新增：統計表、每則筆記是否進入成稿、各細項抓到的標題。
### 變更
- 筆記改為六組、依分類（不再依媒體）：大盤宏觀／AI 與半導體／太空與下一代通訊／電力與電網／油氣／電信，分配給 Gemini／Groq／Cloudflare；
  每組依來源輪流取素材，避免被單一來源佔滿；Groq 連續呼叫間隔 20 秒（免費層每分鐘額度）。
- 統稿提示詞：依固定主題順序、每則筆記都要提到、不說讀者標籤。審稿改用精簡版筆記（省 token）。
- 目標長度約 8 分鐘：靠增加新聞則數，不靠擴寫（約 27 則筆記）。
### 修正
- 備用網址的時間窗以前誤用預設 30 小時（`(alt1)` 後綴沒被辨識），現在正確套用各來源的時間窗。
- 摘要中的 HTML 標籤會被去除。
### 更動檔案
`topics.py`（新）`fetcher.py` `pipeline.py` `episode.py` `main.py` `trial.py` `CHANGELOG.md`
### 回溯
把這 7 個檔案換回 1.7.1 版（`topics.py` 可保留不用刪），或照 `ROLLBACK.md`。

---

## [1.7.1] — 2026-11-05　標題格式與時長估算
- **修正標題格式**：v1.6.0 起集數標題誤用口播用的日期（「11月3日星期二」，少了年份），現在恢復成「2026年11月3日 美股科技收盤簡報」，與 Spotify 上既有集數一致。（`main.py` 1.6.1）
- 語音時長估算由 200 字/分鐘改為 280 字/分鐘（試聽 mp3 實測：1442 字 → 5 分 7 秒）。（`tts.py`）
- 更動檔案：`main.py` `tts.py` `CHANGELOG.md`。

---

## [1.7.0] — 2026-11-04　英文名稱與英文金額單位直接念
依使用者決定（聽眾具美股背景，不需要翻譯）：
- **金額保留 million／billion／trillion**：`$8.97 billion` → 「8.97 billion 美元」，不再換算成萬、億、兆（換算本身就是出錯來源，且兩岸習慣不同）。
  非美元金額仍一律標「（非美元金額）」。數字核對以「數值」比對，所以即使 AI 仍寫成中文單位，十倍之類的錯照樣抓得到。
- **公司名與人名一律保留英文原名**（Nvidia、Apple、Jensen Huang），不再翻成輝達、蘋果等；提示詞、筆記規則同步更新。
- 更動檔案：`numcheck.py` `analyzer.py` `pipeline.py` `CHANGELOG.md`（皆升為 1.7.0）。
- **請聽試跑的 mp3**（Actions → AI Trial，audio 填 1）確認中文女聲念「8.97 billion 美元」與英文名是否自然；若不自然，再考慮念法對照表或換語音。
- 回溯：把這三個檔案換回 1.6.2 版（本 repo 的 History 可找到）即可。

---

## [1.6.2] — 2026-11-04　數字核對修正（第二次試跑）
- 修正誤刪：「4億9000萬」「1億3700萬」這種由兩段組成的寫法，以前被拆成「4億」和「9000萬」各別比對而誤判成找不到；現在合併成一個數字再比對。
- 「數十億」「幾百萬」這類概數不再檢查。
- 確認有效：把 $897 million 誤寫成 89.7億（差十倍）的句子被正確刪除。
- 更動檔案：`numcheck.py` `CHANGELOG.md`。

---

## [1.6.1] — 2026-11-04　第一次試跑後微調
- 稿件出現「影響為…」把筆記欄位名稱念出來、同一件事講兩次：統稿提示詞禁止照抄欄位名稱與重複，筆記解析時若「影響」只是把事實再抄一次就改為「無」。
- 筆記數量略增（大盤 10／科技 8／儲能 5）：用更多「真實新聞」增加內容，不是灌水。
- Nasdaq 逾時放寬到 30 秒；聯準會、勞工統計局時間窗放寬到 240 小時（官方公告更新慢）。
- 試跑新增 `audio` 選項：可合成語音並從 Actions 頁面下載 mp3 試聽（不發布、不上傳 R2）。
- 更動檔案：`pipeline.py` `fetcher.py` `trial.py` `.github/workflows/trial.yml` `CHANGELOG.md`。

---

## [1.6.0] — 2026-11-04　杜絕幻覺、準時發布、休市日照發、官方來源
**回溯方式見 `ROLLBACK.md`（v1.5.1 完整備份 zip 已另存；GitHub 也請在上傳後打 v1.6.0 標籤）。**
### 核心原則
- **不湊字數**：刪除 `ensure_length` 擴寫（它曾編出「20日均線死叉」）；提示詞不再有字數目標，素材有多少講多少。
- **AI 只寫主體**：開場、風險提醒、健康提醒、AI 署名、結尾祝福全由程式寫（`frame.py`），署名反映這一集實際用了哪些模型。
### 防幻覺四道關
1. 程式先把英文金額換成中文單位（`$115 billion` → `1150億美元`），非美元金額改標「（非美元金額）」（`numcheck.py`）。
2. 筆記階段：背景／影響欄「素材沒寫就填無」；來源欄由程式對回真正的媒體。
3. 成稿後程式逐句核對數字（金額、百分比、大數字必須在素材中找得到），找不到的句子**刪除**。
4. 另一家 AI（優先不是寫稿那家）對照筆記審稿，標出無依據的句子，**刪除**（不請 AI 改寫）；標記超過 40% 視為審稿員不可靠，不採用。
- 保底：清理後太短或 AI 全失敗 → 用程式把筆記直接組成稿（不經 AI 撰寫）；連筆記都沒有 → 一段誠實的短版。
### 發布時間與時區（`market.py`）
- 集數以「美東交易日」為單位（slot）；Worker 準時觸發與 GitHub 延遲排程共用同一個 guid，不會重複。
- 開場報三地時間（美東／西岸／台北），自動處理夏令冬令；收盤後一小時（美東 17:00）發布，盤後時段會提醒數字可能變動。
- 平日休市日（硬編 2026–2027 NYSE 假日與提早收盤日）→ 發「休市簡報」（短版）；週六回顧、週日前瞻照舊。
### 來源
- 新增：Federal Reserve、BLS、Nasdaq、Mobile World Live、Utility Dive、Electrek；Google News RSS 當 WSJ／RCR／Telecoms／SDxCentral／Investopedia／Yahoo 的標題備援。
- 修正：備用來源的條目**併入**而非取代官方源條目；試跑診斷新增「最新一則時間」。
### 新增檔案
`market.py` `numcheck.py` `frame.py` `guard.py` `episode.py` `worker/worker.js` `worker/wrangler.toml` `ROLLBACK.md`
### 開關
`TWO_STAGE=0` 關兩階段；`AUDIT=0` 關 AI 審稿；`EPISODE_MODE=` 強制模式；`MIN_BODY_CHARS`（預設 500）。
### 已知限制
- 假日表為硬編，每年請對照 nyse.com 核對。新增 RSS 網址未驗證，以試跑「來源診斷」為準。
- Groq 免費層審稿若超過每分鐘額度會自動換下一家。

---

## [1.5.1] — 2026-11-02　修正週末判斷 + 補足時長 + 試跑後的提示詞修正
### 修正
- **週六回顧被誤判成週日前瞻**（`weekly.py`）：GitHub 排程實際常晚到 UTC 06:30–07:30，換成太平洋時間已過午夜，
  v1.4.0 直接取星期會差一天，導致 11/1 那集標成「下週前瞻」、而本週回顧沒有出。
  現在先把時間往前推 4 小時再換算（`evening_date_pt`），UTC 05:00–10:00 都算前一個太平洋日的傍晚，
  UTC 22:30 排程也一致。已用實際發布時間逐一驗證。
- **播報稿直接念出聽眾設定**（「對只做多、不使用槓桿的上班族…」）與「分散配置、保留現金部位」這類配置建議：
  提示詞新增兩條禁令；另要求不夾雜未翻譯的英文單字（週末集出現過 regulators）。
### 變更
- **補足時長**：稿子低於 `LENGTH_TARGET`（預設 2,600 字，前瞻 2,300 字）時，自動請 AI 在不新增事實的前提下擴寫一次
  （可補名詞與機制說明、因果、背景）；擴寫後結尾祝福不見或沒變長就沿用原稿。
  兩階段流程的筆記數量增加（大盤 8／科技通訊 6／儲能 4），每則筆記含「背景與因果」「可能影響」各一到兩句，
  統稿時每則 4–6 句、綜述 300–400 字。
- 某組筆記太少（少於挑選數的一半）會請下一家補做，取筆記較多的一份（試跑中 Cloudflare 只回 1 則）。
- 「來源」欄只填媒體名稱（試跑中 Cloudflare 填成公司名）。
- **來源抓取**：慢更新的專業媒體放寬時間窗（BNEF 96 小時；Energy-Storage、RCR、Telecoms、SDxCentral、Investopedia 72 小時；
  FierceWireless、Light Reading 48 小時），其餘維持 30 小時；為 RCR、Telecoms、WSJ、Yahoo 增加備用網址。
### 新增
- 試跑 Summary 增加「來源診斷」：每個來源的 HTTP 狀態、條目數、時間窗內條目數與錯誤，用來判斷 0 則的原因。

---

## [1.5.0] — 2026-10-30　兩階段分工 + 擴充到 18 個來源 + 聽眾設定
### 新增
- **兩階段日更**（新檔 `pipeline.py`）：第一階段依「額度與能力」把來源分三組，各由一個 AI 挑重點、輸出短筆記；
  第二階段由提供商鏈（預設 Gemini 優先）把筆記寫成 2,800–3,300 字的完整播報稿。
  分工：大盤、宏觀與財報（10 個來源）→ Gemini；科技、AI 與通訊網路（6 個來源，輸入與輸出都壓小）→ Groq；
  能源與儲能（2 個來源，英文短筆記）→ Cloudflare。某組的 AI 失敗改由 Gemini 補；整體失敗自動退回舊的一次寫完流程。
  環境變數 `TWO_STAGE=0` 可關閉。
- **新增 8 個 RSS 來源**（`fetcher.py`）：Financial Times、Benzinga、Investopedia、RCR Wireless、Telecoms.com、
  FierceWireless、Light Reading、SDxCentral。（Stocktwits 無官方 RSS，未加入。網址尚未實測，讀不到會自動略過。）
- **試跑 Summary** 新增兩段：「各來源抓到幾則」（用來檢查 RSS 是否可用）、「兩階段各組筆記」（可逐條核對事實與數字）。
  試跑預設項目改為 `pipeline`。
### 變更
- **全部提示詞加入聽眾設定與措辭規則**：中立克制、只描述可能性不預判；金額一律美元、不換算其他貨幣；
  聽眾為上班族副業、只做多、不做空、不用槓桿的保守派（含每日、每週交易與長期定投），不談做空／槓桿／選擇權。
- 結尾新增「身心健康提醒」（規律作息與運動、長期心態），不含「逢低」「加碼」等操作字眼。
- 每個來源送進一次寫完流程的則數由 6 改為 5。
- 各家 AI 的呼叫可單獨指定輸出上限（`max_out`），小任務不再佔用整份額度。
### 已知限制
- 新增來源的 RSS 網址未實測；以試跑 Summary 的「各來源抓到幾則」為準，0 則的來源要換網址或移除。
- 若 Groq 免費層仍擋下請求，該組自動改由 Gemini 做，日誌會顯示。

---

## [1.4.0] — 2026-10-30　每集約 10 分鐘 + 週末回顧／前瞻
### 新增
- **週六「本週回顧」、週日「下週前瞻」取代週末日更**（新檔 `weekly.py`）：
  依「美國太平洋時間」的星期判斷（週六＝回顧、週日＝前瞻），用 UTC 01:00 或 22:30 發布都落在同一天。
  回顧集的素材是 R2 `t/zh-TW/` 裡本週平日的播報稿全文（不再抓新聞）；
  前瞻集用本週摘要加週末新聞，只列素材中明確有日期的日程，不預測漲跌。
  本週讀到的平日稿太少（回顧少於 3 集、前瞻少於 2 集）會自動改回日更。
  集數標題後綴：`｜本週回顧`／`｜下週前瞻`。可用環境變數 `EPISODE_MODE`（daily／review／preview）強制指定。
- **試跑可選模式**：trial.yml 新增 `mode` 欄位；試跑結果會顯示估算分鐘數（每分鐘約 300 字）。
### 變更
- **平日每集目標拉長到 2,800–3,300 字（約 10 分鐘）**：提示詞改為分三到四大段、先交代背景再說影響；
  素材量由每來源 5 則×200 字改為 6 則×300 字（`ITEMS_PER_SOURCE`／`SUMMARY_CHARS`，main.py 的來源清單自動同步）。
- 各家 AI 輸出上限調高（Groq 6500、Cloudflare 5000、OpenRouter／DeepSeek 6000）。
- **太短的稿先換下一家**：低於 `SOFT_MIN_CHARS`（預設 2000 字）會先試下一個提供商，全部都太短才收下最長的一份，
  所以不會因為某家只寫 900 字就發出一集 3 分鐘的節目。
### 已知限制
- Groq 免費層的每分鐘 token 上限可能擋掉長稿（會自動換下一家，日誌可見）。
- 未實測 Edge TTS 一次念 3,000 多字的穩定性；第一集長稿請留意 Actions 日誌的「③ TTS」。
- 週日前瞻沒有專門的財經日曆來源，日程多寡取決於新聞素材。

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

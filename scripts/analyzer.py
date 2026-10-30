"""
AI 播報稿生成（v1.5.0）

預設順序：Gemini → Groq → Cloudflare Workers AI → OpenRouter(:free) → DeepSeek
  - 前三個是免費額度；DeepSeek 是付費（按量計費，一集約幾分之一美分），放最後當最終防線
  - 用環境變數 PROVIDER_ORDER 調整順序，例如 "gemini,groq,deepseek,openrouter"
  - 沒有設定對應 API Key 的提供商會自動跳過（並在日誌顯示）

GitHub Secrets（有設才會啟用）：
  GEMINI_API_KEY / GROQ_API_KEY / CLOUDFLARE_API_TOKEN+CLOUDFLARE_ACCOUNT_ID / OPENROUTER_API_KEY / DEEPSEEK_API_KEY
可選：用環境變數 GROQ_MODEL / CLOUDFLARE_MODEL / OPENROUTER_MODEL / DEEPSEEK_MODEL 指定優先使用的模型

設計原則：模型名稱常被下架，所以不寫死，執行時先向各家 API 查詢「這把 key 現在
實際可用的模型」，再依偏好順序嘗試；查不到才退回內建名單。
"""
import logging, os, re, time
import requests

__version__ = "1.5.0"

log = logging.getLogger(__name__)

SYSTEM = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
請把提供的新聞素材整理成一段完整的廣播播報稿。

格式規定：
1. 開場白：「各位聽眾朋友好，歡迎收聽美股科技收盤簡報，今天是 {date}，我是您的主持人。」
2. 用自然口語過渡每則新聞，禁止使用「第一則」「第二則」等數字列表
   常用過渡語：「首先來看」「接下來」「另一個值得關注的消息是」「在科技板塊方面」
   「我們再來看宏觀面」「說到能源與儲能」「值得投資人注意的是」
3. 每則新聞簡述事實 + 一句對投資者的影響分析
4. 結尾：風險提醒（市場波動來自技術面、消息面、機構資金等多重因素，
   請勿單憑新聞買賣股票，投資需謹慎）
5. 最後祝福：「祝各位身體健康、投資順利，闔家平安，神愛世人，耶穌愛您，我們明天見！」
6. 全程繁體中文口語，不用 Markdown 符號，不用括號，字數 2800–3300 字（約 10 分鐘），分成三到四大段：
   美股與科技重點、宏觀與利率、能源與產業、其他值得留意的消息
   每則新聞先交代事實與背景，再用兩三句說明為什麼重要、可能牽動哪些族群
   素材不足以撐到這個長度時，寧可寫短，也不可編造素材沒有的內容或自行補數字
7. 只陳述事實與影響，絕對不給買賣建議：不得出現「逢低加碼」「建議觀望」「持續持有」「可以買進」等字眼
8. 「對投資者的影響」要用自然的話帶出，不要照抄「對投資者的影響分析是」這幾個字，
   每則的說法都要不同；每則新聞至少兩句，不要把全文壓成簡短摘要
9. 一律使用台灣慣用詞：聯準會（不用美聯儲、聯儲局）、升息／降息（不用加息）、
   盈餘或獲利（不用盈利）、營收（不用收入）、財報、股價、輝達、蘋果、微軟、亞馬遜；
   數字用口語中文念法，例如「百分之十」「三百三十二億美元」；
   英文公司名可保留原文。只能根據提供的素材，不可自行補充素材沒有的事實"""

_AUDIENCE_RULES = """語氣中立克制：用「可能」「值得留意」「市場關注」描述可能性，避免「將會」「必然」「勢必」「一定」，不做預判。
金額一律以美元表示，不要換算其他貨幣；素材的金額若不是美元，不要寫出那個金額，只說明事件本身。
聽眾多是上班族副業投資者，只做多、不做空、不用槓桿，有每日交易、每週交易與長期定投的人，多數有技術背景、偏保守。
因此說明影響時，著重「對只做多、不加槓桿的人需要留意什麼風險或指標」；不談做空、槓桿、選擇權等操作；
可以多交代一點原理與因果，不要用煽動的字眼。"""

_RULES_COMMON = """全程繁體中文口語，不用 Markdown 符號，不用括號。
只陳述事實與可能的影響，絕對不給買賣建議；不得出現「逢低加碼」「建議觀望」「持續持有」「可以買進」等字眼。
使用台灣慣用詞：聯準會、升息／降息、盈餘或獲利、營收、財報；數字用口語中文念法，例如「百分之十」。
只能根據提供的素材，不可補充素材沒有的事實、數字或日期；素材不足時寧可寫短。
""" + _AUDIENCE_RULES

SYSTEM_REVIEW = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
這是週六的「本週回顧」特別集。素材是本週每天播報稿的全文，請整理成一集約 10 分鐘的回顧。

格式規定：
1. 開場白：「各位聽眾朋友好，歡迎收聽美股科技收盤簡報，今天是 {date}，這一集是本週回顧。」
2. 先用一小段說明本週的整體氣氛，再歸納三到四條主線（例如科技財報、聯準會與利率、能源與油價、產業趨勢），
   每條主線說清楚：週內發生了什麼、前後怎麼演變、幾件事之間有什麼關聯。
3. 用「週初」「週中」「週五」這類時間順序串起來；有相互矛盾或出現反轉的消息要特別點出。
4. 最後一小段整理「本週留下的未解問題」，只能是素材中已經出現、尚未有答案的事，不可自行推測結果。
5. 結尾：風險提醒（市場波動來自技術面、消息面、機構資金等多重因素，請勿單憑新聞買賣股票，投資需謹慎）
6. 最後祝福：「祝各位身體健康、投資順利，闔家平安，神愛世人，耶穌愛您，我們下週見！」
7. 字數 2800–3300 字。
""" + _RULES_COMMON

SYSTEM_PREVIEW = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
這是週日的「下週前瞻」特別集。素材是本週播報稿摘要，以及週末最新的新聞標題，請整理成一集約 10 分鐘的前瞻。

格式規定：
1. 開場白：「各位聽眾朋友好，歡迎收聽美股科技收盤簡報，今天是 {date}，這一集是下週前瞻。」
2. 先用一小段回顧本週留下的背景，再說「下週要留意的事件」：
   只列出素材中明確提到的日程（財報公布、經濟數據、聯準會相關活動、重要會議或政策期限等），
   每項說明它為什麼受關注、市場目前的疑問是什麼。
3. 素材沒有寫明日期的事，只能說「近期」或「後續」，不可自行推算或補上日期。
4. 如果素材中能明確列出的日程很少，就如實說「目前公開消息中可確認的日程不多」，再把篇幅放在背景與觀察重點，
   不要為了湊字數捏造行程。
5. 結尾：風險提醒（市場波動來自技術面、消息面、機構資金等多重因素，請勿單憑新聞買賣股票，投資需謹慎）
6. 最後祝福：「祝各位身體健康、投資順利，闔家平安，神愛世人，耶穌愛您，我們下週見！」
7. 字數 2400–3000 字。
""" + _RULES_COMMON

SYSTEM = SYSTEM + "\n補充規則：\n" + _AUDIENCE_RULES

MIN_SCRIPT_CHARS = 300          # 低於這個長度視為失敗（被截斷或空回應）
SOFT_MIN_CHARS = int(os.environ.get("SOFT_MIN_CHARS", "") or 2000)  # 低於這個長度先換下一家，全都太短才收下最長的
ITEMS_PER_SOURCE = 5            # 每個來源送給 AI 幾則（main.py 的來源清單會讀這個值，自動同步）
SUMMARY_CHARS = 300             # 每則摘要送多少字
_RETRY_STATUS = (429, 500, 502, 503, 504)   # 暫時性錯誤：同模型重試一次
_FATAL_STATUS = (401, 402, 403)             # 金鑰 / 餘額問題：換模型也沒用，直接放棄該提供商


class ApiError(Exception):
    def __init__(self, status: int, body: str, model: str = ""):
        self.status, self.body, self.model = status, body or "", model
        super().__init__(f"HTTP {status} model={model}: {self.body[:400]}")


def _items_block(items: list[dict], date: str, tail: str = "") -> str:
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it["source"], []).append(it)
    lines = [f"以下是今天（{date}）的新聞素材{tail}：\n"]
    for src, its in groups.items():
        lines.append(f"\n【{src}】")
        for it in its[:ITEMS_PER_SOURCE]:
            lines.append(f"- {it['title']}")
            if it.get("summary"):
                lines.append(f"  {it['summary'][:SUMMARY_CHARS]}")
    return "\n".join(lines)


def _build_prompt(items: list[dict], date: str, mode: str = "daily", digest: str = "") -> str:
    if mode == "review":
        return (SYSTEM_REVIEW.replace("{date}", date)
                + f"\n\n以下是本週每天的播報稿全文，請整理成本週回顧：\n\n{digest}")
    if mode == "preview":
        extra = _items_block(items, date) if items else "（週末沒有抓到新的新聞素材）"
        return (SYSTEM_PREVIEW.replace("{date}", date)
                + f"\n\n【本週播報稿摘要】\n{digest}\n\n【週末最新新聞】\n{extra}")
    return SYSTEM.replace("{date}", date) + "\n\n" + _items_block(items, date, "，請整理成播報稿")


# ── 共用：依序嘗試候選模型 ─────────────────────────────────────────────
def _run_candidates(name: str, candidates: list[str], call) -> str:
    """call(model) -> 文字；失敗時丟 ApiError 或 requests 例外。"""
    errors: list[str] = []
    for model in candidates:
        for attempt in (1, 2):
            try:
                text = call(model)
            except ApiError as e:
                errors.append(f"{model}: HTTP {e.status}")
                log.warning(f"   {name} {model}: HTTP {e.status} {e.body[:200]}")
                if e.status in _FATAL_STATUS:
                    raise RuntimeError(
                        f"{name} 認證或餘額問題 (HTTP {e.status})：{e.body[:200]}")
                if e.status in _RETRY_STATUS and attempt == 1:
                    time.sleep(6)
                    continue
                break
            except requests.RequestException as e:
                errors.append(f"{model}: {type(e).__name__}")
                log.warning(f"   {name} {model}: {type(e).__name__}（第 {attempt} 次）")
                if attempt == 1:
                    time.sleep(3)
                    continue
                break
            if text:
                log.info(f"   ✓ {name} 使用模型: {model}")
                return text
            errors.append(f"{model}: empty")
            log.warning(f"   {name} {model}: 回應內容為空（可能被截斷或被安全機制擋下）")
            break
    raise RuntimeError(f"{name} 全部候選模型失敗: {errors}")


def _pick(avail: list[str], preferred: list[str], override: str | None,
          name: str, heuristic=None) -> list[str]:
    """avail=API 回報的可用模型；依偏好名單挑出候選。avail 為空代表查詢失敗，用內建名單盲試。"""
    cands: list[str] = []
    if override:
        cands.append(override)
    if avail:
        matched = [m for m in preferred if m in avail]
        if not matched and heuristic:
            matched = [m for m in avail if heuristic(m)][:3]
        if not matched:
            log.warning(f"   {name}: 可用模型中找不到預設名單。API 回報的模型: {avail[:25]}")
        cands += matched
    else:
        cands += preferred
    out: list[str] = []
    for m in cands:
        if m and m not in out:
            out.append(m)
    return out or list(preferred)


def _list_models(base_url: str, key: str) -> list[str]:
    try:
        r = requests.get(f"{base_url}/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=20)
        r.raise_for_status()
        return [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
    except Exception as e:
        log.warning(f"   取得 {base_url} 模型清單失敗（{type(e).__name__}），改用內建名單")
        return []


def _chat_call(base_url: str, key: str, model: str, prompt: str, max_tokens: int,
               extra: dict | None = None, headers: dict | None = None) -> str:
    """OpenAI 相容格式（Groq / OpenRouter / DeepSeek 共用）。"""
    def post(payload):
        h = {"Authorization": f"Bearer {key}"}
        h.update(headers or {})
        return requests.post(f"{base_url}/chat/completions",
                             headers=h, json=payload, timeout=120)

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": max_tokens,
    }
    if extra:
        payload.update(extra)
    r = post(payload)
    if r.status_code == 400 and extra:
        # 額外參數（如 reasoning_effort）若不被接受，去掉再試一次
        for k in extra:
            payload.pop(k, None)
        log.warning(f"   {model}: 400，去掉額外參數 {list(extra)} 重試")
        r = post(payload)
    if not r.ok:
        raise ApiError(r.status_code, r.text, model)

    msg = ((r.json().get("choices") or [{}])[0].get("message")) or {}
    text = msg.get("content") or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


# ── 1. Gemini（免費）──────────────────────────────────────────────────
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_FALLBACK_MODELS = [          # models.list 失敗時才用
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
]
_GEMINI_SKIP = ("tts", "image", "live", "audio", "embed", "robotics",
                "computer", "imagen", "veo", "gemma", "aqa")


def _gemini_candidates(key: str) -> list[str]:
    found: list[str] = []
    try:
        r = requests.get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": key},
                         params={"pageSize": 200}, timeout=20)
        r.raise_for_status()
        for m in r.json().get("models", []):
            name = m.get("name", "").removeprefix("models/")
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if "flash" not in name or any(w in name for w in _GEMINI_SKIP):
                continue
            found.append(name)
    except Exception as e:
        log.warning(f"   Gemini models.list 失敗（{type(e).__name__}），改用備用名單")
    found.sort(reverse=True)
    found.sort(key=lambda n: ("preview" in n) or ("exp" in n))   # 穩定版優先
    ordered: list[str] = []
    for n in found + GEMINI_FALLBACK_MODELS:
        if n not in ordered:
            ordered.append(n)
    ordered = ordered[:4]
    log.info(f"   Gemini 候選模型: {ordered}")
    return ordered


def _gemini_extract(data: dict) -> str:
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


def _gemini(prompt: str, max_out: int | None = None) -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY 未設定")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        # 金鑰放 header：錯誤訊息不會把 ?key=... 印到公開日誌
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": max_out or 8192},
    }

    def call(model: str) -> str:
        r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent",
                          headers={"x-goog-api-key": key}, json=body, timeout=120)
        if not r.ok:
            raise ApiError(r.status_code, r.text, model)
        return _gemini_extract(r.json())

    return _run_candidates("Gemini", _gemini_candidates(key), call)


# ── 2. Groq（免費）────────────────────────────────────────────────────
# 官方停用頁：llama3-70b-8192 已於 2025-08 關閉；llama-3.3-70b-versatile 於 2026-08-16 關閉。
# 因此偏好 gpt-oss 系列；實際用哪個以執行時 /models 回報為準。
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_PREFERRED = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]


def _groq(prompt: str, max_out: int | None = None) -> str:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise ValueError("GROQ_API_KEY 未設定")
    cands = _pick(_list_models(GROQ_BASE, key), GROQ_PREFERRED,
                  os.environ.get("GROQ_MODEL"), "Groq")
    log.info(f"   Groq 候選模型: {cands}")

    def call(model: str) -> str:
        extra = {"reasoning_effort": "low"} if "gpt-oss" in model else None
        # max_tokens 不宜過大：Groq 免費層的每分鐘 token 上限會把它算進去
        return _chat_call(GROQ_BASE, key, model, prompt, max_out or 6500, extra)

    return _run_candidates("Groq", cands, call)


# ── Cloudflare Workers AI（免費額度：每天 10,000 neurons）──────────────
# 使用 OpenAI 相容端點；需要 CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID。
# 模型上下文視窗約 24k tokens，一集素材遠低於此。
CF_PREFERRED = ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/meta/llama-3.1-8b-instruct"]


def _cloudflare(prompt: str, max_out: int | None = None) -> str:
    key = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not key or not acct:
        raise ValueError("CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID 未設定")
    base = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1"
    cands = [m for m in [os.environ.get("CLOUDFLARE_MODEL", "")] + CF_PREFERRED if m]
    log.info(f"   Cloudflare 候選模型: {cands}")
    return _run_candidates(
        "Cloudflare", cands,
        lambda m: _chat_call(base, key, m, prompt, max_out or 5000))


# ── 3. OpenRouter（免費 :free 模型，第四個備援）────────────────────────
# 官方限制：未儲值帳號 20 次/分、50 次/天；每天只跑一次綽綽有餘。
# :free 模型清單常變動，所以每次向公開的 /models 查詢現在有哪些。
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OR_PREFER = ("gpt-oss-120b", "llama-3.3-70b", "qwen3", "deepseek", "gemma-3", "mistral")
_OR_FALLBACK = ["openai/gpt-oss-120b:free", "meta-llama/llama-3.3-70b-instruct:free"]


def _openrouter_candidates() -> list[str]:
    free: list[str] = []
    try:
        r = requests.get(f"{OPENROUTER_BASE}/models", timeout=20)
        r.raise_for_status()
        for m in r.json().get("data", []):
            mid = m.get("id", "")
            if not mid.endswith(":free"):
                continue
            out = (m.get("architecture") or {}).get("output_modalities") or ["text"]
            if "text" not in out or (m.get("context_length") or 0) < 16000:
                continue
            free.append(mid)
    except Exception as e:
        log.warning(f"   OpenRouter 模型清單失敗（{type(e).__name__}），改用內建名單")

    def rank(mid: str) -> int:
        for i, k in enumerate(_OR_PREFER):
            if k in mid:
                return i
        return len(_OR_PREFER)

    free.sort(key=lambda x: (rank(x), x))
    cands: list[str] = []
    for m in [os.environ.get("OPENROUTER_MODEL", "")] + free + _OR_FALLBACK:
        if m and m not in cands:
            cands.append(m)
    cands = cands[:4]
    log.info(f"   OpenRouter 候選模型: {cands}")
    return cands


def _openrouter(prompt: str, max_out: int | None = None) -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError("OPENROUTER_API_KEY 未設定")
    headers = {"X-Title": "TechStockMarket-daily"}
    return _run_candidates(
        "OpenRouter", _openrouter_candidates(),
        lambda m: _chat_call(OPENROUTER_BASE, key, m, prompt, max_out or 6000, None, headers))


# ── 4. DeepSeek（付費，按量計費；最後防線）─────────────────────────────
# 網路資料顯示舊名 deepseek-chat 已規劃退役（改指向 V4），所以同樣以 /models 回報為準。
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_PREFERRED = ["deepseek-v4-flash", "deepseek-chat"]


def _deepseek(prompt: str, max_out: int | None = None) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY 未設定")
    heuristic = lambda m: m.startswith("deepseek") and not any(
        w in m for w in ("reason", "r1", "coder", "pro"))
    cands = _pick(_list_models(DEEPSEEK_BASE, key), DEEPSEEK_PREFERRED,
                  os.environ.get("DEEPSEEK_MODEL"), "DeepSeek", heuristic)
    log.info(f"   DeepSeek 候選模型: {cands}")
    return _run_candidates(
        "DeepSeek", cands,
        lambda m: _chat_call(DEEPSEEK_BASE, key, m, prompt, max_out or 6000))


# ── 主入口：依序降級 ───────────────────────────────────────────────────
_REGISTRY = {
    "gemini":     ("Gemini",     _gemini,     "GEMINI_API_KEY"),
    "groq":       ("Groq",       _groq,       "GROQ_API_KEY"),
    "cloudflare": ("Cloudflare", _cloudflare, "CLOUDFLARE_API_TOKEN"),
    "openrouter": ("OpenRouter", _openrouter, "OPENROUTER_API_KEY"),
    "deepseek":   ("DeepSeek",   _deepseek,   "DEEPSEEK_API_KEY"),
}
DEFAULT_ORDER = "gemini,groq,cloudflare,openrouter,deepseek"


def _providers() -> list[tuple]:
    order = [x.strip().lower()
             for x in os.environ.get("PROVIDER_ORDER", DEFAULT_ORDER).split(",")
             if x.strip()]
    out = []
    for key in order:
        if key in _REGISTRY:
            out.append(_REGISTRY[key])
        else:
            log.warning(f"   PROVIDER_ORDER 含未知名稱 {key!r}，已忽略")
    return out


def build_script(items: list[dict], date: str, mode: str = "daily", digest: str = "") -> str:
    if mode == "daily" and not items:
        log.warning("   無新聞素材，生成預設播報稿")
        return (
            f"各位聽眾朋友好，歡迎收聽美股科技收盤簡報，今天是{date}。"
            "由於今日數據抓取異常，暫無詳細新聞播報，請稍後查看文字版。"
            "祝各位身體健康，闔家平安，神愛世人，耶穌愛您，我們明天見！"
        )

    prompt = _build_prompt(items, date, mode, digest)
    log.info(f"   模式：{mode}；提示詞約 {len(prompt)} 字")
    return _run_chain(prompt)


def _run_chain(prompt: str) -> str:
    """依提供商順序降級，直到拿到夠長的稿。兩階段流程的「統稿」也用這個。"""
    providers = _providers()
    have = [n for n, _, k in providers if os.environ.get(k)]
    log.info(f"   提供商順序: {[n for n, _, _ in providers]}；已設定 Key: {have}")
    tried: list[str] = []
    best = ""                               # 太短但可用的備案

    for name, fn, env_key in providers:
        if not os.environ.get(env_key):
            log.warning(f"   {name}: 未設定 {env_key}，跳過")
            continue
        tried.append(name)
        try:
            log.info(f"   嘗試 {name}...")
            text = fn(prompt)
            # 清理殘留 Markdown 符號
            text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
            text = re.sub(r"#{1,4}\s*", "", text)
            if len(text) < MIN_SCRIPT_CHARS:
                raise RuntimeError(f"回傳內容過短（{len(text)} 字），視為失敗")
            if len(text) < SOFT_MIN_CHARS:
                log.warning(f"   {name} 只有 {len(text)} 字（目標至少 {SOFT_MIN_CHARS}），先換下一家，"
                            "全部都太短時才使用最長的一份")
                if len(text) > len(best):
                    best = text
                continue
            log.info(f"   ✓ {name} 完成，{len(text)} 字")
            return text
        except Exception as ex:
            log.warning(f"   {name} 失敗: {ex}")
            time.sleep(2)

    if best:
        log.warning(f"   沒有提供商達到 {SOFT_MIN_CHARS} 字，改用最長的一份（{len(best)} 字）")
        return best
    raise RuntimeError(
        f"所有 AI 提供商均失敗（已嘗試: {tried or '無，請檢查 API Key 設定'}）")

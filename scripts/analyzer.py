"""
AI 稿件生成（v1.6.0）

v1.6.0 的原則：AI 只寫「節目主體」，開場、風險提醒、署名、結尾由程式（frame.py）負責；
不設字數目標、不擴寫，素材有多少就講多少；寧可短，也不要編。

預設順序：Gemini → Groq → Cloudflare Workers AI → OpenRouter(:free) → DeepSeek
  - 用環境變數 PROVIDER_ORDER 調整順序；沒有設定 API Key 的提供商會自動跳過
GitHub Secrets（有設才會啟用）：
  GEMINI_API_KEY / GROQ_API_KEY / CLOUDFLARE_API_TOKEN+CLOUDFLARE_ACCOUNT_ID / OPENROUTER_API_KEY / DEEPSEEK_API_KEY
模型名稱不寫死：執行時先向各家 API 查詢目前可用的模型，再依偏好順序嘗試。
"""
import logging, os, re, time
import requests

__version__ = "1.7.0"

log = logging.getLogger(__name__)

LAST_MODEL: dict[str, str] = {}     # 提供商代號 → 最近一次成功使用的模型名（署名用）
LAST_WINNER: dict[str, str] = {"provider": ""}   # _run_chain 最後由哪一家寫成

_AUDIENCE_RULES = """語氣中立克制：用「可能」「值得留意」「市場關注」描述可能性，避免「將會」「必然」「勢必」「一定」，不做預判。
金額一律以美元表示，不要換算其他貨幣；素材中標示「（非美元金額）」的地方不要引用金額，只說明事件本身。
說明影響時，著重「這件事可能牽動哪些風險、指標或後續事件」；不談做空、槓桿、選擇權。
不要在稿裡提到聽眾的身分或投資習慣，也不要給資產配置或持股建議（例如分散配置、保留現金、檢視持股、逢低、加碼）。
全文用繁體中文；除了公司名、人名、million／billion／trillion 金額單位，以及 AI、Fed、CPI 這類通用縮寫，不要夾雜沒有翻譯的英文單字。"""

_RULES_COMMON = """【最重要：只能依據素材】
- 只能使用素材裡明確寫出的事實、數字、日期與因果。素材沒有說的，一律不要寫：
  不要補充背景、原因、技術指標（例如均線、支撐壓力）、歷史比較、市場預測或你自己知道的資訊。
- 數字與單位照素材抄寫，用阿拉伯數字。金額保留英文單位 million、billion、trillion，例如「8.97 billion 美元」「360 million 美元」，
  絕對不要換算成萬、億、兆，也不要四捨五入或改單位；百分比可寫「3.5%」。
- 公司名與人名一律保留英文原名，不要翻譯成中文（例如 Nvidia、Apple、Jensen Huang）。
- 不要為了拉長篇幅而重複、灌水或加入空泛的評論。素材有多少就講多少，講完就結束，短一點沒有關係。
- 沒有把握的內容就不要寫。
【格式】全程繁體中文口語，不用 Markdown 符號，不用括號，不用數字編號列表；段落之間空一行。
只寫節目主體：不要寫開場白、不要寫風險提醒、不要寫結尾祝福或署名（這些由系統另外加上）。
絕對不給買賣建議。使用台灣慣用詞：聯準會、升息／降息、盈餘或獲利、營收、財報（公司名與人名除外，保留英文）。
""" + _AUDIENCE_RULES

SYSTEM = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
請把提供的新聞素材整理成廣播播報稿的主體。
結構：先用一小段概述今天素材中的主要脈絡，再依主題逐則說明（事實，然後素材中提到的影響或背景），
用自然口語過渡，例如「首先來看」「接下來」「另一個值得關注的消息是」。
""" + _RULES_COMMON

SYSTEM_HOLIDAY = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
今天美股休市，這是一集簡短的休市日簡報。請只挑素材中最重要的幾則（宏觀、政策、財報或產業消息），
簡明說明各自的事實與素材提到的影響，並可以說明休市期間有哪些消息值得在下個交易日留意。
開場已經說明今天休市，主體不用再重複。篇幅簡短即可。
""" + _RULES_COMMON

SYSTEM_REVIEW = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
這是週六的「本週回顧」。素材是本週每天播報稿的全文。請整理成回顧的主體：
先簡述本週整體脈絡，再歸納素材中出現過的幾條主線（例如科技財報、聯準會與利率、能源、產業趨勢），
說明各主線週內的前後演變與關聯，有反轉或矛盾的消息要點出；
最後列出「本週留下的未解問題」，只能是素材中已經出現、尚未有答案的事。
用「週初」「週中」「週五」等時間順序串聯，只能引用素材裡出現過的內容與數字。
""" + _RULES_COMMON

SYSTEM_PREVIEW = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
這是週日的「下週前瞻」。素材是本週播報稿摘要，以及最新的新聞與官方公告標題。請整理成前瞻的主體：
先簡述本週留下的背景；再說「下週要留意的事件」：只列素材中明確提到的日程（財報、經濟數據、聯準會活動、政策期限等），
說明它受關注的原因與目前的疑問。素材沒有寫明日期的事只能說「近期」或「後續」，不可自行推算日期。
如果素材中能確認的日程很少，就如實說「目前公開消息中可確認的日程不多」，講完背景與觀察重點就結束，不要編造行程。
""" + _RULES_COMMON

MIN_SCRIPT_CHARS = 150          # 低於這個長度視為失敗（空回應或被截斷）
SOFT_MIN_CHARS = int(os.environ.get("SOFT_MIN_CHARS", "") or 400)
ITEMS_PER_SOURCE = 5            # 每個來源送給 AI 幾則（main.py 的來源清單會讀這個值）
SUMMARY_CHARS = 300             # 每則摘要送多少字
_RETRY_STATUS = (429, 500, 502, 503, 504)   # 暫時性錯誤：同模型重試一次
_FATAL_STATUS = (401, 402, 403)             # 金鑰 / 餘額問題：換模型也沒用，直接放棄該提供商


class ApiError(Exception):
    def __init__(self, status: int, body: str, model: str = ""):
        self.status, self.body, self.model = status, body or "", model
        super().__init__(f"HTTP {status} model={model}: {self.body[:400]}")


def ai_view(it: dict) -> tuple[str, str]:
    """給 AI 看的標題與摘要：優先用已把外幣金額剔除、美元寫成「X billion 美元」的版本。"""
    return it.get("ai_title") or it["title"], it.get("ai_summary") if "ai_summary" in it else it.get("summary", "")


def _items_block(items: list[dict], date: str, tail: str = "", per_source: int | None = None) -> str:
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it["source"], []).append(it)
    lines = [f"以下是新聞素材（美東交易日 {date}）{tail}：\n"]
    for src, its in groups.items():
        lines.append(f"\n【{src}】")
        for it in its[: per_source or ITEMS_PER_SOURCE]:
            t, s = ai_view(it)
            lines.append(f"- {t}")
            if s:
                lines.append(f"  {s[:SUMMARY_CHARS]}")
    return "\n".join(lines)


def _build_prompt(items: list[dict], date: str, mode: str = "daily", digest: str = "") -> str:
    if mode == "review":
        return SYSTEM_REVIEW + f"\n\n以下是本週每天的播報稿全文：\n\n{digest}"
    if mode == "preview":
        extra = _items_block(items, date) if items else "（週末沒有抓到新的新聞素材）"
        return SYSTEM_PREVIEW + f"\n\n【本週播報稿摘要】\n{digest}\n\n【最新新聞與公告】\n{extra}"
    if mode == "holiday":
        return SYSTEM_HOLIDAY + "\n\n" + _items_block(items, date, "", per_source=3)
    return SYSTEM + "\n\n" + _items_block(items, date)


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
                LAST_MODEL[name.lower()] = model
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


def build_body(items: list[dict], date: str, mode: str = "daily", digest: str = "") -> str:
    """只回傳節目主體（不含開場與結尾）。沒有素材時回傳空字串，由 episode.py 決定怎麼辦。"""
    if mode in ("daily", "holiday") and not items:
        return ""
    prompt = _build_prompt(items, date, mode, digest)
    log.info(f"   模式：{mode}；提示詞約 {len(prompt)} 字")
    return _run_chain(prompt)


def _run_chain(prompt: str) -> str:
    """依提供商順序降級，直到拿到夠長的稿。兩階段流程的「統稿」也用這個。"""
    order = [x.strip().lower() for x in os.environ.get("PROVIDER_ORDER", DEFAULT_ORDER).split(",") if x.strip()]
    order = [k for k in order if k in _REGISTRY]
    have = [k for k in order if os.environ.get(_REGISTRY[k][2])]
    log.info(f"   提供商順序: {order}；已設定 Key: {have}")
    tried: list[str] = []
    best, best_key = "", ""                 # 太短但可用的備案

    for key in order:
        name, fn, env_key = _REGISTRY[key]
        if not os.environ.get(env_key):
            log.warning(f"   {name}: 未設定 {env_key}，跳過")
            continue
        tried.append(name)
        try:
            log.info(f"   嘗試 {name}...")
            text = fn(prompt)
            text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
            text = re.sub(r"#{1,4}\s*", "", text)
            if len(text) < MIN_SCRIPT_CHARS:
                raise RuntimeError(f"回傳內容過短（{len(text)} 字），視為失敗")
            if len(text) < SOFT_MIN_CHARS:
                log.warning(f"   {name} 只有 {len(text)} 字（低於 {SOFT_MIN_CHARS}），先換下一家，全部都太短才用最長的")
                if len(text) > len(best):
                    best, best_key = text, key
                continue
            log.info(f"   ✓ {name} 完成，{len(text)} 字")
            LAST_WINNER["provider"] = key
            return text
        except Exception as ex:
            log.warning(f"   {name} 失敗: {ex}")
            time.sleep(2)

    if best:
        log.warning(f"   沒有提供商達到 {SOFT_MIN_CHARS} 字，改用最長的一份（{len(best)} 字）")
        LAST_WINNER["provider"] = best_key
        return best
    raise RuntimeError(f"所有 AI 提供商均失敗（已嘗試: {tried or '無，請檢查 API Key 設定'}）")

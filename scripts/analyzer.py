"""
AI 播報稿生成（v1.2.0）

預設順序：Gemini → Groq → OpenRouter(:free) → DeepSeek
  - 前三個是免費額度；DeepSeek 是付費（按量計費，一集約幾分之一美分），放最後當最終防線
  - 用環境變數 PROVIDER_ORDER 調整順序，例如 "gemini,groq,deepseek,openrouter"
  - 沒有設定對應 API Key 的提供商會自動跳過（並在日誌顯示）

GitHub Secrets（有設才會啟用）：
  GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY / DEEPSEEK_API_KEY
可選：用環境變數 GROQ_MODEL / OPENROUTER_MODEL / DEEPSEEK_MODEL 指定優先使用的模型

設計原則：模型名稱常被下架，所以不寫死，執行時先向各家 API 查詢「這把 key 現在
實際可用的模型」，再依偏好順序嘗試；查不到才退回內建名單。
"""
import logging, os, re, time
import requests

__version__ = "1.2.0"

log = logging.getLogger(__name__)

SYSTEM = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
請把提供的新聞素材整理成一段完整的廣播播報稿。

格式規定：
1. 開場白：「各位聽眾朋友好，歡迎收聽美股科技晨報，今天是 {date}，我是您的主持人。」
2. 用自然口語過渡每則新聞，禁止使用「第一則」「第二則」等數字列表
   常用過渡語：「首先來看」「接下來」「另一個值得關注的消息是」「在科技板塊方面」
   「我們再來看宏觀面」「說到能源與儲能」「值得投資人注意的是」
3. 每則新聞簡述事實 + 一句對投資者的影響分析
4. 結尾：風險提醒（市場波動來自技術面、消息面、機構資金等多重因素，
   請勿單憑新聞買賣股票，投資需謹慎）
5. 最後祝福：「祝各位身體健康、投資順利，闔家平安，神愛世人，耶穌愛您，我們明天見！」
6. 全程繁體中文口語，不用 Markdown 符號，不用括號，字數 1200–1800 字"""

MIN_SCRIPT_CHARS = 300          # 低於這個長度視為失敗（被截斷或空回應）
_RETRY_STATUS = (429, 500, 502, 503, 504)   # 暫時性錯誤：同模型重試一次
_FATAL_STATUS = (401, 402, 403)             # 金鑰 / 餘額問題：換模型也沒用，直接放棄該提供商


class ApiError(Exception):
    def __init__(self, status: int, body: str, model: str = ""):
        self.status, self.body, self.model = status, body or "", model
        super().__init__(f"HTTP {status} model={model}: {self.body[:400]}")


def _build_prompt(items: list[dict], date: str) -> str:
    system = SYSTEM.replace("{date}", date)
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it["source"], []).append(it)

    lines = [f"以下是今天（{date}）的新聞素材，請整理成播報稿：\n"]
    for src, its in groups.items():
        lines.append(f"\n【{src}】")
        for it in its[:5]:
            lines.append(f"- {it['title']}")
            if it.get("summary"):
                lines.append(f"  {it['summary'][:200]}")
    return system + "\n\n" + "\n".join(lines)


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


def _gemini(prompt: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY 未設定")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        # 金鑰放 header：錯誤訊息不會把 ?key=... 印到公開日誌
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 8192},
    }

    def call(model: str) -> str:
        r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent",
                          headers={"x-goog-api-key": key}, json=body, timeout=120)
        if not r.ok:
            raise ApiError(r.status_code, r.text, model)
        return _gemini_extract(r.json())

    

"""
AI 播報稿生成
模型鏈：Gemini（動態查詢可用模型）→ Groq → DeepSeek

重點修正：
1. Gemini 不再寫死模型名稱，先呼叫 models.list 取得這把 key 實際可用的 flash 模型
2. 單一模型逾時 / 429 / 5xx 只會重試或換下一個模型，不會直接中斷整個 Gemini
3. Gemini 金鑰改放 header（x-goog-api-key），錯誤訊息不會再把 ?key=... 印進公開日誌
4. Groq 預設模型改為 llama-3.3-70b-versatile（llama3-70b-8192 已下架），
   並可用環境變數 GROQ_MODEL 覆蓋
5. 所有提供商失敗時，會把 HTTP 狀態碼與回應內文印出來，方便診斷
"""
import logging, os, re, time
import requests

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

MIN_SCRIPT_CHARS = 300  # 低於這個長度視為失敗（避免被截斷或空回應）


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


# ── Gemini ─────────────────────────────────────────────────────────────
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# models.list 失敗時的備用名單（alias 會自動指向目前的最新版）
GEMINI_FALLBACK_MODELS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
]

# 這些名稱的模型不是用來生成文字稿的
_SKIP_WORDS = ("tts", "image", "live", "audio", "embed", "robotics",
               "computer", "imagen", "veo", "gemma", "aqa")

MAX_GEMINI_CANDIDATES = 4


def _gemini_candidates(key: str) -> list[str]:
    """向 API 查詢這把 key 目前可用、支援 generateContent 的 flash 模型。"""
    found: list[str] = []
    try:
        r = requests.get(
            f"{GEMINI_BASE}/models",
            headers={"x-goog-api-key": key},
            params={"pageSize": 200},
            timeout=20,
        )
        r.raise_for_status()
        for m in r.json().get("models", []):
            name = m.get("name", "").removeprefix("models/")
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if "flash" not in name or any(w in name for w in _SKIP_WORDS):
                continue
            found.append(name)
    except Exception as e:
        log.warning(f"   Gemini models.list 失敗: {type(e).__name__}，改用備用名單")

    # 穩定版優先於 preview/exp，其餘依名稱由新到舊
    found.sort(reverse=True)
    found.sort(key=lambda n: ("preview" in n) or ("exp" in n))

    ordered: list[str] = []
    for n in found + GEMINI_FALLBACK_MODELS:
        if n not in ordered:
            ordered.append(n)
    ordered = ordered[:MAX_GEMINI_CANDIDATES]
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
        "generationConfig": {
            "temperature": 0.4,
            # 思考型模型的 thinking tokens 也會算進去，留足空間避免被截斷
            "maxOutputTokens": 8192,
        },
    }
    errors: list[str] = []

    for model in _gemini_candidates(key):
        for attempt in (1, 2):
            try:
                r = requests.post(
                    f"{GEMINI_BASE}/models/{model}:generateContent",
                    headers={"x-goog-api-key": key},
                    json=body,
                    timeout=120,
                )
            except requests.RequestException as e:
                msg = f"{type(e).__name__}"
                log.warning(f"   Gemini {model} 連線錯誤（第 {attempt} 次）: {msg}")
                errors.append(f"{model}: {msg}")
                if attempt == 1:
                    time.sleep(3)
                    continue
                break

            if r.status_code == 404:
                log.warning(f"   Gemini {model}: 404（此 key 不可用），換下一個")
                errors.append(f"{model}: 404")
                break

            if r.status_code in (429, 500, 502, 503, 504):
                log.warning(f"   Gemini {model}: HTTP {r.status_code}（第 {attempt} 次）")
                errors.append(f"{model}: HTTP {r.status_code}")
                if attempt == 1:
                    time.sleep(6)
                    continue
                break

            if not r.ok:
                log.warning(f"   Gemini {model}: HTTP {r.status_code} {r.text[:300]}")
                errors.append(f"{model}: HTTP {r.status_code}")
                break

            text = _gemini_extract(r.json())
            if text:
                log.info(f"   ✓ Gemini 使用模型: {model}")
                return text
            log.warning(f"   Gemini {model}: 回應內容為空（可能被安全機制擋下或被截斷）")
            errors.append(f"{model}: empty")
            break

    raise RuntimeError(f"Gemini 全部候選模型失敗: {errors}")


# ── OpenAI 相容格式（Groq / DeepSeek 共用）─────────────────────────────
def _openai_style(url: str, key: str, model: str, prompt: str) -> str:
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "max_tokens": 3000,
        },
        timeout=120,
    )
    if not r.ok:
        # 把回應內文帶出來，400 的真正原因都寫在這裡
        raise RuntimeError(f"HTTP {r.status_code} model={model}: {r.text[:500]}")
    return r.json()["choices"][0]["message"]["content"]


def _groq(prompt: str) -> str:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise ValueError("GROQ_API_KEY 未設定")
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    return _openai_style("https://api.groq.com/openai/v1/chat/completions",
                         key, model, prompt)


def _deepseek(prompt: str) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY 未設定")
    return _openai_style("https://api.deepseek.com/chat/completions",
                         key, "deepseek-chat", prompt)


# ── 主入口：自動降級鏈 ─────────────────────────────────────────────────
PROVIDERS = [
    ("Gemini",   _gemini,   "GEMINI_API_KEY"),
    ("Groq",     _groq,     "GROQ_API_KEY"),
    ("DeepSeek", _deepseek, "DEEPSEEK_API_KEY"),
]


def build_script(items: list[dict], date: str) -> str:
    if not items:
        log.warning("   無新聞素材，生成預設播報稿")
        return (
            f"各位聽眾朋友好，歡迎收聽美股科技晨報，今天是{date}。"
            "由於今日數據抓取異常，暫無詳細新聞播報，請稍後查看文字版。"
            "祝各位身體健康，闔家平安，神愛世人，耶穌愛您，我們明天見！"
        )

    prompt = _build_prompt(items, date)
    tried: list[str] = []

    for name, fn, env_key in PROVIDERS:
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
            log.info(f"   ✓ {name} 完成，{len(text)} 字")
            return text
        except Exception as ex:
            log.warning(f"   {name} 失敗: {ex}")
            time.sleep(2)

    raise RuntimeError(f"所有 AI 提供商均失敗（已嘗試: {tried or '無，請檢查 API Key 設定'}）")

"""
兩階段日更（v1.8.0）

第一階段「素材筆記」：新聞先由程式（topics.py）依關鍵詞分到細項，再把細項併成六個「筆記組」，
各交給一個 AI 挑重點、寫成固定格式的短筆記（依額度與能力分配）：
    大盤宏觀財報政策 → Gemini；AI 與半導體 → Groq；太空與下一代通訊 → Cloudflare（英文短筆記）
    資訊安全與數據中心基礎設施 → Gemini
    電力與電網 → Gemini；油氣 → Cloudflare（英文短筆記）；電信 → Groq
    某組 AI 失敗，改由另一家補做（Groq 組補 Gemini，Gemini 組補 Groq）。
第二階段「統稿」：把筆記交給提供商鏈寫成節目主體（不含開場／結尾；不設字數目標）。
build_daily 回傳 dict：body、groups、notes_text、notes_compact、groups_notes（保底稿）、notes_all（統計用）、writer。
環境變數 TWO_STAGE=0 可關閉。
"""
import logging, os, re, time

import analyzer as A
import topics as T

__version__ = "1.8.4"
log = logging.getLogger(__name__)

# feed＝每組最多送給 AI 幾則素材（依來源輪流取，關注公司優先）；pick＝AI 挑出幾則筆記
GROUPS = [
    {"key": "macro", "name": "大盤、宏觀、財報與政策", "buckets": ["C1", "C2", "C3"], "short": "大盤與總體經濟", "provider": "gemini",
     "pick": 6, "feed": 14, "max_out": 2600, "lang": "zh"},
    {"key": "ai", "name": "AI 與半導體（晶片、記憶體、製造、雲端資本支出）", "buckets": ["A1", "A2", "A3", "A4"], "short": "AI 與半導體", "provider": "groq",
     "pick": 7, "feed": 14, "max_out": 2800, "lang": "zh"},
    {"key": "space", "name": "太空與下一代通訊（衛星、6G、NGN、光通訊）", "buckets": ["A5", "A6", "A7"], "short": "太空與下一代通訊", "provider": "cloudflare",
     "pick": 3, "feed": 10, "max_out": 1400, "lang": "en"},
    {"key": "sec", "name": "資訊安全與數據中心基礎設施（網路安全、防駭、機櫃與散熱）", "buckets": ["S1", "S2", "S3"], "short": "資訊安全與數據中心設施", "provider": "gemini",
     "pick": 4, "feed": 12, "max_out": 1800, "lang": "zh"},
    {"key": "power", "name": "電力與電網（發電、輸配電設備、儲能、數據中心供電）", "buckets": ["B1", "B2", "B3", "B4"], "short": "電力與電網", "provider": "gemini",
     "pick": 6, "feed": 14, "max_out": 2600, "lang": "zh"},
    {"key": "oil", "name": "油氣與油價", "buckets": ["B5"], "short": "油氣與油價", "provider": "cloudflare",
     "pick": 3, "feed": 10, "max_out": 1600, "lang": "en"},
    {"key": "telecom", "name": "電信運營商與供應鏈", "buckets": ["B6", "B7"], "short": "電信運營商與供應鏈", "provider": "groq",
     "pick": 5, "feed": 12, "max_out": 2200, "lang": "zh"},
]
MIN_GROUPS = 3
_GAP = {"groq": 20}            # 同一家連續呼叫之間至少間隔幾秒（Groq 免費層每分鐘 token 有限）
_last_call: dict[str, float] = {}

NOTE_RULES_ZH = """你是財經資料編輯。下面是「{name}」的新聞素材。
請挑出對美股、科技產業最有影響力的 {pick} 則，依重要度由高到低排列。
輸出格式：每則一行，欄位用全形「｜」分隔，不要輸出任何其他文字：
來源｜事實｜背景｜可能的影響｜重要度（1到5的整數）
規則：
- 「來源」欄只填素材中【】內的媒體名稱，不要填公司名。
- 「事實」：一句話，只寫素材明確寫出的內容；數字、單位與專有名詞照素材抄寫，用阿拉伯數字。
- 「背景」：只寫素材中明確寫出的背景或原因；素材沒有寫就填「無」，絕對不要用你自己的知識補充。
- 「可能的影響」：只寫素材中提到的影響或市場反應；素材沒有寫就填「無」，不要自行推測。
- 不要補充素材沒有的事實、數字、日期；不要抄錄訂閱、廣告、作者介紹等與事件無關的文字；同一事件只算一則；與美股、科技、宏觀、電力能源、油氣、太空、通訊、資訊安全無關的略過。
- 金額照素材的美元寫法（保留 million／billion 英文單位）；標示「（非美元金額）」的不要引用金額。
- 公司名與人名保留英文原名，不要翻譯。
- 語氣中立克制，不預測漲跌，不給買賣建議。"""

NOTE_RULES_EN = """You are a financial news editor. Below are news items for "{name}".
Pick the {pick} items most relevant to US stocks and the technology industry, most important first.
Output one line per item, fields separated by the full-width bar "｜", and nothing else:
Source｜Fact｜Background｜Possible impact｜Importance (integer 1-5)
Rules:
- Source: the media name shown in 【】, not a company name.
- Fact: one sentence using ONLY what the item says; copy numbers and names exactly.
- Background: only if the item itself states it; otherwise write "none". Never add outside knowledge.
- Possible impact: only if the item itself states it; otherwise write "none". Never speculate.
- One line per event. Skip items unrelated to US stocks, tech, macro, power/energy, oil & gas, space, telecom or cybersecurity.
- Keep amounts exactly as written in the item (US dollars). Skip amounts marked （非美元金額）.
- Neutral tone; no price predictions; no buy/sell advice."""

SYSTEM_COMPOSE = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
下面是編輯整理好的新聞筆記，分成幾個主題。請把它們寫成廣播播報稿的主體。
結構：先用一小段（兩到四句）概述今天筆記裡的主要脈絡；再依下面的主題順序逐段說明，沒有筆記的主題整段略過：
大盤與總體經濟 → AI 與半導體 → 太空與下一代通訊 → 資訊安全與數據中心設施 → 電力與電網 → 油氣與油價 → 電信運營商與供應鏈。
轉場時用自然的口語帶出主題（例如「接下來看 AI 與半導體」），不要把主題名稱當成標題一個字一個字念出來。
每一則筆記都要提到（同一事件的多條筆記可合併成一則），不要遺漏；每則先說事實，再說筆記中的背景與可能影響，用自然的句子帶出。
筆記寫「無」或 none 的欄位就不要講，不要自己補。不要說「積極」「保守」這類讀者標籤。
絕對不要照抄筆記的欄位名稱（例如「事實」「背景」「影響為」「可能影響」），也不要把同一件事用不同說法重複講兩次。
重要度高的先講。用自然口語過渡，例如「首先來看」「接下來」「另一個值得關注的消息是」。
英文筆記請翻成台灣慣用的繁體中文；公司名與人名保留英文原名，金額保留 million／billion／trillion 英文單位，不要換算成萬、億。
筆記有多少就講多少，每則的長短由筆記內容決定，不要為了拉長而灌水。
【標記規則】每則筆記前面有編號（N1、N2…）。講完某則筆記的內容時，請在該句的句號前面加上標記【N編號】，
例如「Nasdaq 100 指數下跌 6.4%【N1】。」；一句話合併了多則筆記就寫【N2、N3】。標記會由程式移除，不會念出來，請務必標記，且標記一律放在句號之前。
""" + A._RULES_COMMON


def _group_block(items: list[dict], g: dict) -> tuple[str, int, list[dict]]:
    pool = [it for it in items if it.get("bucket") in g["buckets"]]
    by_src: dict[str, list] = {}
    for it in sorted(pool, key=lambda x: not x.get("watch")):       # 關注公司優先
        by_src.setdefault(it.get("source", ""), []).append(it)
    chosen: list[dict] = []
    # 先保證每個細項至少有 2 則（例如資安新聞量很大時，不會把機櫃散熱擠掉），不同來源優先
    for b in g["buckets"]:
        seen_src: set[str] = set()
        for it in sorted([x for x in pool if x.get("bucket") == b], key=lambda x: not x.get("watch")):
            if len([c for c in chosen if c.get("bucket") == b]) >= 2:
                break
            if it["source"] not in seen_src and it not in chosen:
                chosen.append(it)
                seen_src.add(it["source"])
    for k in list(by_src):
        by_src[k] = [x for x in by_src[k] if x not in chosen]
    i = 0
    while len(chosen) < g["feed"] and any(len(v) > i for v in by_src.values()):   # 依來源輪流取，避免被單一來源佔滿
        for v in by_src.values():
            if len(v) > i and len(chosen) < g["feed"]:
                chosen.append(v[i])
        i += 1
    lines, cur = [], None
    for it in sorted(chosen, key=lambda x: x.get("source", "")):
        if it["source"] != cur:
            cur = it["source"]
            lines.append(f"\n【{cur}】")
        t, sm = A.ai_view(it)
        lines.append(f"- {t}")
        if sm:
            lines.append(f"  {sm[:A.SUMMARY_CHARS]}")
    return "\n".join(lines), len(chosen), chosen


def _tok(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9\.\-]{2,}|\d[\d,\.]*", s)}


def _fix_source(row: dict, used: list[dict], default_bucket: str) -> dict:
    """AI 常把公司名填進來源欄；用事實與標題的字詞重疊，對回真正的來源媒體與細項。"""
    ft, best, bs = _tok(row["fact"]), None, 0
    for it in used:
        sc = len(ft & _tok(it["title"] + " " + (it.get("summary") or "")[:200]))
        if sc > bs:
            best, bs = it, sc
    names = {it["source"] for it in used}
    ok = row["source"] in names or any(row["source"].startswith(n) or n.startswith(row["source"]) for n in names)
    if not ok:
        row["source"] = best["source"] if best and bs else ""
    row["bucket"] = best["bucket"] if best and bs else default_bucket
    return row


def _parse_notes(text: str, pick: int, used: list[dict] | None = None, default_bucket: str = "C1") -> list[dict]:
    rows = []
    for line in text.splitlines():
        line = re.sub(r"^[\s\-\*•\d\.\)、]+", "", line.strip())
        parts = [p.strip() for p in re.split(r"[｜|]", line)]
        if len(parts) < 5 or len(parts[1]) < 8:
            continue
        m = re.search(r"[1-5]", parts[-1])
        none = lambda x: x.strip(" 。.").lower() in ("無", "无", "none", "n/a", "")
        if parts[3] and parts[1][:25] in parts[3]:      # 「影響」只是把事實再抄一次 → 視為沒有
            parts[3] = "無"
        row = {"source": parts[0][:40], "fact": parts[1],
               "background": "無" if none(parts[2]) else parts[2],
               "impact": "無" if none(parts[3]) else parts[3],
               "score": int(m.group()) if m else 3, "bucket": default_bucket}
        rows.append(_fix_source(row, used or [], default_bucket))
    rows.sort(key=lambda r: -r["score"])
    return rows[:pick]


def _call(provider: str, prompt: str, max_out: int) -> str:
    name, fn, env_key = A._REGISTRY[provider]
    if provider == "cloudflare":
        if not (os.environ.get("CLOUDFLARE_API_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID")):
            raise ValueError("Cloudflare 未設定")
    elif not os.environ.get(env_key):
        raise ValueError(f"{env_key} 未設定")
    gap = _GAP.get(provider, 0)
    wait = gap - (time.time() - _last_call.get(provider, 0))
    if wait > 0:
        log.info(f"   等 {wait:.0f} 秒再呼叫 {provider}（避免超過每分鐘額度）")
        time.sleep(wait)
    try:
        return fn(prompt, max_out)
    finally:
        _last_call[provider] = time.time()


def _notes_for_group(items: list[dict], g: dict, trace: list) -> tuple[list[dict], str, str]:
    """回傳 (筆記, 實際提供商, 模型名)。"""
    block, n, used = _group_block(items, g)
    if n == 0:
        log.warning(f"   [{g['name']}] 沒有素材，略過")
        trace.append({"group": g["name"], "provider": "-", "status": "無素材", "notes": []})
        return [], "", ""
    rules = (NOTE_RULES_EN if g["lang"] == "en" else NOTE_RULES_ZH).format(name=g["name"], pick=g["pick"])
    prompt = f"{rules}\n\n素材（共 {n} 則）：\n{block}"
    order = [g["provider"], "gemini" if g["provider"] != "gemini" else "groq"]
    want = min(max(2, g["pick"] // 2), max(1, n))       # 素材本來就少時，不為了湊數去請下一家
    best: list[dict] = []
    best_prov = best_model = ""
    for prov in order:
        t0 = time.time()
        try:
            log.info(f"   [{g['name']}] 交給 {prov}（素材 {n} 則，提示詞約 {len(prompt)} 字，輸出上限 {g['max_out']}）")
            text = _call(prov, prompt, g["max_out"])
            notes = _parse_notes(text, g["pick"], used, g["buckets"][0])
            if not notes:
                raise RuntimeError("解析不到任何筆記")
            model = A.LAST_MODEL.get(prov, "")
            log.info(f"   ✓ [{g['name']}] {prov} 產出 {len(notes)} 則筆記（{time.time() - t0:.0f}s）")
            trace.append({"group": g["name"], "provider": prov, "model": model, "status": "成功",
                          "seconds": round(time.time() - t0), "notes": notes})
            if len(notes) > len(best):
                best, best_prov, best_model = notes, prov, model
            if len(best) >= want:
                return best, best_prov, best_model
            log.warning(f"   [{g['name']}] 只有 {len(best)} 則（想要至少 {want}），請下一家補做")
        except Exception as ex:
            log.warning(f"   ✗ [{g['name']}] {prov} 失敗：{str(ex)[:200]}")
            trace.append({"group": g["name"], "provider": prov, "status": f"失敗：{str(ex)[:120]}", "notes": []})
    return best, best_prov, best_model


def _notes_text(groups_notes: list[tuple[str, list[dict]]], compact: bool = False) -> str:
    out = []
    for name, notes in groups_notes:
        out.append(f"\n【{name}】")
        for i, r in enumerate(notes, 1):
            src = f"[{r['source']}] " if r.get("source") else ""
            if compact:      # 審稿用：去掉重要度與欄位前綴，省 token
                bits = [r["fact"]] + [x for x in (r["background"], r["impact"]) if x and x != "無"]
                out.append(f"N{r.get('id', i)}. {src}" + "；".join(bits))
                continue
            out.append(f"N{r.get('id', i)}. {src}事實：{r['fact']}　背景：{r['background']}　"
                       f"可能影響：{r['impact']}　（重要度 {r['score']}）")
    return "\n".join(out)


def build_daily(items: list[dict], date: str, trace: list | None = None) -> dict:
    """回傳 dict：body, groups(署名用), notes_text, groups_notes(保底稿用), writer"""
    trace = trace if trace is not None else []
    got: list[tuple[str, list[dict]]] = []
    info: list[dict] = []
    safe_src: list[tuple[str, list[dict], str]] = []
    for g in GROUPS:
        notes, prov, model = _notes_for_group(items, g, trace)
        if notes:
            got.append((g["short"], notes))
            info.append({"name": g["short"], "provider": prov, "model": model, "planned": g["provider"]})
            safe_src.append((g["short"], notes, g["lang"]))
    if len(got) < MIN_GROUPS:
        raise RuntimeError(f"只有 {len(got)} 組筆記（至少需要 {MIN_GROUPS}），退回一次寫完的流程")

    nid = 0
    for _, ns in got:                       # 全域編號 N1…Nk，統稿時用來標記、成稿後用來統計
        for r in ns:
            nid += 1
            r["id"] = nid
    ntext = _notes_text(got)
    prompt = SYSTEM_COMPOSE + "\n\n以下是今天各組整理好的新聞筆記（重要度 5 最高）：\n" + ntext
    log.info(f"   統稿：{sum(len(n) for _, n in got)} 則筆記，提示詞約 {len(prompt)} 字")
    trace.append({"group": "統稿", "provider": "chain", "status": "進行中", "notes": [], "notes_text": ntext})
    try:
        body = A._run_chain(prompt)
        w = A.LAST_WINNER["provider"]
        trace[-1]["status"] = f"完成（{len(body)} 字，{w}）"
        writer = {"provider": w, "model": A.LAST_MODEL.get(w, "")}
    except Exception as ex:             # 統稿全部失敗：筆記仍保留，交給 episode 用保底稿
        log.warning(f"   統稿失敗：{str(ex)[:200]}")
        trace[-1]["status"] = "統稿失敗"
        body, writer = "", None
    return {"body": body, "groups": info, "notes_text": ntext, "notes_compact": _notes_text(got, compact=True),
            "groups_notes": safe_src, "fed_items": [it for g in GROUPS for it in _group_block(items, g)[2]], "notes_all": [r for _, ns in got for r in ns], "writer": writer}

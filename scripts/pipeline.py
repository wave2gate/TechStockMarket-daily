"""
兩階段日更（v1.6.0）

第一階段「素材筆記」：依額度與能力把來源分三組，各交給一個 AI 挑重點、寫成固定格式的短筆記。
    大盤、宏觀與財報 → Gemini；科技、AI 與通訊網路 → Groq；能源與儲能 → Cloudflare（只做英文短筆記）
    某組 AI 失敗，改由 Gemini 補做；Gemini 也失敗就略過那組。
第二階段「統稿」：把筆記交給提供商鏈，寫成節目主體（不含開場／結尾；不設字數目標）。
build_daily 回傳 (主體, 各組實際使用情形, 筆記文字, 筆記資料)，供 guard / frame 使用。
任何環節整體失敗 → 丟例外，由 episode.py 退回舊流程或保底稿。
環境變數 TWO_STAGE=0 可關閉。
"""
import logging, os, re, time

import analyzer as A

__version__ = "1.7.0"
log = logging.getLogger(__name__)

GROUPS = [
    {"key": "macro", "name": "大盤、宏觀與財報", "provider": "gemini", "pick": 10,
     "per_source": 5, "max_out": 3200, "lang": "zh",
     "sources": ["Federal Reserve", "BLS", "WSJ Markets", "CNBC", "Bloomberg Markets", "Yahoo Finance",
                 "MarketWatch", "Investing.com", "Nasdaq", "Financial Times", "Benzinga", "Investopedia",
                 "Seeking Alpha"]},
    {"key": "tech", "name": "科技、AI 與通訊網路", "provider": "groq", "pick": 8,
     "per_source": 5, "max_out": 2200, "lang": "zh",
     "sources": ["TechCrunch", "RCR Wireless", "Telecoms.com", "FierceWireless", "Light Reading",
                 "SDxCentral", "Mobile World Live"]},
    {"key": "energy", "name": "能源與儲能", "provider": "cloudflare", "pick": 5,
     "per_source": 6, "max_out": 1400, "lang": "en",
     "sources": ["Energy Storage News", "Bloomberg NEF", "Utility Dive", "Electrek"]},
]
MIN_GROUPS = 2

NOTE_RULES_ZH = """你是財經資料編輯。下面是「{name}」的新聞素材。
請挑出對美股、科技產業最有影響力的 {pick} 則，依重要度由高到低排列。
輸出格式：每則一行，欄位用全形「｜」分隔，不要輸出任何其他文字：
來源｜事實｜背景｜可能的影響｜重要度（1到5的整數）
規則：
- 「來源」欄只填素材中【】內的媒體名稱，不要填公司名。
- 「事實」：一句話，只寫素材明確寫出的內容；數字、單位與專有名詞照素材抄寫，用阿拉伯數字。
- 「背景」：只寫素材中明確寫出的背景或原因；素材沒有寫就填「無」，絕對不要用你自己的知識補充。
- 「可能的影響」：只寫素材中提到的影響或市場反應；素材沒有寫就填「無」，不要自行推測。
- 不要補充素材沒有的事實、數字、日期；同一事件只算一則；與美股、科技、宏觀、通訊、儲能無關的略過。
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
- One line per event. Skip items unrelated to US stocks, tech, macro, telecom or energy storage.
- Keep amounts exactly as written in the item (US dollars). Skip amounts marked （非美元金額）.
- Neutral tone; no price predictions; no buy/sell advice."""

SYSTEM_COMPOSE = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
下面是編輯整理好的新聞筆記。請把它們寫成廣播播報稿的主體。
結構：先用一小段（兩到四句）概述今天筆記裡的主要脈絡；再依主題逐則說明——
美股與科技、宏觀與利率、通訊與網路、能源與儲能；某一類沒有筆記就整段略過。
每則先說事實，再說筆記中的背景與可能影響，用自然的句子帶出；筆記寫「無」或 none 的欄位就不要講，不要自己補。
絕對不要照抄筆記的欄位名稱（例如「事實」「背景」「影響為」「可能影響」），也不要把同一件事用不同說法重複講兩次。
重要度高的先講，同一事件的多條筆記合併。用自然口語過渡，例如「首先來看」「接下來」「另一個值得關注的消息是」。
英文筆記請翻成台灣慣用的繁體中文；公司名與人名保留英文原名，金額保留 million／billion／trillion 英文單位，不要換算成萬、億。
筆記有多少就講多少，每則的長短由筆記內容決定，不要為了拉長而灌水。
""" + A._RULES_COMMON


def _group_block(items: list[dict], g: dict) -> tuple[str, int, list[dict]]:
    lines, n, used = [], 0, []
    for src in g["sources"]:
        its = [it for it in items if it.get("source", "").startswith(src)][: g["per_source"]]
        if not its:
            continue
        lines.append(f"\n【{src}】")
        for it in its:
            n += 1
            used.append(it)
            t, s = A.ai_view(it)
            lines.append(f"- {t}")
            if s:
                lines.append(f"  {s[:A.SUMMARY_CHARS]}")
    return "\n".join(lines), n, used


def _tok(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9\.\-]{2,}|\d[\d,\.]*", s)}


def _fix_source(row: dict, used: list[dict]) -> dict:
    """AI 常把公司名填進來源欄；用事實與標題的字詞重疊，對回真正的來源媒體。"""
    names = {it["source"] for it in used}
    if row["source"] in names or any(row["source"].startswith(n) or n.startswith(row["source"]) for n in names):
        return row
    ft, best, bs = _tok(row["fact"]), None, 0
    for it in used:
        sc = len(ft & _tok(it["title"] + " " + (it.get("summary") or "")[:200]))
        if sc > bs:
            best, bs = it, sc
    row["source"] = best["source"] if best and bs else ""
    return row


def _parse_notes(text: str, pick: int, used: list[dict] | None = None) -> list[dict]:
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
               "score": int(m.group()) if m else 3}
        rows.append(_fix_source(row, used) if used else row)
    rows.sort(key=lambda r: -r["score"])
    return rows[:pick]


def _call(provider: str, prompt: str, max_out: int) -> str:
    name, fn, env_key = A._REGISTRY[provider]
    if provider == "cloudflare":
        if not (os.environ.get("CLOUDFLARE_API_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID")):
            raise ValueError("Cloudflare 未設定")
    elif not os.environ.get(env_key):
        raise ValueError(f"{env_key} 未設定")
    return fn(prompt, max_out)


def _notes_for_group(items: list[dict], g: dict, trace: list) -> tuple[list[dict], str, str]:
    """回傳 (筆記, 實際提供商, 模型名)。"""
    block, n, used = _group_block(items, g)
    if n == 0:
        log.warning(f"   [{g['name']}] 沒有素材，略過")
        trace.append({"group": g["name"], "provider": "-", "status": "無素材", "notes": []})
        return [], "", ""
    rules = (NOTE_RULES_EN if g["lang"] == "en" else NOTE_RULES_ZH).format(name=g["name"], pick=g["pick"])
    prompt = f"{rules}\n\n素材（共 {n} 則）：\n{block}"
    order = [g["provider"]] + (["gemini"] if g["provider"] != "gemini" else [])
    want = max(2, g["pick"] // 2)
    best: list[dict] = []
    best_prov = best_model = ""
    for prov in order:
        t0 = time.time()
        try:
            log.info(f"   [{g['name']}] 交給 {prov}（素材 {n} 則，提示詞約 {len(prompt)} 字，輸出上限 {g['max_out']}）")
            text = _call(prov, prompt, g["max_out"])
            notes = _parse_notes(text, g["pick"], used)
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


def _notes_text(groups_notes: list[tuple[str, list[dict]]]) -> str:
    out = []
    for name, notes in groups_notes:
        out.append(f"\n【{name}】")
        for i, r in enumerate(notes, 1):
            src = f"[{r['source']}] " if r.get("source") else ""
            out.append(f"{i}. {src}事實：{r['fact']}　背景：{r['background']}　"
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
            got.append((g["name"], notes))
            info.append({"name": g["name"], "provider": prov, "model": model, "planned": g["provider"]})
            safe_src.append((g["name"], notes, g["lang"]))
    if len(got) < MIN_GROUPS:
        raise RuntimeError(f"只有 {len(got)} 組筆記（至少需要 {MIN_GROUPS}），退回一次寫完的流程")

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
    return {"body": body, "groups": info, "notes_text": ntext, "groups_notes": safe_src, "writer": writer}

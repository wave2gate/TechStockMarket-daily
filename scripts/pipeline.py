"""
兩階段日更播報稿（v1.5.0）

第一階段「素材筆記」：依額度與能力把來源分成三組，各交給一個 AI 挑出最重要的幾則，輸出固定格式的短筆記。
    大盤、宏觀與財報 → Gemini（額度大、中文穩）
    科技、AI 與通訊網路 → Groq（結構清楚、速度快；輸入與輸出都壓小，不碰免費層的每分鐘上限）
    能源與儲能        → Cloudflare Workers AI（只做英文短筆記，不寫中文成稿、不處理長文）
    任何一組的 AI 失敗，改由 Gemini 補做；Gemini 也失敗就略過那一組。
第二階段「統稿」：把所有筆記交給提供商鏈（預設 Gemini 優先）寫成 2800–3300 字的完整播報稿。
任何環節整體失敗（筆記少於兩組、統稿太短…）→ 丟出例外，由 main.py 退回舊的「一次寫完」流程。
環境變數 TWO_STAGE=0 可關閉；PIPELINE_TRACE 指向的 list 會收到各階段紀錄（試跑用）。
"""
import logging, os, re, time

import analyzer as A

__version__ = "1.5.0"
log = logging.getLogger(__name__)

GROUPS = [
    {"key": "macro", "name": "大盤、宏觀與財報", "provider": "gemini", "pick": 5,
     "per_source": 5, "max_out": 1800, "lang": "zh",
     "sources": ["WSJ Markets", "CNBC", "Bloomberg Markets", "Yahoo Finance", "MarketWatch",
                 "Investing.com", "Financial Times", "Benzinga", "Investopedia", "Seeking Alpha"]},
    {"key": "tech", "name": "科技、AI 與通訊網路", "provider": "groq", "pick": 4,
     "per_source": 4, "max_out": 1500, "lang": "zh",
     "sources": ["TechCrunch", "RCR Wireless", "Telecoms.com", "FierceWireless",
                 "Light Reading", "SDxCentral"]},
    {"key": "energy", "name": "能源與儲能", "provider": "cloudflare", "pick": 3,
     "per_source": 6, "max_out": 1200, "lang": "en",
     "sources": ["Energy Storage News", "Bloomberg NEF"]},
]
MIN_GROUPS = 2          # 至少要有幾組筆記才進統稿

NOTE_RULES_ZH = """你是財經資料編輯。下面是「{name}」的新聞素材。
請挑出對美股、科技產業最有影響力的 {pick} 則，依重要度由高到低排列。
輸出格式：每則一行，欄位用全形「｜」分隔，不要輸出任何其他文字：
來源｜事實（一句，數字與專有名詞照原文）｜背景（一句）｜對科技股可能的影響（一句，只描述可能性）｜重要度（1到5的整數）
規則：
- 只用素材裡的資訊，不可補充；同一事件只算一則；與美股、科技、宏觀、通訊、儲能無關的略過。
- 金額一律只保留美元；其他貨幣的金額不要換算，也不要寫出那個金額。
- 語氣中立克制，用「可能」「值得留意」，不預測漲跌，不給買賣建議。"""

NOTE_RULES_EN = """You are a financial news editor. Below are news items for "{name}".
Pick the {pick} items most relevant to US stocks and the technology industry, most important first.
Output one line per item, fields separated by the full-width bar "｜", and nothing else:
Source｜Fact (one sentence, copy numbers and names exactly)｜Background (one sentence)｜Possible impact on tech stocks (one sentence, describe possibilities only)｜Importance (integer 1-5)
Rules:
- Use only information in the items; never add facts. One line per event. Skip items unrelated to US stocks, tech, macro, telecom or energy storage.
- Keep amounts in US dollars only. Do not convert or quote amounts in other currencies.
- Neutral tone: say "may" or "could"; no price predictions; no buy/sell advice."""

SYSTEM_COMPOSE = """你是一位專業的台灣財經播客主持人，聲音沉穩、邏輯清晰。
請把下面各組編輯整理好的新聞筆記，寫成一集約 10 分鐘的廣播播報稿。

格式規定：
1. 開場白：「各位聽眾朋友好，歡迎收聽美股科技收盤簡報，今天是 {date}，我是您的主持人。」
2. 綜述：開場後先用一小段（四到六句）說出今天市場的整體氣氛與兩三條主軸。
3. 主體依序分四段：美股與科技重點、宏觀與利率、通訊與網路、能源與儲能。
   每則新聞用不超過五句話：發生了什麼、背景、可能的影響。重要度高的多著墨，同一事件的多條筆記要合併。
   某一段沒有筆記就整段略過，不要硬湊。
   用自然口語過渡，禁止「第一則」「第二則」等數字列表；
   常用過渡語：「首先來看」「接下來」「另一個值得關注的消息是」「在科技板塊方面」「我們再來看宏觀面」「說到能源與儲能」。
   英文筆記請翻成台灣慣用的繁體中文，公司名可保留原文。
4. 風險提醒：「市場波動來自技術面、消息面、機構資金等多重因素，請勿單憑新聞買賣股票，投資需謹慎。」
5. 身心健康提醒：一到兩句，提醒聽眾無論走勢如何，都要維持規律作息與運動，長期心態比短線漲跌更重要；
   不要出現「逢低」「加碼」「定投某標的」等操作字眼。
6. 最後祝福：「祝各位身體健康、投資順利，闔家平安，神愛世人，耶穌愛您，我們明天見！」
7. 字數 2800–3300 字。筆記不足以撐到這個長度時，寧可寫短，也不可補充筆記沒有的事實或數字。
""" + A._RULES_COMMON


def _group_block(items: list[dict], g: dict) -> tuple[str, int]:
    lines, n = [], 0
    for src in g["sources"]:
        its = [it for it in items if it.get("source", "").startswith(src)][: g["per_source"]]
        if not its:
            continue
        lines.append(f"\n【{src}】")
        for it in its:
            n += 1
            lines.append(f"- {it['title']}")
            if it.get("summary"):
                lines.append(f"  {it['summary'][:A.SUMMARY_CHARS]}")
    return "\n".join(lines), n


def _parse_notes(text: str, pick: int) -> list[dict]:
    rows = []
    for line in text.splitlines():
        line = re.sub(r"^[\s\-\*•\d\.\)、]+", "", line.strip())
        parts = [p.strip() for p in re.split(r"[｜|]", line)]
        if len(parts) < 5 or len(parts[1]) < 8:
            continue
        m = re.search(r"[1-5]", parts[-1])
        rows.append({"source": parts[0][:40], "fact": parts[1], "background": parts[2],
                     "impact": parts[3], "score": int(m.group()) if m else 3})
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


def _notes_for_group(items: list[dict], g: dict, trace: list) -> list[dict]:
    block, n = _group_block(items, g)
    if n == 0:
        log.warning(f"   [{g['name']}] 沒有素材，略過")
        trace.append({"group": g["name"], "provider": "-", "status": "無素材", "notes": []})
        return []
    rules = (NOTE_RULES_EN if g["lang"] == "en" else NOTE_RULES_ZH).format(name=g["name"], pick=g["pick"])
    prompt = f"{rules}\n\n素材（共 {n} 則）：\n{block}"
    order = [g["provider"]] + (["gemini"] if g["provider"] != "gemini" else [])
    for prov in order:
        t0 = time.time()
        try:
            log.info(f"   [{g['name']}] 交給 {prov}（素材 {n} 則，提示詞約 {len(prompt)} 字，輸出上限 {g['max_out']}）")
            text = _call(prov, prompt, g["max_out"])
            notes = _parse_notes(text, g["pick"])
            if not notes:
                raise RuntimeError("解析不到任何筆記")
            log.info(f"   ✓ [{g['name']}] {prov} 產出 {len(notes)} 則筆記（{time.time() - t0:.0f}s）")
            trace.append({"group": g["name"], "provider": prov, "status": "成功",
                          "seconds": round(time.time() - t0), "notes": notes})
            return notes
        except Exception as ex:
            log.warning(f"   ✗ [{g['name']}] {prov} 失敗：{str(ex)[:200]}")
            trace.append({"group": g["name"], "provider": prov, "status": f"失敗：{str(ex)[:120]}", "notes": []})
    return []


def _notes_text(groups_notes: list[tuple[str, list[dict]]]) -> str:
    out = []
    for name, notes in groups_notes:
        out.append(f"\n【{name}】")
        for i, r in enumerate(notes, 1):
            out.append(f"{i}. [{r['source']}] 事實：{r['fact']}　背景：{r['background']}　"
                       f"可能影響：{r['impact']}　（重要度 {r['score']}）")
    return "\n".join(out)


def build_daily(items: list[dict], date: str, trace: list | None = None) -> str:
    trace = trace if trace is not None else []
    got: list[tuple[str, list[dict]]] = []
    for g in GROUPS:
        notes = _notes_for_group(items, g, trace)
        if notes:
            got.append((g["name"], notes))
    if len(got) < MIN_GROUPS:
        raise RuntimeError(f"只有 {len(got)} 組筆記（至少需要 {MIN_GROUPS}），退回一次寫完的流程")

    prompt = (SYSTEM_COMPOSE.replace("{date}", date)
              + "\n\n以下是今天各組整理好的新聞筆記（重要度 5 最高）：\n" + _notes_text(got))
    log.info(f"   統稿：{sum(len(n) for _, n in got)} 則筆記，提示詞約 {len(prompt)} 字")
    trace.append({"group": "統稿", "provider": "chain", "status": "進行中", "notes": [],
                  "notes_text": _notes_text(got)})
    text = A._run_chain(prompt)
    trace[-1]["status"] = f"完成（{len(text)} 字）"
    return text

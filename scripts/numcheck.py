"""
數字處理（v1.7.0）：兩件事都由程式做，不交給 AI
  1. normalize_amounts()  送進 AI 前，美元金額改成「115 billion 美元」（保留英文單位，不換算成萬／億，避免換算出錯）；
                          非美元金額一律改成「（非美元金額）」，不讓 AI 看到也不用換算。
  2. check_sentences()    成稿後，逐句抓出金額、百分比與大數字，必須能在素材裡找到對應的值，找不到就標記。
v1.5.1 試跑曾出現「$115 billion 念成一百十五億」「$984 million 念成九千八百萬」，這支就是為了擋這類錯誤。
"""
import re

__version__ = "1.7.0"

_MAG_EN = {"trillion": 1e12, "tn": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6, "thousand": 1e3}
_MAG_SHORT = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
_MAG_ZH = {"兆": 1e12, "億": 1e8, "萬": 1e4, "千": 1e3}
_TOL = 0.005                       # 相對誤差 0.5% 內視為相同（容許「約」與四捨五入）
_COMMON = {100, 400, 401, 500, 600, 1000, 2000}      # 指數與常見代號（Nasdaq-100、S&P 500、Russell 2000…）
_SKIP_AFTER = set("年月日號點時分秒週天則家次個位名檔季檔筆項種")


# ───────────────────────── 1. 送進 AI 前的金額處理 ─────────────────────────
def _fmt_zh(v: float) -> str:
    if v >= 1e12:
        return f"{v / 1e12:.6g}兆"
    if v >= 1e8:
        return f"{v / 1e8:.6g}億"
    if v >= 1e4:
        return f"{v / 1e4:.6g}萬"
    return f"{v:.10g}"


_NUM = r"[\d,]+(?:\.\d+)?"
_MAGW = r"(?:trillion|billion|million|thousand|tn|bn|mn)"
_NON_USD = [
    re.compile(rf"(?<![A-Za-z])(?:A|C|HK|NT|S|R|NZ)\$\s?{_NUM}(?:\s?{_MAGW}\b|[TBMK]\b)?"),
    re.compile(rf"[€£¥₩₹]\s?{_NUM}(?:\s?{_MAGW}\b|[TBMK]\b)?"),
    re.compile(rf"\b(?:RMB|CNY|JPY|EUR|GBP|KRW|INR)\s?{_NUM}(?:\s?{_MAGW}\b)?", re.I),
    re.compile(rf"\b{_NUM}(?:\s?{_MAGW})?\s?(?:yuan|yen|euros?|pounds|won|rupees|RMB)\b", re.I),
]
_USD = re.compile(rf"(?<![A-Za-z])(?:US)?\$\s?({_NUM})(?:\s?({_MAGW})\b|([TBMK])\b)?")


def normalize_amounts(text: str) -> str:
    if not text:
        return text
    for pat in _NON_USD:
        text = pat.sub("（非美元金額）", text)

    def usd(m: re.Match) -> str:
        word = ""
        if m.group(2):
            word = {"tn": "trillion", "bn": "billion", "mn": "million"}.get(m.group(2).lower(), m.group(2).lower())
        elif m.group(3):
            word = {"T": "trillion", "B": "billion", "M": "million", "K": "thousand"}[m.group(3)]
        return f"{m.group(1)} {word} 美元" if word else f"{m.group(1)} 美元"

    return _USD.sub(usd, text)


def prepare_items(items: list[dict]) -> list[dict]:
    """替每則素材加上 ai_title / ai_summary（已換好單位）；原文欄位不動，全文頁的來源清單仍用原標題。"""
    for it in items:
        it["ai_title"] = normalize_amounts(it.get("title", ""))
        it["ai_summary"] = normalize_amounts(it.get("summary", ""))
    return items


# ───────────────────────── 2. 成稿數字檢查 ─────────────────────────
_CN_DIG = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_CHARS = "零〇一二兩三四五六七八九十百千萬億兆點"


def cn2num(s: str) -> float | None:
    """中文數字轉數值；無法解析回傳 None。『二零二六』這種逐位唸法當作年份處理（回傳整數）。"""
    if not s:
        return None
    mag = 1.0
    if "點" in s:
        ip, fp = s.split("點", 1)
        while fp and fp[-1] in "萬億兆":
            mag *= {"萬": 1e4, "億": 1e8, "兆": 1e12}[fp[-1]]
            fp = fp[:-1]
        if not ip or any(c not in _CN_DIG for c in fp) or not fp:
            return None
        base = cn2num(ip)
        if base is None:
            return None
        frac = float("0." + "".join(str(_CN_DIG[c]) for c in fp))
        return (base + frac) * mag
    if all(c in _CN_DIG for c in s):
        return float(int("".join(str(_CN_DIG[c]) for c in s))) if len(s) > 1 else float(_CN_DIG[s])
    total = section = number = 0.0
    for ch in s:
        if ch in _CN_DIG:
            number = _CN_DIG[ch]
        elif ch in "十百千":
            u = {"十": 10, "百": 100, "千": 1000}[ch]
            if number == 0 and (ch == "十" or (ch in "百千" and section == 0 and total == 0)):
                number = 1                                   # 『十五』『百六十』省略了開頭的一
            section += number * u
            number = 0
        elif ch in "萬億兆":
            m = {"萬": 1e4, "億": 1e8, "兆": 1e12}[ch]
            section += number
            number = 0
            if section == 0:
                section = 1
            total += section * m
            section = 0
        else:
            return None
    return total + section + number


_PCT_CN = re.compile(rf"百分之([{_CN_CHARS}]+|\d+(?:\.\d+)?)")
_ARABIC = re.compile(rf"(?<![A-Za-z\d.,])(\d[\d,]*(?:\.\d+)?)\s?(%|％|兆|億|萬|千|{_MAGW}\b)?")
_COMPOSITE = re.compile(r"(?<![A-Za-z\d.,])(?:\d[\d,]*(?:\.\d+)?[兆億萬]\s?){2,3}")
_CN_NUM = re.compile(rf"[{_CN_CHARS}]+(?:\s?(%|％))?")


def _tokens(text: str) -> list[dict]:
    """回傳 [{raw,val,kind,start,end,unit}]。kind: pct（百分比）或 num。"""
    toks, mask = [], [False] * len(text)
    for m in _PCT_CN.finditer(text):
        g = m.group(1)
        v = float(g) if re.fullmatch(r"\d+(?:\.\d+)?", g) else cn2num(g)
        if v is not None:
            toks.append({"raw": m.group(0), "val": v, "kind": "pct", "start": m.start(), "end": m.end(), "unit": True})
        for i in range(m.start(), m.end()):
            mask[i] = True
    for m in _COMPOSITE.finditer(text):            # 『4億9000萬』『1億3700萬』：合起來才是一個數字
        parts = re.findall(r"(\d[\d,]*(?:\.\d+)?)([兆億萬])", m.group(0))
        v = sum(float(n.replace(",", "")) * {"兆": 1e12, "億": 1e8, "萬": 1e4}[u] for n, u in parts)
        toks.append({"raw": m.group(0).strip(), "val": v, "kind": "num", "start": m.start(), "end": m.end(), "unit": True})
        for i in range(m.start(), m.end()):
            mask[i] = True
    for m in _ARABIC.finditer(text):
        if any(mask[m.start():m.end()]):
            continue
        v = float(m.group(1).replace(",", ""))
        u = m.group(2)
        kind = "num"
        if u in ("%", "％"):
            kind = "pct"
        elif u:
            v *= _MAG_ZH.get(u, _MAG_EN.get(u.lower(), 1))
        toks.append({"raw": m.group(0).strip(), "val": v, "kind": kind, "start": m.start(), "end": m.end(),
                     "unit": bool(u), "base": float(m.group(1).replace(",", ""))})
        for i in range(m.start(), m.end()):
            mask[i] = True
    for m in _CN_NUM.finditer(text):
        if any(mask[m.start():m.end()]):
            continue
        s = m.group(0)
        pct = bool(m.group(1))
        if m.start() > 0 and text[m.start() - 1] in "數幾多":      # 『數十億』『幾百萬』是概數，不檢查
            continue
        core = re.sub(r"\s?(%|％)$", "", s)
        if core and all(c in "百千萬億兆" for c in core):      # 『百萬』『千萬』（如『數百萬』）不精確，不檢查
            continue
        v = cn2num(core)
        if v is None:
            continue
        has_unit = any(c in core for c in "萬億兆")
        toks.append({"raw": s.strip(), "val": v, "kind": "pct" if pct else "num",
                     "start": m.start(), "end": m.end(), "unit": has_unit})
    toks.sort(key=lambda t: t["start"])
    return toks


def allowed_values(*texts: str) -> set[float]:
    """素材裡出現過的所有數值（含換算後的值）。"""
    vals: set[float] = set()
    for text in texts:
        for t in _tokens(text or ""):
            vals.add(t["val"])
            if "base" in t:
                vals.add(t["base"])
    return vals


def _match(v: float, allowed: set[float]) -> bool:
    for a in allowed:
        if a == v or (a and abs(v - a) / abs(a) <= _TOL):
            return True
    return False


def check_text(text: str, allowed: set[float]) -> list[str]:
    """回傳這段文字裡『在素材找不到對應值』的數字原文。"""
    bad = []
    for t in _tokens(text):
        v = t["val"]
        nxt = text[t["end"]:t["end"] + 1]
        if t["kind"] != "pct":
            if nxt and nxt in _SKIP_AFTER and not t["unit"]:
                continue                                   # 日期、時間、數量詞
            if float(v).is_integer() and 1900 <= v <= 2100 and not t["unit"]:
                continue                                   # 年份
            if v < 100 and not t["unit"]:
                continue                                   # 小數字太常見，交給 AI 審稿
            if v in _COMMON:
                continue
        if not _match(v, allowed):
            bad.append(t["raw"])
    return bad

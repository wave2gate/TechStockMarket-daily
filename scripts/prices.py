"""
價格模組（v1.10.0）：用程式算價格事實，全部不經 AI。
  ① 觀察列表每檔：今日收盤是否為「滾動 21 個交易日」的最高或最低收盤價
  ② 各分類指數型基金（ETF）近 21 個交易日漲跌
v1.10.0 起日更集數會把它變成一小段固定句型口播（spoken）；R2 文稿頁／試跑顯示完整表格（render_md）。
資料來源依序：Yahoo 圖表介面（調整後收盤價，避免拆股造成假新低）→ Stooq 日線 CSV。
安全設計：先用 SPY 試連，兩個來源都失敗就整個略過（不等 60 檔逐一逾時）；SPY 最新日期不等於交易日（資料過期或還沒收盤）也整段略過。
User-Agent 只用誠實的程式名稱，不偽裝瀏覽器。
"""
import csv, io, json, logging, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from watchlist import WATCH, LEAD

__version__ = "1.10.0"
log = logging.getLogger(__name__)
WINDOW = 21
_UA = {"User-Agent": "TechStockMarket-daily/1.10 (podcast research script)"}
_ET = ZoneInfo("America/New_York")
_CACHE: dict[str, dict] = {}


def _get(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _yahoo(sym: str) -> tuple[list[float], str]:
    d = json.loads(_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d"))
    res = d["chart"]["result"][0]
    ts = res.get("timestamp") or []
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    closes = adj or res["indicators"]["quote"][0]["close"]
    pairs = [(t, c) for t, c in zip(ts, closes) if c is not None]
    return [c for _, c in pairs], datetime.fromtimestamp(pairs[-1][0], _ET).date().isoformat()


def _stooq(sym: str) -> tuple[list[float], str]:
    rows = [r for r in csv.DictReader(io.StringIO(_get(f"https://stooq.com/q/d/l/?s={sym.lower()}.us&i=d")))
            if r.get("Close") not in (None, "", "null")]
    return [float(r["Close"]) for r in rows], rows[-1]["Date"]


def closes_for(sym: str) -> tuple[list[float], str, str]:
    """回傳 (收盤價由舊到新, 最新一筆日期, 來源或錯誤)。"""
    err = ""
    for name, fn in (("yahoo", _yahoo), ("stooq", _stooq)):
        try:
            c, last = fn(sym)
            if len(c) >= WINDOW:
                return c, last, name
            err = f"{name}:資料不足({len(c)})"
        except Exception as e:
            err = f"{name}:{type(e).__name__}"
    return [], "", err


def analyze(closes: list[float]) -> dict | None:
    """closes：由舊到新。回傳滾動 21 個交易日的高低點狀態與漲跌幅。"""
    if len(closes) < WINDOW:
        return None
    w = closes[-WINDOW:]
    last = w[-1]
    chg = (last / w[0] - 1) * 100
    state = "high" if last >= max(w) else ("low" if last <= min(w) else "")
    return {"last": last, "chg21": chg, "state": state}


def run(slot_iso: str = "", fetch=closes_for) -> dict:
    """fetch 可替換（測試用）。回傳 {rows, alerts, fail, sources, asof, stale, error}。"""
    out = {"rows": [], "alerts": [], "fail": [], "sources": {}, "asof": "", "stale": False, "error": ""}
    probe_c, probe_d, probe_src = fetch("SPY")
    if not probe_c:
        out["error"] = f"價格來源連不上（SPY：{probe_src}）"
        return out
    out["asof"] = probe_d
    if slot_iso and probe_d != slot_iso:
        out["stale"] = True
        out["error"] = f"價格最新日期 {probe_d} 與交易日 {slot_iso} 不符（資料過期或尚未收盤），本集不使用"

    def one(sym):
        return sym, fetch(sym)

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(one, list(WATCH)))
    for sym, (closes, last, src) in results:
        name, kind, sec = WATCH[sym]
        a = analyze(closes) if closes else None
        if not a:
            out["fail"].append(f"{sym}（{src}）")
            continue
        out["sources"][src] = out["sources"].get(src, 0) + 1
        out["rows"].append({"sym": sym, "name": name or sym, "kind": kind, "sec": sec, "date": last, **a})
    out["alerts"] = [r for r in out["rows"] if r["state"] and r["kind"] != "etf"]
    return out


def get(slot_iso: str = "", fetch=closes_for) -> dict:
    """同一個交易日在同一次執行裡只抓一次（試跑與成稿共用）。"""
    if slot_iso not in _CACHE:
        _CACHE[slot_iso] = run(slot_iso, fetch)
    return _CACHE[slot_iso]


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else "、".join(names[:-1]) + " 與 " + names[-1]


def spoken(res: dict) -> str:
    """日更集數口播的一小段（固定句型、中立、不含任何建議）。資料不可用就回空字串。"""
    if not res.get("rows") or res.get("stale"):
        return ""
    by = {r["sym"]: r for r in res["rows"]}
    parts = []
    for sec, syms in LEAD:
        bits = [f"{s} {'上漲' if by[s]['chg21'] >= 0 else '下跌'} {abs(by[s]['chg21']):.1f}%" for s in syms if s in by]
        if bits:
            parts.append(f"{sec}方面，" + "，".join(bits))
    if not parts:
        return ""
    txt = "接下來看價格動向，以下都是過去 21 個交易日的收盤價變化。" + "；".join(parts) + "。"
    etf_hi = [r["sym"] for r in res["rows"] if r["kind"] == "etf" and r["state"] == "high"]
    etf_lo = [r["sym"] for r in res["rows"] if r["kind"] == "etf" and r["state"] == "low"]
    if etf_lo:
        txt += f"指數型基金中，{_join(etf_lo)} 今天收盤創下近 21 個交易日的新低。"
    if etf_hi:
        txt += f"{_join(etf_hi)} 今天收盤創下近 21 個交易日的新高。"
    lo = [r["name"] for r in res["alerts"] if r["state"] == "low"]
    hi = [r["name"] for r in res["alerts"] if r["state"] == "high"]
    cap = lambda xs: _join(xs[:8]) + (f" 等 {len(xs)} 檔" if len(xs) > 8 else "")
    if lo or hi:
        txt += "觀察列表中，"
        if lo:
            txt += f"{cap(lo)} 的收盤價創下近 21 個交易日新低"
        if lo and hi:
            txt += "；"
        if hi:
            txt += f"{cap(hi)} 的收盤價創下近 21 個交易日新高"
        txt += "。"
    return txt + "以上由程式依收盤價計算，僅供參考。"


def render_md(res: dict) -> str:
    out = ["## 價格動向（滾動 21 個交易日）", ""]
    out.append(f"成功 {len(res['rows'])} 檔；失敗 {len(res['fail'])} 檔；資料來源：{res['sources'] or '無'}；資料日期：{res.get('asof') or '無'}")
    if res.get("error"):
        out.append(f"⚠️ {res['error']}")
    if res["fail"]:
        out.append("失敗清單：" + "、".join(res["fail"]))
    out += ["", "### 各分類指數型基金（ETF）近 21 個交易日", ""]
    for r in sorted((x for x in res["rows"] if x["kind"] == "etf"), key=lambda x: x["sec"]):
        tag = {"high": "　⬆ 今日收盤為 21 日高點", "low": "　⬇ 今日收盤為 21 日低點"}.get(r["state"], "")
        out.append(f"- [{r['sec']}] {r['sym']}：{r['chg21']:+.1f}%{tag}")
    out += ["", "### 觀察列表個股提醒（收盤為 21 日高點或低點）", ""]
    if res["alerts"]:
        for r in res["alerts"]:
            out.append(f"- {r['sym']}（{r['name']}，{'大盤權重股' if r['kind'] == 'heavy' else '個股'}）：今日收盤為近 21 個交易日的{'最高' if r['state'] == 'high' else '最低'}收盤價")
    else:
        out.append("- 今天沒有個股觸發。")
    out += ["", "_以上由程式依收盤價計算，不構成任何買賣建議。_"]
    return "\n".join(out) + "\n"

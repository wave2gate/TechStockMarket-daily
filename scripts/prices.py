"""
價格模組（v1.10.0）：用程式算價格事實，全部不經 AI。
  ① 觀察列表每檔：今日收盤是否為「滾動 21 個交易日」的最高或最低收盤價
  ② 各分類指數型基金（ETF）近 21 個交易日漲跌
v1.10.0 起日更集數會把它變成一小段固定句型口播（spoken）；R2 文稿頁／試跑顯示完整表格（render_md）。
資料來源依序：Yahoo 圖表介面（調整後收盤價，避免拆股造成假新低）→ Stooq 日線 CSV。
安全設計：先用 SPY 試連，兩個來源都失敗就整個略過（不等 60 檔逐一逾時）；SPY 最新日期不等於交易日（資料過期或還沒收盤）也整段略過。
User-Agent 只用誠實的程式名稱，不偽裝瀏覽器。
"""
import csv, functools, io, json, logging, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from watchlist import WATCH, LEAD

__version__ = "1.10.2"
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
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or []
    raw = res["indicators"]["quote"][0]["close"]
    # v1.10.2：當天最新一根的「調整後收盤」常比一般收盤晚更新（為 null）；最新一根的調整後收盤本來就等於收盤，所以缺的時候用收盤補，
    # 否則最新日期會被誤判成前一天、整段價格被當成過期丟掉。
    closes = [(adj[i] if i < len(adj) and adj[i] is not None else raw[i]) for i in range(len(raw))]
    pairs = [(t, c) for t, c in zip(ts, closes) if c is not None]
    return [c for _, c in pairs], datetime.fromtimestamp(pairs[-1][0], _ET).date().isoformat()


def _stooq(sym: str) -> tuple[list[float], str]:
    rows = [r for r in csv.DictReader(io.StringIO(_get(f"https://stooq.com/q/d/l/?s={sym.lower()}.us&i=d")))
            if r.get("Close") not in (None, "", "null")]
    return [float(r["Close"]) for r in rows], rows[-1]["Date"]


def closes_for(sym: str, expect: str = "") -> tuple[list[float], str, str]:
    """回傳 (收盤價由舊到新, 最新一筆日期, 來源或錯誤)。
    expect＝期望的最新日期（美東交易日）。第一個來源的最新日期不是它時，會再試第二個來源，取日期較新的那份。"""
    err, best = "", ([], "", "")
    for name, fn in (("yahoo", _yahoo), ("stooq", _stooq)):
        try:
            c, last = fn(sym)
            if len(c) >= WINDOW:
                if not expect or last >= expect:
                    return c, last, name
                if last > best[1]:
                    best = (c, last, name)
            else:
                err = f"{name}:資料不足({len(c)})"
        except Exception as e:
            err = f"{name}:{type(e).__name__}"
    return best if best[0] else ([], "", err)


def diagnose() -> str:
    """過期時給試跑看的診斷：兩個來源各自的最新日期與最後幾筆。"""
    bits = []
    try:
        d = json.loads(_get("https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=1mo&interval=1d"))
        res = d["chart"]["result"][0]
        ts = res.get("timestamp") or []
        adj = ((res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [])[-3:]
        raw = res["indicators"]["quote"][0]["close"][-3:]
        days = [datetime.fromtimestamp(t, _ET).date().isoformat() for t in ts[-3:]]
        bits.append(f"yahoo 最後三筆日期 {days}；收盤 {raw}；調整後收盤 {adj}")
    except Exception as e:
        bits.append(f"yahoo 診斷失敗 {type(e).__name__}")
    try:
        c, last = _stooq("SPY")
        bits.append(f"stooq 最新日期 {last}")
    except Exception as e:
        bits.append(f"stooq 診斷失敗 {type(e).__name__}")
    return "；".join(bits)


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
    if fetch is closes_for and slot_iso:
        fetch = functools.partial(closes_for, expect=slot_iso)
    probe_c, probe_d, probe_src = fetch("SPY")
    if not probe_c:
        out["error"] = f"價格來源連不上（SPY：{probe_src}）"
        return out
    out["asof"] = probe_d
    if slot_iso and probe_d != slot_iso:
        out["stale"] = True
        out["error"] = f"價格最新日期 {probe_d} 與交易日 {slot_iso} 不符（資料過期或尚未收盤），本集不使用"
        try:
            out["diag"] = diagnose()
        except Exception:
            pass

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
        res = run(slot_iso, fetch)
        # 正式發布（排程）會在等發布時刻前，資料還沒更新就每分鐘重試一次，最多 PRICE_WAIT_MIN 分鐘；試跑預設不等
        try:
            wait_min = int(os.environ.get("PRICE_WAIT_MIN", "0") or 0)
        except ValueError:
            wait_min = 0
        t0 = time.time()
        while slot_iso and wait_min > 0 and (res.get("stale") or (res.get("error") and not res.get("rows"))) \
                and time.time() - t0 < wait_min * 60:
            log.info("   價格資料還沒更新到交易日，1 分鐘後重試")
            time.sleep(60)
            res = run(slot_iso, fetch)
        _CACHE[slot_iso] = res
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
    if res.get("diag"):
        out.append(f"診斷：{res['diag']}")
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

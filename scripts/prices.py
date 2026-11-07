"""
價格模組（v1.9.0，只在「試跑」顯示，還沒接進節目稿）。
做兩件事，全部由程式計算，不交給 AI：
  ① 每檔觀察列表的「滾動 21 個交易日」收盤價：今天收盤是否為這 21 天的最高或最低
  ② 各分類指數型基金（ETF）近 21 個交易日的漲跌幅
資料來源依序嘗試：Yahoo 圖表介面（用調整後收盤價，避免拆股造成假新低）→ Stooq 日線 CSV。
兩個來源我都沒在雲端環境驗證過（這裡連不到），所以抓不到時整檔略過、並在試跑摘要列出失敗清單。
User-Agent 只用誠實的程式名稱，不偽裝瀏覽器。
"""
import csv, io, json, logging, urllib.request

from watchlist import WATCH

__version__ = "1.9.0"
log = logging.getLogger(__name__)
WINDOW = 21
_UA = {"User-Agent": "TechStockMarket-daily/1.9 (podcast research script)"}


def _get(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _yahoo(sym: str) -> list[float]:
    d = json.loads(_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d"))
    res = d["chart"]["result"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    closes = adj or res["indicators"]["quote"][0]["close"]
    return [c for c in closes if c is not None]


def _stooq(sym: str) -> list[float]:
    rows = list(csv.DictReader(io.StringIO(_get(f"https://stooq.com/q/d/l/?s={sym.lower()}.us&i=d"))))
    return [float(r["Close"]) for r in rows if r.get("Close") not in (None, "", "null")]


def closes_for(sym: str) -> tuple[list[float], str]:
    err = ""
    for name, fn in (("yahoo", _yahoo), ("stooq", _stooq)):
        try:
            c = fn(sym)
            if len(c) >= WINDOW:
                return c, name
            err = f"{name}:資料不足({len(c)})"
        except Exception as e:
            err = f"{name}:{type(e).__name__}"
    return [], err


def analyze(closes: list[float]) -> dict | None:
    """closes：由舊到新的收盤價。回傳滾動 21 個交易日的高低點狀態與漲跌幅。"""
    if len(closes) < WINDOW:
        return None
    w = closes[-WINDOW:]
    last = w[-1]
    chg = (last / w[0] - 1) * 100
    state = "high" if last >= max(w) else ("low" if last <= min(w) else "")
    return {"last": last, "chg21": chg, "state": state}


def run(fetch=closes_for) -> dict:
    """fetch 可替換（測試用）。回傳 {rows, alerts, fail, sources}。"""
    rows, fail, srcs = [], [], {}
    for sym, (name, kind, sec) in WATCH.items():
        closes, src = fetch(sym)
        a = analyze(closes) if closes else None
        if not a:
            fail.append(f"{sym}（{src}）")
            continue
        srcs[src] = srcs.get(src, 0) + 1
        rows.append({"sym": sym, "name": name or sym, "kind": kind, "sec": sec, **a})
    alerts = [r for r in rows if r["state"] and r["kind"] != "etf"]
    return {"rows": rows, "alerts": alerts, "fail": fail, "sources": srcs}


def render_md(res: dict) -> str:
    out = ["## 價格試驗（滾動 21 個交易日；未進入節目稿）", ""]
    out.append(f"成功 {len(res['rows'])} 檔；失敗 {len(res['fail'])} 檔；資料來源：{res['sources'] or '無'}")
    if res["fail"]:
        out.append("失敗清單：" + "、".join(res["fail"]))
    out += ["", "### 各分類指數型基金（ETF）近 21 個交易日", ""]
    for r in sorted((x for x in res["rows"] if x["kind"] == "etf"), key=lambda x: x["sec"]):
        tag = {"high": "　⬆ 今日收盤為 21 日高點", "low": "　⬇ 今日收盤為 21 日低點"}.get(r["state"], "")
        out.append(f"- [{r['sec']}] {r['sym']}：{r['chg21']:+.1f}%{tag}")
    out += ["", "### 觀察列表個股提醒（收盤為 21 日高點或低點）", ""]
    if res["alerts"]:
        for r in res["alerts"]:
            out.append(f"- {r['sym']}（{r['name']}，{'大盤權重股' if r['kind']=='heavy' else '個股'}）：今日收盤為近 21 個交易日的{'最高' if r['state']=='high' else '最低'}收盤價")
    else:
        out.append("- 今天沒有個股觸發。")
    return "\n".join(out) + "\n"

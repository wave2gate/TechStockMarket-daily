"""
數據抓取（v1.6.0）：官方 RSS 為主；每個來源可有多個備用網址，備用來源的條目「併入」而不是取代。
新增官方來源：聯準會、勞工統計局；Google News RSS 只當作標題備援（無摘要）。
新網址未必都有效，試跑 Summary 的「來源診斷」會逐一列出。
"""
__version__ = "1.6.1"
import time, logging
from datetime import datetime, timedelta, timezone

import feedparser, requests

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PodcastBot/1.0)"}
DEFAULT_AGE_H = 30
# 更新較慢的專業媒體放寬時間窗（小時）；否則一直是 0 則
MAX_AGE_H = {"Bloomberg NEF": 96, "Energy Storage News": 72, "RCR Wireless": 72, "Telecoms.com": 72,
             "SDxCentral": 72, "Investopedia": 72, "FierceWireless": 48, "Light Reading": 48}
DIAG: dict[str, dict] = {}      # 每個來源最後一次嘗試的結果（試跑 Summary 會列出）
MAX_PER = 8

# ── 帳號清單：(顯示名稱, 官方RSS) ─────────────────────────────────────
# 全部使用官方 RSS，nitter 已不可靠
SOURCES = [
    ("WSJ Markets",
     "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),

    ("CNBC",
     "https://www.cnbc.com/id/100003114/device/rss/rss.html"),

    ("Bloomberg Markets",
     "https://feeds.bloomberg.com/markets/news.rss"),

    ("Seeking Alpha",
     "https://seekingalpha.com/feed.xml"),

    ("TechCrunch",
     "https://techcrunch.com/feed/"),

    ("MarketWatch",
     "https://feeds.content.dowjones.io/public/rss/mw_topstories"),

    ("Yahoo Finance",
     "https://finance.yahoo.com/rss/topstories"),

    ("Investing.com",
     "https://www.investing.com/rss/news.rss"),

    ("Energy Storage News",
     "https://www.energy-storage.news/feed/"),

    ("Bloomberg NEF",
     "https://about.bnef.com/feed/"),

    # ── v1.5.0 新增（RSS 網址未在開發環境驗證；抓不到的會自動略過，試跑 Summary 會列出每個來源的則數）──
    ("Financial Times",
     "https://www.ft.com/rss/home"),

    ("Benzinga",
     "https://www.benzinga.com/feed"),

    ("Investopedia",
     "https://www.investopedia.com/feedbuilder/feed/getfeed?feedName=rss_headline"),

    ("RCR Wireless",
     "https://www.rcrwireless.com/feed"),

    ("Telecoms.com",
     "https://www.telecoms.com/feed/"),

    ("FierceWireless",
     "https://www.fiercewireless.com/rss/xml"),

    ("Light Reading",
     "https://www.lightreading.com/rss.xml"),

    ("SDxCentral",
     "https://www.sdxcentral.com/feed/"),

    # ── v1.6.0 新增 ──
    ("Federal Reserve",
     "https://www.federalreserve.gov/feeds/press_all.xml"),

    ("BLS",
     "https://www.bls.gov/feed/bls_latest.rss"),

    ("Nasdaq",
     "https://www.nasdaq.com/feed/rssoutbound?category=Markets"),

    ("Mobile World Live",
     "https://www.mobileworldlive.com/feed/"),

    ("Utility Dive",
     "https://www.utilitydive.com/feeds/news/"),

    ("Electrek",
     "https://electrek.co/feed/"),
]

def _gnews(q: str) -> str:
    return f"https://news.google.com/rss/search?q={q}+when:2d&hl=en-US&gl=US&ceid=US:en"

# 備用網址（依序嘗試，條目併入；官方源條目不足 2 則才會啟動）
FALLBACKS = {
    "Bloomberg Markets": ["https://feeds.bloomberg.com/technology/news.rss"],
    "Bloomberg NEF":     ["https://www.bnef.com/core/search/news.rss"],
    "Seeking Alpha":     ["https://seekingalpha.com/market_currents.xml"],
    "FierceWireless":    ["https://www.fierce-network.com/rss/xml"],
    "RCR Wireless":      ["https://www.rcrwireless.com/feed/", _gnews("site:rcrwireless.com")],
    "Telecoms.com":      ["https://telecoms.com/feed/", _gnews("site:telecoms.com")],
    "WSJ Markets":       ["https://feeds.a.dj.com/rss/RSSWSJD.xml", _gnews("site:wsj.com+markets")],
    "Yahoo Finance":     ["https://finance.yahoo.com/news/rssindex",
                          "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC,%5EIXIC,NVDA,AAPL,MSFT&region=US&lang=en-US",
                          _gnews("site:finance.yahoo.com")],
    "Investopedia":      [_gnews("site:investopedia.com")],
    "SDxCentral":        [_gnews("site:sdxcentral.com")],
    "Federal Reserve":   ["https://www.federalreserve.gov/feeds/press_monetary.xml"],
}
TIMEOUT = {"Nasdaq": 30}
MAX_AGE_H.update({"Federal Reserve": 240, "BLS": 240, "Utility Dive": 48, "Electrek": 36, "Mobile World Live": 72})


def _parse(url: str, label: str) -> list[dict]:
    """解析單個 RSS URL，返回標準化條目；同時把診斷結果記進 DIAG。"""
    base = label.replace("(alt)", "")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_H.get(base, DEFAULT_AGE_H))
    diag = {"url": url, "status": "-", "entries": 0, "fresh": 0, "newest": "-", "error": ""}
    DIAG[label] = diag
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT.get(base, 15))
        diag["status"] = r.status_code
        r.raise_for_status()
        feed  = feedparser.parse(r.content)
        diag["entries"] = len(feed.entries)
        items = []
        newest = None
        for e in feed.entries[:MAX_PER]:
            # 解析發布時間
            pub = datetime.now(timezone.utc)
            for attr in ("published_parsed", "updated_parsed"):
                t = getattr(e, attr, None)
                if t:
                    try:
                        pub = datetime(*t[:6], tzinfo=timezone.utc)
                        break
                    except Exception:
                        pass
            if getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None):
                newest = max(newest, pub) if newest else pub
            if pub < cutoff:
                continue
            items.append({
                "source":  base,
                "title":   getattr(e, "title",   "").strip(),
                "summary": getattr(e, "summary", "")[:400].strip(),
                "url":     getattr(e, "link",    ""),
            })
        diag["fresh"] = len(items)
        diag["newest"] = newest.strftime("%m-%d %H:%M UTC") if newest else "無時間欄位"
        return items
    except Exception as ex:
        diag["error"] = f"{type(ex).__name__}: {str(ex)[:100]}"
        log.warning(f"   {label} RSS 失敗: {ex}")
        return []


def fetch_all() -> list[dict]:
    results = []
    for label, rss_url in SOURCES:
        items = _parse(rss_url, label)

        # 官方源條目不足 → 依序嘗試備用網址，條目「併入」（不丟掉官方源已抓到的）
        if len(items) < 2:
            seen = {it["url"] for it in items}
            for i, alt in enumerate(FALLBACKS.get(label, []), 1):
                log.info(f"   {label} 條目不足，嘗試備用源 {i}...")
                for it in _parse(alt, f"{label}(alt{i})"):
                    if it["url"] not in seen:
                        items.append(it)
                        seen.add(it["url"])
                if len(items) >= 3:
                    break

        if items:
            log.info(f"   ✓ {label}: {len(items)} 則")
        else:
            log.warning(f"   ✗ {label}: 0 則（跳過）")

        results.extend(items)
        time.sleep(1.0)

    total = len(results)
    log.info(f"抓取完成，共 {total} 則")

    # 保底：若總量太少，返回基本提示讓 AI 知道數據不足
    if total < 5:
        log.error("抓取數據嚴重不足！請檢查網路或 RSS 源")

    return results

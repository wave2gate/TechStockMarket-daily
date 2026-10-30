"""
數據抓取：官方 RSS 為主（穩定），nitter 已基本失效不再依賴
10個帳號全部有官方 RSS 備源
"""
__version__ = "1.5.0"
import time, logging
from datetime import datetime, timedelta, timezone

import feedparser, requests

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PodcastBot/1.0)"}
CUTOFF  = datetime.now(timezone.utc) - timedelta(hours=30)
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
]

# 備用：若官方 RSS 失敗，嘗試這些替代源
FALLBACKS = {
    "Bloomberg Markets": "https://feeds.bloomberg.com/technology/news.rss",
    "Bloomberg NEF":     "https://www.bnef.com/core/search/news.rss",
    "Seeking Alpha":     "https://seekingalpha.com/market_currents.xml",
    "FierceWireless":    "https://www.fierce-network.com/rss/xml",
}


def _parse(url: str, label: str) -> list[dict]:
    """解析單個 RSS URL，返回標準化條目"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        feed  = feedparser.parse(r.content)
        items = []
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
            if pub < CUTOFF:
                continue
            items.append({
                "source":  label,
                "title":   getattr(e, "title",   "").strip(),
                "summary": getattr(e, "summary", "")[:400].strip(),
                "url":     getattr(e, "link",    ""),
            })
        return items
    except Exception as ex:
        log.warning(f"   {label} RSS 失敗: {ex}")
        return []


def fetch_all() -> list[dict]:
    results = []
    for label, rss_url in SOURCES:
        items = _parse(rss_url, label)

        # 若官方源條目不足，嘗試備用源
        if len(items) < 2 and label in FALLBACKS:
            log.info(f"   {label} 條目不足，嘗試備用源...")
            items = _parse(FALLBACKS[label], f"{label}(alt)")

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

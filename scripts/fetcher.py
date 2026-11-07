"""
數據抓取（v1.6.0）：官方 RSS 為主；每個來源可有多個備用網址，備用來源的條目「併入」而不是取代。
新增官方來源：聯準會、勞工統計局；Google News RSS 只當作標題備援（無摘要）。
新網址未必都有效，試跑 Summary 的「來源診斷」會逐一列出。
"""
__version__ = "1.9.0"
import html as _html, re, time, logging
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


# ── v1.8.0 新增：依主題補強的專業來源（網址未驗證，以試跑「來源診斷」為準；抓不到會自動略過）──
SOURCES += [
    ("Semiconductor Engineering", "https://semiengineering.com/feed/"),
    ("EE Times",                  "https://www.eetimes.com/feed/"),
    ("SpaceNews",                 "https://spacenews.com/feed/"),
    ("Via Satellite",             "https://www.satellitetoday.com/feed/"),
    ("POWER Magazine",            "https://www.powermag.com/feed/"),
    ("Canary Media",              "https://www.canarymedia.com/rss.rss"),
    ("Data Center Dynamics",      "https://www.datacenterdynamics.com/en/rss/"),
    ("EIA Today in Energy",       "https://www.eia.gov/rss/todayinenergy.xml"),
    ("OilPrice.com",              "https://oilprice.com/rss/main"),
    ("Rigzone",                   "https://www.rigzone.com/news/rss/rigzone_latest.aspx"),
    # 資安與數據中心基礎設施（v1.8.1）
    ("Krebs on Security",         "https://krebsonsecurity.com/feed/"),
    ("BleepingComputer",          "https://www.bleepingcomputer.com/feed/"),
    ("The Hacker News",           "https://feeds.feedburner.com/TheHackersNews"),
    ("SecurityWeek",              "https://feeds.feedburner.com/securityweek"),
    ("Dark Reading",              "https://www.darkreading.com/rss.xml"),
    ("CISA Advisories",           "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
    ("Data Center Knowledge",     "https://www.datacenterknowledge.com/rss.xml"),
    ("The Record",                "https://therecord.media/feed"),
    ("Microsoft Security",        "https://www.microsoft.com/en-us/security/blog/feed/"),
    # 貴金屬與關鍵礦產（v1.9.0，網址未驗證，以試跑「來源診斷」為準）
    ("Mining.com",                "https://www.mining.com/feed/"),
    ("Kitco",                     "https://www.kitco.com/rss/KitcoNews.xml"),
    ("Northern Miner",            "https://www.northernminer.com/feed/"),
]
# Google News 關鍵字搜尋（公開 RSS，只有標題；補專門主題的缺口）。標籤以「Google News｜」開頭，摘要不使用。
GNEWS_TOPICS = [
    ("記憶體與 HBM",   "HBM+OR+DRAM+OR+Micron+OR+%22SK+hynix%22", "A2"),
    ("AI 晶片",        "Nvidia+OR+AMD+OR+Broadcom+AI+chips", "A1"),
    ("晶圓製造與設備", "TSMC+OR+ASML+OR+%22advanced+packaging%22", "A3"),
    ("變壓器與電網設備", "transformer+shortage+OR+%22grid+equipment%22+OR+substation+OR+switchgear", "B2"),
    ("數據中心供電",   "%22data+center%22+power+demand+OR+%22behind-the-meter%22", "B4"),
    ("油氣與油價",     "oil+prices+OR+OPEC+OR+LNG", "B5"),
    ("6G 與下一代網路", "6G+OR+%22next-generation+network%22+OR+%22open+RAN%22", "A7"),
    ("衛星與太空",     "%22direct-to-cell%22+OR+Starlink+OR+%22AST+SpaceMobile%22+OR+%22Rocket+Lab%22", "A6"),
    ("電信運營商",     "Verizon+OR+AT%26T+OR+T-Mobile+capex+OR+fiber", "B6"),
    ("電信設備",       "Ericsson+OR+Nokia+OR+Corning+OR+Ciena", "B7"),
    ("資安與駭客事件", "cyberattack+OR+ransomware+OR+%22zero-day%22+OR+%22data+breach%22", "S1"),
    ("資安公司",       "%22Palo+Alto+Networks%22+OR+CrowdStrike+OR+Zscaler+OR+Cloudflare+OR+Fortinet", "S1"),
    ("機櫃與散熱",     "%22data+center%22+cooling+OR+Vertiv+OR+%22liquid+cooling%22+OR+nVent", "S3"),
    ("重大駭客與加密貨幣盜竊", "%22crypto%22+hack+OR+%22exchange+hack%22+OR+%22stolen+crypto%22+OR+%22crypto+theft%22", "S1"),
    ("上市公司資安事件", "%22data+breach%22+OR+ransomware+company+shares+OR+%228-K%22+cybersecurity+incident", "S1"),
    ("貴金屬",         "gold+price+OR+silver+price+OR+%22precious+metals%22", "M1"),
    ("銅與關鍵礦產",   "copper+price+OR+%22rare+earth%22+OR+%22critical+minerals%22+OR+lithium+miner", "M2"),
    ("鈾與核燃料",     "uranium+OR+Cameco+OR+Centrus+OR+%22nuclear+fuel%22", "M3"),
    ("數據中心樓控與工控攻擊", "%22data+center%22+HVAC+OR+SCADA+OR+%22cooling+system%22+cyberattack+OR+hack", "S3"),
]
for _n, _q, _h in GNEWS_TOPICS:
    SOURCES.append((f"Google News｜{_n}", _gnews(_q)))
GN_HINTS = {f"Google News｜{n}": h for n, _, h in GNEWS_TOPICS}

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
    "Mining.com":        [_gnews("site:mining.com")],
    "Kitco":             [_gnews("site:kitco.com")],
    "Northern Miner":    [_gnews("site:northernminer.com")],
    "The Record":        [_gnews("site:therecord.media")],
}
TIMEOUT = {"Nasdaq": 30}
MAX_AGE_H.update({"Krebs on Security": 72, "BleepingComputer": 36, "The Hacker News": 36, "SecurityWeek": 48, "Dark Reading": 48,
                  "CISA Advisories": 168, "Data Center Knowledge": 72, "Semiconductor Engineering": 48, "EE Times": 48, "SpaceNews": 48, "Via Satellite": 72, "POWER Magazine": 72,
                  "Mining.com": 36, "Kitco": 36, "Northern Miner": 72, "The Record": 48, "Microsoft Security": 168, "Canary Media": 72, "Data Center Dynamics": 48, "EIA Today in Energy": 168, "OilPrice.com": 36, "Rigzone": 36,"Federal Reserve": 240, "BLS": 240, "Utility Dive": 48, "Electrek": 36, "Mobile World Live": 72})


def _parse(url: str, label: str) -> list[dict]:
    """解析單個 RSS URL，返回標準化條目；同時把診斷結果記進 DIAG。"""
    base = re.sub(r"\(alt\d*\)", "", label)
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
                "title":   _html.unescape(re.sub(r"<[^>]+>", " ", getattr(e, "title", ""))).strip(),
                "summary": "" if base.startswith("Google News") else re.sub(r"<[^>]+>", " ", getattr(e, "summary", ""))[:400].strip(),
                "hint":    GN_HINTS.get(base, ""),
                "url":     getattr(e, "link",    ""),
            })
        diag["fresh"] = len(items)
        diag["newest"] = newest.strftime("%m-%d %H:%M UTC") if newest else "無時間欄位"
        return items
    except Exception as ex:
        diag["error"] = f"{type(ex).__name__}: {str(ex)[:100]}"
        log.warning(f"   {label} RSS 失敗: {ex}")
        return []


def _dedupe(items: list[dict]) -> list[dict]:
    """同一則新聞常被多個來源／Google News 重複收錄：依網址與標題前 60 字去重，保留先出現的。"""
    seen_u, seen_t, out = set(), set(), []
    for it in items:
        key = re.sub(r"[^a-z0-9]+", "", re.sub(r"\s+[-–|]\s+[^-–|]+$", "", it["title"].lower()))[:60]
        if (it["url"] and it["url"] in seen_u) or (key and key in seen_t):
            continue
        seen_u.add(it["url"]); seen_t.add(key); out.append(it)
    return out


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

    results = _dedupe(results)
    total = len(results)
    log.info(f"抓取完成，共 {total} 則（已去除重複）")

    # 保底：若總量太少，返回基本提示讓 AI 知道數據不足
    if total < 5:
        log.error("抓取數據嚴重不足！請檢查網路或 RSS 源")

    return results

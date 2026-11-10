"""
新聞分類（v1.8.0）：用關鍵詞把每則新聞歸到一個細項，由程式決定，不讓 AI 決定。

★ 你可以直接改這個檔案：
  - BUCKETS 每個細項的 "kw" 是關鍵詞（英文，不分大小寫；多字詞權重較高）。
  - WATCHLIST 填你想優先的公司或關鍵字（例如 "Nvidia", "Micron"）：提到的新聞選材時優先，只是「選材優先」，不是買賣建議。
分數規則：關鍵詞命中越多、越具體分數越高；來源本身的預設細項（HINTS）加 1 分；沒有任何命中就用來源預設。
"""
import re

__version__ = "1.10.1"
try:
    from version import RELEASE as _REL
except Exception:                                  # 沒有 version.py 時不讓整個流程壞掉
    _REL = "?"

try:
    from watchlist import news_keywords as _nk
    WATCHLIST: list[str] = _nk()                 # 選材優先（不是買賣建議）；清單在 watchlist.py
except Exception:
    WATCHLIST = ["Palo Alto Networks", "Cloudflare", "Vertiv"]

# 區塊 → 細項。順序也是稿子與統計表的順序。
SECTIONS = [
    ("共通", [("C1", "大盤、利率與聯準會"), ("C2", "財報與重要公司事件"), ("C3", "政策與監管")]),
    ("AI 與半導體", [("A1", "AI 晶片與算力"), ("A2", "記憶體與儲存（HBM、DRAM、NAND）"),
                    ("A3", "晶圓製造、設備與先進封裝"), ("A4", "AI 軟體、雲端與資本支出")]),
    ("太空與下一代通訊", [("A5", "光通訊與資料中心互連"), ("A6", "衛星、航太與太空"), ("A7", "6G 與下一代網路（NGN）")]),
    ("資安與數據中心基礎設施", [("S1", "網路與通訊安全（駭客、勒索、漏洞）"), ("S2", "軟硬體與供應鏈安全"),
                      ("S3", "數據中心機櫃、散熱與樓控／工控安全")]),
    ("電信", [("B6", "電信運營商"), ("B7", "電信設備與供應鏈")]),
    ("電力與電網", [("B1", "發電與公用事業"), ("B2", "電網與輸配電設備"), ("B3", "儲能與電池"),
                  ("B4", "數據中心供電")]),
    ("油氣", [("B5", "石油與天然氣")]),
    ("貴金屬與關鍵礦產", [("M1", "貴金屬（黃金、白銀、鉑）"), ("M2", "銅與關鍵礦產（稀土、鋰、鎳、鈷）"), ("M3", "鈾與核燃料")]),
]
NAMES = {k: n for _, subs in SECTIONS for k, n in subs}

# 越前面的細項，同分時越優先（具體的在前、泛用的在後）
PRIORITY = ["S3", "S1", "S2", "M3", "M2", "M1", "B2", "B4", "B3", "B1", "B5", "A2", "A1", "A3", "A5", "A6", "A7", "A4", "B6", "B7", "C3", "C2", "C1"]

BUCKETS: dict[str, dict] = {
    "C1": {"w": 0.5, "kw": ["federal reserve", "fed ", "fomc", "powell", "market cap", "market value", "selloff", "sell-off", "rout", "tumbles", "plunge", "wipeout", "futures", "rate cut", "rate hike", "inflation", "cpi", "pce",
                            "jobs report", "payrolls", "unemployment", "treasury yield", "treasuries", "s&p 500", "nasdaq",
                            "dow jones", "wall street", "stock futures", "stocks", "gdp", "recession", "bond"]},
    "C2": {"w": 0.7, "kw": ["earnings", "quarterly results", "third-quarter", "revenue", "guidance", "eps", "profit",
                            "ipo", "acquisition", "acquire", "merger", "buyback", "dividend", "layoffs"]},
    "C3": {"w": 0.8, "kw": ["export control", "tariff", "sanction", "antitrust", "regulator", "fcc", "sec ", "chips act",
                            "executive order", "subsidy", "ban on", "lawsuit", "congress", "moratorium", "midterm", "democrat", "republican",
                            "lawmakers", "white house", "regulation", "legislation"]},
    "A1": {"w": 1.0, "kw": ["quantum", "gpu", "nvidia", "amd", "ai chip", "accelerator", "blackwell", "rubin", "custom silicon", "asic",
                            "tpu", "trainium", "inference", "broadcom", "supercomputer", "ai server", "super micro"]},
    "A2": {"w": 1.2, "kw": ["hbm", "dram", "nand", "memory chip", "memory", "micron", "sk hynix", "samsung electronics",
                            "sandisk", "kioxia", "flash storage", "western digital", "seagate"]},
    "A3": {"w": 1.1, "kw": ["tsmc", "foundry", "wafer", "fab ", "lithography", "asml", "applied materials", "lam research",
                            "advanced packaging", "cowos", "semiconductor", "intel foundry", "euv", "chipmaker",
                            "globalfoundries", "kla", "chip equipment", "tokyo electron"]},
    "A4": {"w": 0.9, "kw": ["hyperscaler", "capex", "capital expenditure", "openai", "anthropic", "azure", "aws",
                            "google cloud", "oracle cloud", "llm", "copilot", "ai model", "generative ai", "cloud"]},
    "A5": {"w": 1.2, "kw": ["optical", "optics", "transceiver", "photonic", "co-packaged", "lumentum", "coherent",
                            "marvell", "interconnect", "800g", "1.6t", "indium phosphide", "inp "]},
    "A6": {"w": 1.2, "kw": ["satellite", "spacex", "starlink", "starship", "rocket", "rocket launch", "launch vehicle", "orbit", "leo ",
                            "direct-to-cell", "ast spacemobile", "rocket lab", "kuiper", "blue origin", "nasa",
                            "aerospace", "space station", "lunar", "spacecraft"]},
    "A7": {"w": 1.3, "kw": ["6g", "5g-advanced", "5g advanced", "ngn", "next-generation network", "open ran", "o-ran",
                            "ai-ran", "3gpp", "non-terrestrial", "ntn", "spectrum", "ran "]},
    "S1": {"w": 1.3, "kw": ["cyberattack", "cyber attack", "cyberattacks", "hacker", "hackers", "hacked", "breach", "ransomware",
                            "zero-day", "vulnerability", "vulnerabilities", "cve-", "exploit", "malware", "phishing", "ddos",
                            "zero trust", "sase", "firewall", "palo alto", "crowdstrike", "zscaler", "fortinet", "okta",
                            "sentinelone", "cloudflare", "cisa", "botnet", "crypto hack", "exchange hack", "crypto theft", "stolen crypto", "drained", "lazarus", "north korea", "dprk", "8-k cyber", "data breach", "stolen data", "espionage", "salt typhoon", "volt typhoon",
                            "encryption", "post-quantum", "cybersecurity", "security flaw", "threat actor"]},
    "S2": {"w": 1.2, "kw": ["firmware", "supply chain attack", "software supply chain", "hardware security", "chip vulnerability",
                            "spectre", "side-channel", "secure boot", "backdoor", "vpn", "edge device", "tpm",
                            "confidential computing", "router flaw", "bios", "open source package"]},
    "S3": {"w": 1.6, "kw": ["cooling", "liquid cooling", "chiller", "hvac", "cdu", "thermal", "vertiv", "nvent", "modine",
                            "schneider electric", "building management", "scada", "ot security", "industrial control",
                            "water cooling", "cooling system", "power distribution unit", "pdu", "server rack", "rack-level",
                            "immersion cooling"]},
    "M1": {"w": 1.3, "kw": ["gold price", "gold prices", "gold futures", "gold miners", "gold mining", "gold mine", "gold rally", "gold hits",
                            "gold falls", "gold slips", "gold surges", "silver price", "silver prices", "silver futures", "platinum", "palladium", "bullion", "precious metal",
                            "precious metals", "gold miner", "newmont", "barrick", "agnico", "kinross", "wheaton", "royal gold",
                            "franco-nevada", "hecla", "coeur", "pan american silver", "safe haven", "safe-haven"]},
    "M2": {"w": 1.4, "kw": ["copper", "rare earth", "rare earths", "critical mineral", "critical minerals", "nickel", "cobalt",
                            "graphite", "gallium", "germanium", "antimony", "tungsten", "freeport", "southern copper",
                            "mp materials", "albemarle", "lithium price", "spodumene", "mining", "miner ", "magnet supply",
                            "rio tinto", "bhp", "teck", "glencore", "mine "]},
    "M3": {"w": 1.5, "kw": ["uranium", "enrichment", "enriched uranium", "haleu", "nuclear fuel", "cameco", "centrus", "energy fuels",
                            "yellowcake", "uranium price"]},
    "B1": {"w": 1.0, "kw": ["duke energy", "natural gas generation", "gas generation", "spending plan", "capital plan", "rate base", "utility", "utilities", "power plant", "nuclear", "smr", "uprate", "gas-fired", "solar", "wind farm",
                            "renewable", "generation", "coal", "ppa", "rate case", "dominion", "nextera", "vistra",
                            "constellation energy", "geothermal"]},
    "B2": {"w": 1.4, "kw": ["transformer", "grid", "transmission line", "transmission", "substation", "switchgear",
                            "interconnection queue", "pjm", "ercot", "miso", "ferc", "hvdc", "ge vernova", "siemens energy",
                            "hitachi energy", "eaton", "hubbell", "quanta services", "power cable"]},
    "B3": {"w": 1.3, "kw": ["battery", "energy storage", "bess", "lithium", "lfp", "grid-scale", "megapack", "fluence",
                            "storage project", "gwh", "mwh"]},
    "B4": {"w": 1.4, "kw": ["data center power", "data centre power", "backstop", "behind-the-meter",
                            "power demand", "load growth", "gigawatt", "nuclear-powered data"]},
    "B5": {"w": 1.3, "kw": ["oil", "crude", "brent", "wti", "opec", "lng", "natural gas", "gas prices", "refinery",
                            "rig count", "shale", "exxon", "chevron", "occidental", "drilling", "petroleum", "eia "]},
    "B6": {"w": 1.1, "kw": ["verizon", "at&t", "t-mobile", "comcast", "charter", "carrier", "operator", "fiber",
                            "broadband", "wireless", "spectrum auction", "fwa", "lumen", "telecom", "5g", "mobile network", "deutsche telekom", "vodafone", "mobile operator"]},
    "B7": {"w": 1.2, "kw": ["ericsson", "nokia", "cisco", "corning", "ciena", "commscope", "base station", "radio access",
                            "telecom equipment", "fiber optic", "samsung networks", "huawei"]},
}

# 來源預設細項（沒有關鍵詞命中時使用）
HINTS = {
    "CNBC": "C1", "Bloomberg Markets": "C1", "WSJ Markets": "C1", "Yahoo Finance": "C1", "MarketWatch": "C1",
    "Investing.com": "C1", "Nasdaq": "C1", "Financial Times": "C1", "Benzinga": "C1", "Investopedia": "C1",
    "Seeking Alpha": "C2", "Federal Reserve": "C1", "BLS": "C1",
    "TechCrunch": "A4", "Semiconductor Engineering": "A3", "EE Times": "A3", "SpaceNews": "A6", "Via Satellite": "A6",
    "Mobile World Live": "A7", "Light Reading": "B7", "SDxCentral": "B7", "RCR Wireless": "B6", "Telecoms.com": "B6",
    "FierceWireless": "B6", "Energy Storage News": "B3", "Bloomberg NEF": "B1", "Utility Dive": "B2",
    "POWER Magazine": "B1", "Canary Media": "B1", "Data Center Dynamics": "B4", "EIA Today in Energy": "B5",
    "OilPrice.com": "B5", "Rigzone": "B5",
    "Krebs on Security": "S1", "BleepingComputer": "S1", "The Hacker News": "S1", "SecurityWeek": "S1",
    "Dark Reading": "S1", "CISA Advisories": "S1", "Data Center Knowledge": "B4", "The Record": "S1", "Microsoft Security": "S1",
    "Kitco": "M1", "Northern Miner": "M1", "Mining.com": "M2",
}

_COMPILED: dict[str, list[tuple[re.Pattern, float]]] = {}
for _k, _b in BUCKETS.items():
    _COMPILED[_k] = [(re.compile(r"(?<![a-z0-9])" + re.escape(w.strip()) + (r"" if w.endswith(" ") else r"(?![a-z0-9])"),
                              re.I), _b["w"] * (1.0 + 0.5 * (len(w.split()) > 1))) for w in _b["kw"]]


# v1.10.1：貴金屬／礦產細項必須「標題」真的提到金屬或礦業公司才算（Kitco 也發大盤文章，不能只憑來源就歸進來）；
# Mining.com 與 Northern Miner 是礦業專門媒體，不受此限。
_METAL_TITLE = re.compile(
    r"(?<![a-z0-9])(gold|silver|platinum|palladium|bullion|copper|uranium|lithium|nickel|cobalt|rare earths?|critical minerals?|"
    r"graphite|tungsten|antimony|gallium|germanium|miners?|mining|mines?|enrichment|stockpiles?|"
    r"newmont|barrick|agnico|kinross|wheaton|freeport|mp materials|cameco|centrus|rio tinto|bhp|teck|glencore|albemarle|"
    r"hecla|coeur|energy fuels)(?![a-z0-9])")
_MINING_ONLY = {"Mining.com", "Northern Miner"}


def classify(item: dict) -> str:
    text = f"{item.get('title', '')} {(item.get('summary') or '')[:300]} ".lower()
    scores: dict[str, float] = {}
    for k, pats in _COMPILED.items():
        s = sum(w for p, w in pats if p.search(text))
        if s:
            scores[k] = s
    hint = item.get("hint") or HINTS.get(item.get("source", ""))
    if hint:
        scores[hint] = scores.get(hint, 0) + 1.0
    _t = str(item.get("title", "")).lower()
    if (item.get("source") not in _MINING_ONLY and not _METAL_TITLE.search(_t)) or re.search(r"\b(theft|stolen|police)\b", _t):
        for k in ("M1", "M2", "M3"):
            scores.pop(k, None)         # 標題與金屬無關：不歸入貴金屬與礦產（改歸其他細項，沒有線索就是 X）
    if not scores:
        return "X"                      # 沒有任何線索（例如電動車消費新聞）：不進任何筆記組
    return max(scores, key=lambda k: (scores[k], -PRIORITY.index(k)))


def in_watchlist(item: dict) -> bool:
    text = f"{item.get('title', '')} {(item.get('summary') or '')[:300]}".lower()
    return any(w.lower() in text for w in WATCHLIST)


def tag_items(items: list[dict]) -> list[dict]:
    for it in items:
        it["bucket"] = classify(it)
        it["watch"] = in_watchlist(it)
    return items


def count_by_bucket(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        k = it.get("bucket") if isinstance(it, dict) else it
        out[k] = out.get(k, 0) + 1
    return out


# ── 統計表（R2 全文頁與說明欄用；不口播）────────────────────────────
def render_stats(fetched: dict[str, int], covered: dict[str, int]) -> dict:
    total_c = sum(covered.values())
    total_f = sum(v for k, v in fetched.items() if k in NAMES)
    md = [f"## 本集新聞統計（v{_REL}）", "", f"本集稿件涵蓋 **{total_c}** 則新聞（依成稿比對）；今天各來源共抓到 {total_f} 則。", "",
          "| 區塊 | 細項 | 本集涵蓋 | 抓到 |", "|---|---|---|---|"]
    html = [f"<h2>本集新聞統計（v{_REL}）</h2>",
            f"<p>本集稿件涵蓋 <strong>{total_c}</strong> 則新聞（依成稿比對）；今天各來源共抓到 {total_f} 則。</p>",
            "<table><thead><tr><th>區塊</th><th>細項</th><th>本集涵蓋</th><th>抓到</th></tr></thead><tbody>"]
    line_parts = []
    for sec, subs in SECTIONS:
        sc = sum(covered.get(k, 0) for k, _ in subs)
        line_parts.append(f"{sec} {sc}")
        for i, (k, name) in enumerate(subs):
            md.append(f"| {sec if i == 0 else ''} | {name} | {covered.get(k, 0)} | {fetched.get(k, 0)} |")
            html.append(f"<tr><td>{sec if i == 0 else ''}</td><td>{name}</td><td>{covered.get(k, 0)}</td><td>{fetched.get(k, 0)}</td></tr>")
    html.append("</tbody></table>")
    return {"md": "\n".join(md) + "\n", "html": "".join(html),
            "line": f"本集統計：共 {total_c} 則新聞（" + "、".join(line_parts) + "）。",
            "total_covered": total_c, "total_fetched": total_f}

"""
觀察列表（你可以直接改這個檔案）。這不是買賣建議，只用於兩件事：
  ① 新聞選材時，提到這些公司的新聞優先被挑進筆記（用 news 欄的名稱比對）
  ② 價格模組：算每檔的「滾動 21 個交易日」收盤高低點，以及各分類指數型基金（ETF）的近期趨勢（v1.9.0 起只在試跑顯示）
欄位：代號 → (新聞用名稱或 None, 類型, 區塊)
  類型：etf＝指數型基金（看趨勢）／heavy＝大盤權重股（占比高，值得注意）／stock＝一般個股／fav＝你特別看好
這份是我依你描述的方向先挑的起始清單，你之後貼自己的清單，我再幫你分類整理。
"""
__version__ = "1.9.0"

WATCH: dict[str, tuple[str | None, str, str]] = {
    # 定投與大盤（每週定投參考）
    "SPY": (None, "etf", "大盤"), "VOO": (None, "etf", "大盤"), "QQQ": (None, "etf", "大盤"),
    "VTI": (None, "etf", "大盤"), "DIA": (None, "etf", "大盤"),
    # 大盤權重股（占指數比重高，漲跌會帶動指數）
    "NVDA": ("Nvidia", "heavy", "AI 與半導體"), "MSFT": ("Microsoft", "heavy", "大盤"), "AAPL": ("Apple", "heavy", "大盤"),
    "AMZN": ("Amazon", "heavy", "大盤"), "GOOGL": ("Alphabet", "heavy", "大盤"), "META": ("Meta", "heavy", "大盤"),
    "AVGO": ("Broadcom", "heavy", "AI 與半導體"), "TSLA": ("Tesla", "heavy", "大盤"),
    # AI 與半導體
    "SMH": (None, "etf", "AI 與半導體"), "SOXX": (None, "etf", "AI 與半導體"),
    "MU": ("Micron", "stock", "AI 與半導體"), "AMD": ("AMD", "stock", "AI 與半導體"), "TSM": ("TSMC", "stock", "AI 與半導體"),
    "ASML": ("ASML", "stock", "AI 與半導體"), "SNDK": ("Sandisk", "stock", "AI 與半導體"), "MRVL": ("Marvell", "stock", "AI 與半導體"),
    "CRWV": ("CoreWeave", "stock", "AI 與半導體"),
    # 太空與下一代通訊
    "UFO": (None, "etf", "太空與下一代通訊"), "ITA": (None, "etf", "太空與下一代通訊"),
    "ASTS": ("AST SpaceMobile", "stock", "太空與下一代通訊"), "RKLB": ("Rocket Lab", "stock", "太空與下一代通訊"),
    "QCOM": ("Qualcomm", "stock", "太空與下一代通訊"),
    # 資安與數據中心基礎設施
    "CIBR": (None, "etf", "資安與數據中心"), "HACK": (None, "etf", "資安與數據中心"),
    "PANW": ("Palo Alto Networks", "fav", "資安與數據中心"), "NET": ("Cloudflare", "fav", "資安與數據中心"),
    "CRWD": ("CrowdStrike", "stock", "資安與數據中心"), "FTNT": ("Fortinet", "stock", "資安與數據中心"),
    "ZS": ("Zscaler", "stock", "資安與數據中心"), "VRT": ("Vertiv", "fav", "資安與數據中心"),
    # 電信
    "IYZ": (None, "etf", "電信"), "T": ("AT&T", "stock", "電信"), "VZ": ("Verizon", "stock", "電信"),
    "TMUS": ("T-Mobile", "stock", "電信"), "CSCO": ("Cisco", "stock", "電信"), "GLW": ("Corning", "stock", "電信"),
    # 電力與電網
    "XLU": (None, "etf", "電力與電網"), "GRID": (None, "etf", "電力與電網"),
    "ETN": ("Eaton", "stock", "電力與電網"), "GEV": ("GE Vernova", "stock", "電力與電網"), "VST": ("Vistra", "stock", "電力與電網"),
    "CEG": ("Constellation Energy", "stock", "電力與電網"), "NEE": ("NextEra", "stock", "電力與電網"),
    # 油氣
    "XLE": (None, "etf", "油氣"), "XOP": (None, "etf", "油氣"), "XOM": ("Exxon", "stock", "油氣"), "CVX": ("Chevron", "stock", "油氣"),
    # 貴金屬與關鍵礦產
    "GLD": (None, "etf", "貴金屬與關鍵礦產"), "SLV": (None, "etf", "貴金屬與關鍵礦產"), "GDX": (None, "etf", "貴金屬與關鍵礦產"),
    "COPX": (None, "etf", "貴金屬與關鍵礦產"), "URA": (None, "etf", "貴金屬與關鍵礦產"), "REMX": (None, "etf", "貴金屬與關鍵礦產"),
    "NEM": ("Newmont", "stock", "貴金屬與關鍵礦產"), "FCX": ("Freeport-McMoRan", "stock", "貴金屬與關鍵礦產"),
    "MP": ("MP Materials", "stock", "貴金屬與關鍵礦產"), "CCJ": ("Cameco", "stock", "貴金屬與關鍵礦產"),
}


def news_keywords() -> list[str]:
    """新聞選材優先用的公司名稱（去重、保持順序）。"""
    out: list[str] = []
    for name, _kind, _sec in WATCH.values():
        if name and name not in out:
            out.append(name)
    return out

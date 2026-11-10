"""
給讀者看的版本更新紀錄（白話、一句話）。開發者的詳細紀錄在 CHANGELOG.md。
每次發版在 UPDATES 最後加一筆：(日期, 版本, 一句白話)。
  - R2 文稿頁底部會累積顯示全部紀錄（新的在上）。
  - 發版後 SPEAK_DAYS 天內的日更集數，會口播最新一筆（只有一句）。
日期要填「實際上線的日期」（美東交易日），過了口播期就不會再念。
"""
from datetime import date

__version__ = "1.10.1"
SPEAK_DAYS = 3

UPDATES: list[tuple[str, str, str]] = [
    ("2026-11-03", "1.6.0", "每天都有一集：美股休市日播短版休市簡報，週六回顧、週日前瞻；新增美聯儲與勞工統計局官方來源；加強數字核對，杜絕編造。"),
    ("2026-11-04", "1.7.0", "公司名與人名直接念英文原名，金額保留 million、billion、trillion 英文單位，不再換算成萬、億，避免換算出錯。"),
    ("2026-11-05", "1.8.0", "新聞分成 20 個細項，文稿頁新增「本集新聞統計」；新增太空、下一代通訊、電力電網、油氣、電信等專題來源。"),
    ("2026-11-06", "1.8.1", "新增資訊安全與數據中心基礎設施單元，涵蓋網路攻擊與機櫃散熱。"),
    ("2026-11-07", "1.9.0", "播報順序調整為電信在電力之前，新增「貴金屬與關鍵礦產」單元；資安加入重大駭客與加密貨幣盜竊事件。"),
    ("2026-11-07", "1.10.0", "新增價格動向：各分類指數型基金近 21 個交易日漲跌，以及觀察列表個股創 21 日新高或新低的提醒。"),
    ("2026-11-10", "1.10.1", "修正貴金屬單元誤收大盤新聞的問題，同一事件最多報兩則、各細項盡量都有入選，並修正部分金額與月份的念法。"),
]


def spoken_line(slot_iso: str) -> str:
    try:
        d = date.fromisoformat(slot_iso)
    except Exception:
        return ""
    recent = [(dt, v, t) for dt, v, t in UPDATES if 0 <= (d - date.fromisoformat(dt)).days < SPEAK_DAYS]
    if not recent:
        return ""
    dt, v, t = recent[-1]
    return f"另外跟大家報告一下，本節目有更新：{t}"


def render_md() -> str:
    lines = ["## 版本更新紀錄", ""]
    lines += [f"- **v{v}**（{dt}）：{t}" for dt, v, t in reversed(UPDATES)]
    return "\n".join(lines) + "\n"


def render_html() -> str:
    import html as _h
    items = "".join(f"<li><strong>v{_h.escape(v)}</strong>（{dt}）：{_h.escape(t)}</li>" for dt, v, t in reversed(UPDATES))
    return f"<h2>版本更新紀錄</h2><ul>{items}</ul>"

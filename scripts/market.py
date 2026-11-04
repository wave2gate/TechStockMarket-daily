"""
市場日歷與「這一集屬於哪一天、哪一種」（v1.6.0）

核心觀念：一集節目的日期以「美東時間的交易日」為準（slot_date），不看 UTC。
    slot_date = (現在的美東時間 − 12 小時) 的日期
    → 美東 17:00（收盤後一小時）到隔天 11:59 之間執行，都算同一天的那一集。
    所以 Cloudflare Worker 準時觸發、或 GitHub 排程晚到好幾個小時，都對得上同一個 guid，不會重複發。

模式 mode：
    daily    美股交易日（週一到週五、非假日）
    holiday  週一到週五但美股休市 → 發簡短的休市簡報
    review   美東週六 → 本週回顧
    preview  美東週日 → 下週前瞻
環境變數 EPISODE_MODE 可強制指定（試跑或補發用）。

⚠️ HOLIDAYS / EARLY_CLOSE 是依 NYSE 公告整理，請在每年初對照官方公告核實後再修改此表：
    https://www.nyse.com/markets/hours-calendars
"""
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

__version__ = "1.6.0"

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")
TPE = ZoneInfo("Asia/Taipei")

# 休市日（日期 → 名稱）。週末本來就休市，不必列。
HOLIDAYS: dict[date, str] = {
    # 2026
    date(2026, 1, 1): "新年", date(2026, 1, 19): "馬丁路德金紀念日", date(2026, 2, 16): "總統日",
    date(2026, 4, 3): "耶穌受難日", date(2026, 5, 25): "國殤日", date(2026, 6, 19): "六月節",
    date(2026, 7, 3): "獨立紀念日（補假）", date(2026, 9, 7): "勞動節", date(2026, 11, 26): "感恩節",
    date(2026, 12, 25): "聖誕節",
    # 2027
    date(2027, 1, 1): "新年", date(2027, 1, 18): "馬丁路德金紀念日", date(2027, 2, 15): "總統日",
    date(2027, 3, 26): "耶穌受難日", date(2027, 5, 31): "國殤日", date(2027, 6, 18): "六月節（補假）",
    date(2027, 7, 5): "獨立紀念日（補假）", date(2027, 9, 6): "勞動節", date(2027, 11, 25): "感恩節",
    date(2027, 12, 24): "聖誕節（補假）",
}
# 提早在美東 13:00 收盤的日子
EARLY_CLOSE: dict[date, str] = {
    date(2026, 11, 27): "感恩節隔天", date(2026, 12, 24): "平安夜",
    date(2027, 11, 26): "感恩節隔天",
}

WEEKDAY_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def slot_date(now_utc: datetime) -> date:
    return (now_utc.astimezone(ET) - timedelta(hours=12)).date()


def holiday_name(d: date) -> str | None:
    return HOLIDAYS.get(d)


def episode_mode(now_utc: datetime) -> str:
    forced = (os.environ.get("EPISODE_MODE") or "").strip().lower()
    if forced in ("daily", "review", "preview", "holiday"):
        return forced
    d = slot_date(now_utc)
    wd = d.weekday()
    if wd == 5:
        return "review"
    if wd == 6:
        return "preview"
    return "holiday" if d in HOLIDAYS else "daily"


def next_trading_day(d: date) -> date:
    n = d + timedelta(days=1)
    while n.weekday() >= 5 or n in HOLIDAYS:
        n += timedelta(days=1)
    return n


def last_trading_day(d: date) -> date:
    """d 之前（不含 d）最近的一個交易日。"""
    n = d - timedelta(days=1)
    while n.weekday() >= 5 or n in HOLIDAYS:
        n -= timedelta(days=1)
    return n


# ── 口語時間 ───────────────────────────────────────────────────────────
_HOUR_ZH = {1: "一", 2: "兩", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九",
            10: "十", 11: "十一", 12: "十二"}


def _hour_zh(h12: int) -> str:
    return _HOUR_ZH[h12]


def time_zh(dt: datetime) -> str:
    """口語時間，四捨五入到半點：『下午五點』『下午五點半』『凌晨十二點半』。"""
    minutes = dt.hour * 60 + dt.minute
    minutes = int(round(minutes / 30.0)) * 30
    h, m = divmod(minutes % (24 * 60), 60)
    if h < 6:
        period = "凌晨"
    elif h < 12:
        period = "早上"
    elif h == 12:
        period = "中午"
    elif h < 18:
        period = "下午"
    else:
        period = "晚上"
    h12 = h % 12 or 12
    return f"{period}{_hour_zh(h12)}點" + ("半" if m == 30 else "")


def three_zone_line(now_utc: datetime) -> str:
    et, pt, tpe = (now_utc.astimezone(z) for z in (ET, PT, TPE))
    return (f"現在是美國東岸時間{time_zh(et)}，西岸時間{time_zh(pt)}，台北時間{time_zh(tpe)}")


def date_zh(d: date) -> str:
    return f"{d.month}月{d.day}日{WEEKDAY_ZH[d.weekday()]}"


def is_after_hours_window(now_utc: datetime) -> bool:
    """現在是否在美東 16:00–20:00（盤後交易時段）。"""
    et = now_utc.astimezone(ET)
    return 16 <= et.hour < 20

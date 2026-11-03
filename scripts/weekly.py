"""
週末特別集用的工具（v1.4.0）

  episode_mode(now)        依「美國太平洋時間的傍晚日期」決定這集是 daily / review / preview
                           太平洋時間週六 → review（本週回顧）；週日 → preview（下週前瞻）
                           （不論用 UTC 01:00 或 22:30 發布，都落在同一天，行為一致）
  gather_digest(...)       從 R2 的全文頁 t/zh-TW/YYYYMMDD.md 讀回這週每天的播報稿
  環境變數 EPISODE_MODE    可強制指定 daily / review / preview（試跑或補發用）
"""
import logging, os, re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger(__name__)
__version__ = "1.5.1"

PT = ZoneInfo("America/Los_Angeles")
WEEKEND_MARKERS = ("週回顧", "下週前瞻")      # 標題含這些字的集數是特別集，不當作「本週素材」
TRANSCRIPT_DIR = "t/zh-TW"


def evening_date_pt(now_utc: datetime):
    """這次執行屬於「太平洋時間的哪一天傍晚」。
    GitHub 排程常延遲，UTC 01:00 的排程實際會在 UTC 05:30–07:30 跑，換成太平洋時間已逼近或越過午夜，
    直接取星期會差一天（v1.4.0 曾因此把週六回顧誤判成週日前瞻）。
    做法：先扣掉 4 小時再換算，這樣 UTC 05:00–10:00 都算前一個太平洋日的傍晚，UTC 22:30 排程則算當天。"""
    return (now_utc - timedelta(hours=4)).astimezone(PT)


def episode_mode(now_utc: datetime) -> str:
    forced = (os.environ.get("EPISODE_MODE") or "").strip().lower()
    if forced in ("daily", "review", "preview"):
        return forced
    wd = evening_date_pt(now_utc).weekday()   # 0=週一 … 5=週六 6=週日
    return {5: "review", 6: "preview"}.get(wd, "daily")


def _script_from_md(md: str) -> tuple[str, str]:
    """回傳 (標題, 播報稿正文)。格式見 main.build_transcript_md。"""
    lines = md.replace("\r\n", "\n").split("\n")
    title = lines[0].lstrip("# ").strip() if lines else ""
    body = "\n".join(lines[1:])
    body = body.split("## 本集參考的新聞來源")[0]
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    paras = [p for p in paras
             if "[收聽音頻]" not in p and not (p.startswith("_") and p.endswith("_"))]
    return title, "\n\n".join(paras)


def gather_digest(base_url: str, now_utc: datetime, days: int = 7,
                  max_chars_per_ep: int = 4000) -> tuple[str, int]:
    """讀回最近 days 天的平日播報稿，回傳 (合併文字, 集數)。找不到的日子直接略過。"""
    parts: list[str] = []
    for back in range(days, 0, -1):                       # 由舊到新
        d = now_utc - timedelta(days=back)
        key = f"{TRANSCRIPT_DIR}/{d.strftime('%Y%m%d')}.md"
        try:
            r = requests.get(f"{base_url.rstrip('/')}/{key}", timeout=20)
        except requests.RequestException as e:
            log.warning(f"   讀取 {key} 失敗：{type(e).__name__}")
            continue
        if r.status_code != 200:
            log.info(f"   {key}: HTTP {r.status_code}（略過）")
            continue
        title, script = _script_from_md(r.content.decode("utf-8", errors="replace"))
        if any(m in title for m in WEEKEND_MARKERS) or len(script) < 300:
            continue
        label = d.strftime("%Y-%m-%d")
        parts.append(f"【{label} 播報稿】\n{script[:max_chars_per_ep]}")
    log.info(f"   週彙整：讀到 {len(parts)} 集")
    return "\n\n".join(parts), len(parts)

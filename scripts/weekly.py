"""
週末特別集用的工具（v1.4.0）

  episode_mode(now)        （已移到 market.py）
  gather_digest(...)       從 R2 的全文頁 t/zh-TW/YYYYMMDD.md 讀回這週每天的播報稿
  環境變數 EPISODE_MODE    可強制指定 daily / review / preview（試跑或補發用）
"""
import logging, os, re
from datetime import datetime, timedelta

import requests

log = logging.getLogger(__name__)
__version__ = "1.6.0"

WEEKEND_MARKERS = ("本週回顧", "週回顧", "下週前瞻")      # 標題含這些字的集數是特別集，不當作「本週素材」
TRANSCRIPT_DIR = "t/zh-TW"


def episode_mode(now_utc: datetime) -> str:
    """v1.6.0 起由 market.py 決定（美東時間；含休市日）。保留此函式讓舊程式碼不會壞。"""
    import market
    return market.episode_mode(now_utc)


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


def gather_digest(base_url: str, slot, days: int = 7, max_chars_per_ep: int = 4000) -> tuple[str, int]:
    """讀回 slot（集數的美東交易日，date 物件）之前 days 天的播報稿，回傳 (合併文字, 集數)。"""
    parts: list[str] = []
    for back in range(days, 0, -1):                       # 由舊到新
        d = slot - timedelta(days=back)
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
        parts.append(f"【{d.strftime('%Y-%m-%d')} 播報稿】\n{script[:max_chars_per_ep]}")
    log.info(f"   週彙整：讀到 {len(parts)} 集")
    return "\n\n".join(parts), len(parts)

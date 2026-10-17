# scripts/main.py  (v1.2.0)
import asyncio, html, logging, os, re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

__version__ = "1.2.0"

# 讓 analyzer.py 的 log.info 也會顯示在 GitHub Actions 日誌
logging.basicConfig(level=logging.INFO, format="%(message)s")

from fetcher  import fetch_all
import analyzer as _an
from analyzer import build_script
from tts      import to_mp3
from r2       import upload_file, upload_text

# publish.py 在同一個 scripts/ 目錄，直接 import
from publish  import update_rss_feed, load_queue, save_queue

# ── 路徑：scripts/ 內執行，feed.xml 在上一層根目錄 ──────────────────
ROOT      = Path(__file__).parent.parent   # repo 根目錄
FEED_PATH = ROOT / "feed.xml"
QUEUE_PATH = ROOT / "episodes_queue.json"

# publish.py 裡的 FEED_PATH / QUEUE_PATH 是字串常數，需要覆蓋
import publish as _pub
_pub.FEED_PATH  = str(FEED_PATH)
_pub.QUEUE_PATH = str(QUEUE_PATH)

_GUID_RE  = re.compile(r"<guid[^>]*>(.*?)</guid>", re.S)
_BARE_AMP = re.compile(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)")


def already_published(url: str) -> bool:
    """feed.xml 是否已有這個 guid（guid 就是 mp3 網址）。"""
    if not FEED_PATH.exists():
        return False
    xml = FEED_PATH.read_text(encoding="utf-8")
    return any(html.unescape(g.strip()) == url for g in _GUID_RE.findall(xml))


def dedupe_feed(path: Path) -> tuple[int, int]:
    """
    最後一道保險，回傳 (移除的重複集數, 修正的 & 數量)：
    1. 依 <guid> 去除重複的 <item>（保留第一次出現 = 最新那筆）。
    2. 把未跳脫的 & 改成 &amp;（舊集數裡的 AT&T 會讓整份 RSS 變成非法 XML）。
    3. 用 XML 解析器驗證；仍不合法就丟例外，避免把壞掉的 feed 上傳到 R2。
    """
    xml = path.read_text(encoding="utf-8")
    seen: set[str] = set()
    removed = 0

    def _keep_first(m: re.Match) -> str:
        nonlocal removed
        g = _GUID_RE.search(m.group(0))
        if not g:
            return m.group(0)
        guid = html.unescape(g.group(1).strip())
        if guid in seen:
            removed += 1
            return ""
        seen.add(guid)
        return m.group(0)

    new_xml = re.sub(r"<item>.*?</item>", _keep_first, xml, flags=re.S)
    new_xml, fixed_amp = _BARE_AMP.subn("&amp;", new_xml)
    ET.fromstring(new_xml.encode("utf-8"))   # 不合法會在這裡丟 ParseError

    if new_xml != xml:
        path.write_text(new_xml, encoding="utf-8")
    return removed, fixed_amp


async def main():
    print(f"版本：main {__version__} | analyzer {getattr(_an, '__version__', '?')} "
          f"| publish {getattr(_pub, '__version__', '?')}")

    # 日期（UTC）
    now      = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    disp     = now.strftime("%Y年%-m月%-d日")
    base_url = os.environ["R2_PUBLIC_URL"].rstrip("/")
    mp3_key  = f"ep_{date_str}.mp3"
    episode_url = f"{base_url}/{mp3_key}"

    print(f"=== {disp} 晨報開始 ===")

    # ⓪ 防重複：今天的集數已經在 feed 裡就不再重做
    #    手動按 Run workflow（workflow_dispatch）或設 FORCE_REBUILD=1 才會強制重做並原地更新
    force = (os.environ.get("FORCE_REBUILD") == "1"
             or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch")
    if already_published(episode_url) and not force:
        print(f"⏭️  今天（{disp}）的集數已在 feed.xml，跳過。"
              "（要重做：手動 Run workflow，或設定 FORCE_REBUILD=1）")
        return

    # ① 抓取 RSS
    print("① 抓取中...")
    items = fetch_all()
    print(f"   共 {len(items)} 則原始條目")

    # ② AI 生成播報稿
    print("② 生成播報稿...")
    script = build_script(items, disp)
    print(f"   {len(script)} 字")

    # ③ TTS → MP3（存到 /tmp 避免汙染 repo）
    print("③ TTS 生成音頻...")
    mp3_path = f"/tmp/ep_{date_str}.mp3"
    duration = await to_mp3(script, mp3_path)

    # ④ 上傳 MP3 到 R2
    print("④ 上傳 R2...")
    upload_file(mp3_path, mp3_key, "audio/mpeg")

    # ⑤ 組成 episode dict（符合 publish.py 的格式）
    episode = {
        "title":        f"{disp} 美股科技晨報",
        "url":          episode_url,
        "size":         Path(mp3_path).stat().st_size,
        "content_type": "audio/mpeg",
        "pubDate":      format_datetime(now),
        "description":  script[:300],
        "guid":         f"ep_{date_str}",
    }

    # ⑥ 寫入本地 feed.xml（publish.py v1.2.0：同 guid 取代，不重複追加）
    print("⑤ 更新 feed.xml...")
    if not update_rss_feed(episode):
        raise RuntimeError("update_rss_feed 失敗，中止（不上傳 R2 的 feed.xml）")

    # ⑥-b 保險：去重、修正舊集數的 &、驗證 XML 合法
    removed, fixed_amp = dedupe_feed(FEED_PATH)
    if removed:
        print(f"   已移除 {removed} 筆重複 guid 的集數")
    if fixed_amp:
        print(f"   已修正 {fixed_amp} 處未跳脫的 &")

    # ⑦ 上傳 feed.xml 到 R2（讓播客平台能讀到最新 RSS）
    with open(FEED_PATH, "r", encoding="utf-8") as f:
        xml = f.read()
    upload_text(xml, "feed.xml", "application/rss+xml; charset=utf-8")
    print(f"   RSS 已上傳：{base_url}/feed.xml")

    # ⑧ 更新 episodes_queue.json 歷史紀錄（同 guid 只保留最新一筆）
    queue = load_queue()
    published = [e for e in queue.get("published", [])
                 if e.get("guid") != episode["guid"]]
    published.append(episode)
    queue["published"] = published
    save_queue(queue)

    print(f"\n✅ 完成！")
    print(f"   MP3 : {base_url}/{mp3_key}")
    print(f"   RSS : {base_url}/feed.xml")


if __name__ == "__main__":
    asyncio.run(main())

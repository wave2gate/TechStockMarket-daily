"""
publish.py (v1.2.1)
把集數寫入 feed.xml。

v1.2.1：
- 若 episode 帶有 description_html，額外寫入 <content:encoded>（HTML 版說明，含可點連結）；
  <description> 仍是純文字版。兩者內容一致，用來觀察各平台實際讀哪一個。
- feed 缺少 xmlns:content 命名空間時自動補上。

v1.2.0：
- upsert：同一個 guid 已存在就「取代」，不再重複追加（這是重複 guid 的根源）
- 標題 / 描述 / 網址一律做 XML 跳脫（AT&T 之類的 & 不會再讓整份 RSS 失效）
- 不再每次多塞一堆空白行
"""
import json
import os
import re
from xml.sax.saxutils import escape, quoteattr, unescape

__version__ = "1.2.1"

QUEUE_PATH = "episodes_queue.json"
FEED_PATH = "feed.xml"

_ITEM_RE = re.compile(r"<item>.*?</item>", re.S)
_GUID_RE = re.compile(r"<guid[^>]*>(.*?)</guid>", re.S)
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # XML 1.0 不允許的控制字元
_CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


def load_queue():
    if not os.path.exists(QUEUE_PATH):
        return {"pending": [], "published": []}
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def _clean(text: str) -> str:
    return _CTRL_RE.sub("", text or "")


def _cdata(text: str) -> str:
    """CDATA 區塊；內文若剛好含 ]]> 會被拆開，避免提早結束。"""
    return "<![CDATA[" + _clean(text).replace("]]>", "]]&gt;") + "]]>"


def _build_item(episode) -> str:
    title = escape(_clean(episode["title"]))
    desc = escape(_clean(episode.get("description") or ("本集講解：" + episode["title"])))
    url = episode["url"]
    html_desc = episode.get("description_html")
    content_encoded = (
        f"      <content:encoded>{_cdata(html_desc)}</content:encoded>\n" if html_desc else ""
    )
    return (
        "<item>\n"
        f"      <title>{title}</title>\n"
        f"      <description>{desc}</description>\n"
        f"{content_encoded}"
        f"      <pubDate>{episode['pubDate']}</pubDate>\n"
        f"      <guid>{escape(url)}</guid>\n"
        f"      <enclosure url={quoteattr(url)} length=\"{int(episode['size'])}\" "
        f"type={quoteattr(episode['content_type'])}/>\n"
        "      <itunes:explicit>no</itunes:explicit>\n"
        "    </item>"
    )


def update_rss_feed(episode):
    if not os.path.exists(FEED_PATH):
        print(f"❌ 找不到 {FEED_PATH}")
        return False

    with open(FEED_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # guid 沿用 mp3 網址（與歷史集數一致，不可改，否則播客平台會視為新集數）
    guid = episode["url"]
    new_item = _build_item(episode)

    # <content:encoded> 需要 xmlns:content；舊 feed 已有就不動
    if "<content:encoded>" in new_item and "xmlns:content=" not in content:
        content = content.replace("<rss ", f'<rss xmlns:content="{_CONTENT_NS}" ', 1)

    state = {"replaced": 0, "dropped": 0}

    def _swap(m: re.Match) -> str:
        g = _GUID_RE.search(m.group(0))
        if g and unescape(g.group(1).strip(), {"&quot;": '"', "&apos;": "'"}) == guid:
            if state["replaced"] == 0:
                state["replaced"] = 1      # 第一筆：原地取代
                return new_item
            state["dropped"] += 1          # 其餘同 guid 的：刪除
            return ""
        return m.group(0)

    content = _ITEM_RE.sub(_swap, content)

    if not state["replaced"]:
        idx = content.find("<item>")
        insert_at = idx if idx != -1 else content.find("</channel>")
        if insert_at == -1:
            print("❌ feed.xml 格式異常，缺少 <item> 或 </channel>")
            return False
        content = content[:insert_at] + new_item + "\n    " + content[insert_at:]
        print("   ➕ 已新增集數")
    else:
        print("   ♻️  feed 內已有同 guid 的集數，已原地更新（未重複新增）")
    if state["dropped"]:
        print(f"   🧹 另外移除 {state['dropped']} 筆同 guid 的重複集數")

    # 連續 2 行以上空白行壓成 1 行（舊版每次執行都會多留一堆空白行）
    content = re.sub(r"(?:[ \t]*\n){3,}", "\n\n", content)

    with open(FEED_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def main():
    queue = load_queue()
    pending = queue.get("pending", [])

    if not pending:
        print("ℹ️  佇列裡沒有待發布的集數，結束")
        return

    print(f"📁 發現 {len(pending)} 集待發布")
    still_pending = []

    for episode in pending:
        print(f"\n🎵 處理: {episode['title']}")
        if update_rss_feed(episode):
            queue.setdefault("published", []).append(episode)
            print(f"✅ {episode['title']} 已寫入 feed.xml")
        else:
            still_pending.append(episode)

    queue["pending"] = still_pending
    save_queue(queue)
    print("\n✅ 全部處理完成")


if __name__ == "__main__":
    main()

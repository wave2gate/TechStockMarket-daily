# scripts/main.py  (v1.5.0)
import asyncio, html, logging, os, re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

__version__ = "1.5.0"

# 讓 analyzer.py 的 log.info 也會顯示在 GitHub Actions 日誌
logging.basicConfig(level=logging.INFO, format="%(message)s")

from fetcher  import fetch_all
import analyzer as _an
from analyzer import build_script
from tts      import to_mp3
from weekly   import episode_mode, gather_digest
import pipeline as _pl
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


# ══════════════════════════════════════════════════════════════════════
#  說明欄與全文頁（v1.2.1）
# ══════════════════════════════════════════════════════════════════════
def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, "") or default)
        return v if v >= 300 else default
    except ValueError:
        return default


# 說明欄字符上限。試驗值 4000；想調整不用改程式，在 workflow 的 env 加 DESC_MAX_CHARS 即可。
DESC_MAX_CHARS = _env_int("DESC_MAX_CHARS", 4000)
SHOW_NAME      = os.environ.get("POD_TITLE") or "美股科技收盤簡報"
TRANSCRIPT_DIR = "t/zh-TW"        # R2 上的全文頁資料夾（之後英文版用 t/en-US）
AI_NOTICE      = "本內容由 AI 協助整理並以合成語音播出，僅供參考，不構成投資建議。"
LINK_LABEL     = "全文與新聞來源："

_ENDERS  = "。！？!?"
_CLOSERS = "」』”’)）\"'"
_GREET_RE = re.compile(r"歡迎收聽|欢迎收听|Welcome to", re.I)


def _paragraphs(script: str) -> list[str]:
    s = script.replace("\r\n", "\n").replace("\r", "\n").strip()
    return [p.strip() for p in re.split(r"\n\s*\n", s) if p.strip()]


def _sentences(text: str) -> list[str]:
    """依句號等切句，把所有片段接回去等於原文（不遺失任何字）。"""
    out, start, i, n = [], 0, 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _ENDERS or (ch == "." and (i + 1 >= n or text[i + 1].isspace())):
            i += 1
            while i < n and (text[i] in _ENDERS or text[i] in _CLOSERS):
                i += 1
            out.append(text[start:i])
            start = i
        else:
            i += 1
    if start < n:
        out.append(text[start:])
    return out


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """在句界把 text 截到 limit 字符內。回傳 (文字, 是否被截斷)。"""
    if len(text) <= limit:
        return text, False
    if limit <= 0:
        return "", True
    acc = ""
    for s in _sentences(text):
        if len(acc) + len(s) > limit:
            break
        acc += s
    if len(acc) < limit * 0.4:                 # 第一句就太長：只好硬切並加省略號
        acc = text[: max(limit - 1, 0)].rstrip() + "…"
    return acc.rstrip(), True


LEAD_MAX = 320      # 導語最長字符數；第一段超過這個長度就在句界切開，讓連結盡量靠前


def _take_lead(par: str) -> tuple[str, str]:
    """第一段夠短就整段當導語；太長（或 AI 沒分段）就取前幾句（約 150 字），其餘留給內文。"""
    if len(par) <= LEAD_MAX:
        return par, ""
    sents, lead, k = _sentences(par), "", 0
    while k < len(sents):
        s = sents[k]
        if lead and (len(lead) >= 150 or len(lead) + len(s) > LEAD_MAX):
            break
        lead += s
        k += 1
    return lead.strip(), "".join(sents[k:]).strip()


def split_script(script: str) -> tuple[str, list[str]]:
    """回傳 (導語, 其餘段落)。標準開場白（歡迎收聽…）不放進說明欄，讓預覽區直接看到內容。"""
    paras = _paragraphs(script)
    if len(paras) > 1 and len(paras[0]) <= 120 and _GREET_RE.search(paras[0]):
        paras = paras[1:]
    if not paras:
        return "", []
    lead, remainder = _take_lead(paras[0])
    return lead, ([remainder] if remainder else []) + paras[1:]


def build_notes(script: str, transcript_url: str | None,
                max_chars: int = DESC_MAX_CHARS) -> tuple[str, str, bool]:
    """
    組出說明欄，回傳 (純文字版, HTML 版, 是否被截斷)。結構：
        導語（第一段，預覽區看得到）
        全文與新聞來源：<連結>          ← 放在前面，就算平台截斷也留得住
        其餘內文（超過上限就在句號處截斷）
        （後文請見全文連結）            ← 只有被截斷時才有
        AI 聲明
    純文字版放 <description>，HTML 版放 <content:encoded>，兩者內容一致。
    """
    sep = "\n\n"
    lead, rest_paras = split_script(script)
    link_line = f"{LINK_LABEL}{transcript_url}" if transcript_url else ""
    more = "（後文請見全文連結）" if transcript_url else "（後文略）"

    lead, _ = _truncate(lead, max(max_chars // 2, 100))      # 保險：導語本身過長
    head = sep.join(x for x in (lead, link_line) if x)
    rest_text = sep.join(rest_paras)

    truncated = False
    if rest_text and len(rest_text) > max_chars - (len(head) + len(AI_NOTICE) + 2 * len(sep)):
        avail = max_chars - (len(head) + len(AI_NOTICE) + 3 * len(sep) + len(more))
        rest_text, _ = _truncate(rest_text, max(avail, 0))
        truncated = True

    parts = [head, rest_text] + ([more] if truncated else []) + [AI_NOTICE]
    plain = sep.join(p for p in parts if p)

    # HTML 版：由純文字版逐段轉換，確保兩者一致
    blocks = []
    for chunk in plain.split(sep):
        if transcript_url and chunk == f"{LINK_LABEL}{transcript_url}":
            u = html.escape(transcript_url, quote=True)
            blocks.append(f'<p>{html.escape(LINK_LABEL)}<a href="{u}">{u}</a></p>')
        elif chunk == AI_NOTICE:
            blocks.append(f"<p><em>{html.escape(chunk)}</em></p>")
        else:
            blocks.append("<p>" + html.escape(chunk).replace("\n", "<br>") + "</p>")
    return plain, "".join(blocks), truncated


# ── 全文頁（HTML 給人讀，Markdown 方便日後貼到 Substack 等）──────────────
def _prompt_items(items: list[dict]) -> list[dict]:
    """與 analyzer 送給 AI 的條目一致：每個來源取前 N 則（N 讀 analyzer.ITEMS_PER_SOURCE，自動同步）。"""
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it.get("source", ""), []).append(it)
    out: list[dict] = []
    for its in groups.values():
        out.extend(its[:getattr(_an, "ITEMS_PER_SOURCE", 5)])
    return out


def _source_rows(items: list[dict]) -> list[tuple[str, str, str]]:
    rows = []
    for it in _prompt_items(items):
        url = (it.get("url") or "").strip()
        if url.startswith(("http://", "https://")):
            rows.append((it.get("source", ""), (it.get("title") or url).strip(), url))
    return rows


def build_transcript_html(title: str, script: str, items: list[dict], mp3_url: str) -> str:
    e = html.escape
    body = "\n".join("<p>" + e(p).replace("\n", "<br>") + "</p>" for p in _paragraphs(script))
    rows = "\n".join(
        f'<li><a href="{e(u, quote=True)}" rel="noopener nofollow">{e(t)}</a> <small>— {e(s)}</small></li>'
        for s, t, u in _source_rows(items)
    )
    sources = f"<h2>本集參考的新聞來源</h2>\n<ol>\n{rows}\n</ol>" if rows else ""
    return f"""<!doctype html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<style>
:root{{color-scheme:light dark}}
body{{font:17px/1.85 -apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;max-width:42rem;margin:0 auto;padding:1rem 16px 3rem}}
h1{{font-size:1.45rem;line-height:1.4;margin-bottom:.3rem}}
h2{{font-size:1.1rem;margin-top:2rem}}
.meta{{opacity:.7;font-size:.9rem;margin-top:0}}
audio{{width:100%;margin:.8rem 0 1.2rem}}
li{{margin:.45rem 0;word-break:break-word}}
small,.note{{opacity:.7}}
</style>
</head>
<body>
<h1>{e(title)}</h1>
<p class="meta">{e(SHOW_NAME)}</p>
<audio controls preload="none" src="{e(mp3_url, quote=True)}"></audio>
{body}
{sources}
<p class="note"><small>{e(AI_NOTICE)}新聞連結指向原網站，版權屬原作者。</small></p>
</body>
</html>
"""


def build_transcript_md(title: str, script: str, items: list[dict], mp3_url: str) -> str:
    lines = [f"# {title}", "", f"{SHOW_NAME}　[收聽音頻]({mp3_url})", ""]
    for para in _paragraphs(script):
        lines += [para, ""]
    rows = _source_rows(items)
    if rows:
        lines += ["## 本集參考的新聞來源", ""]
        lines += [f"{i}. [{t}]({u}) — {s}" for i, (s, t, u) in enumerate(rows, 1)]
        lines.append("")
    lines += [f"_{AI_NOTICE}新聞連結指向原網站，版權屬原作者。_", ""]
    return "\n".join(lines)


def publish_transcript(base_url: str, date_str: str, title: str, script: str,
                       items: list[dict], mp3_url: str) -> str | None:
    """上傳全文頁到 R2，回傳 HTML 的公開網址；任何失敗都只警告、不影響集數發布。"""
    key_html = f"{TRANSCRIPT_DIR}/{date_str}.html"
    key_md   = f"{TRANSCRIPT_DIR}/{date_str}.md"
    try:
        upload_text(build_transcript_md(title, script, items, mp3_url),
                    key_md, "text/markdown; charset=utf-8")
    except Exception as ex:
        print(f"   ⚠️ Markdown 全文上傳失敗（不影響發布）: {type(ex).__name__}")
    try:
        upload_text(build_transcript_html(title, script, items, mp3_url),
                    key_html, "text/html; charset=utf-8")
        return f"{base_url}/{key_html}"
    except Exception as ex:
        print(f"   ⚠️ 全文頁上傳失敗，說明欄將不附連結（不影響發布）: {type(ex).__name__}")
        return None


# ══════════════════════════════════════════════════════════════════════
#  feed 保險與主流程
# ══════════════════════════════════════════════════════════════════════
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
          f"| publish {getattr(_pub, '__version__', '?')} | pipeline {getattr(_pl, '__version__', '?')}")

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

    # ⓪-b 這集是日更、週六回顧還是週日前瞻（依美國太平洋時間的星期；EPISODE_MODE 可強制指定）
    mode = episode_mode(now)
    digest = ""
    if mode in ("review", "preview"):
        digest, n_eps = gather_digest(base_url, now, days=7,
                                      max_chars_per_ep=4000 if mode == "review" else 1500)
        need = 3 if mode == "review" else 2
        if n_eps < need:
            print(f"⚠️ 本週只讀到 {n_eps} 集播報稿（至少需要 {need}），改回日更模式")
            mode, digest = "daily", ""
    print(f"   本集模式：{mode}")

    # ① 抓取 RSS（週六回顧只用本週播報稿，不再抓新聞）
    if mode == "review":
        items = []
        print("① 週六回顧：略過新聞抓取")
    else:
        print("① 抓取中...")
        items = fetch_all()
        print(f"   共 {len(items)} 則原始條目")

    # ② AI 生成播報稿
    print("② 生成播報稿...")
    script = None
    if mode == "daily" and os.environ.get("TWO_STAGE", "1") != "0":
        try:                                    # 兩階段：分組筆記 → 統稿（pipeline.py）
            script = _pl.build_daily(items, disp)
        except Exception as ex:
            print(f"⚠️ 兩階段流程失敗，退回一次寫完：{str(ex)[:200]}")
    if script is None:
        script = build_script(items, disp, mode, digest)
    print(f"   {len(script)} 字（約 {len(script) / 300:.1f} 分鐘，以每分鐘 300 字估算）")

    # ③ TTS → MP3（存到 /tmp 避免汙染 repo）
    print("③ TTS 生成音頻...")
    mp3_path = f"/tmp/ep_{date_str}.mp3"
    duration = await to_mp3(script, mp3_path)

    # ④ 上傳 MP3 到 R2
    print("④ 上傳 R2...")
    upload_file(mp3_path, mp3_key, "audio/mpeg")

    # ④-b 全文頁（HTML + Markdown）存到 R2，說明欄會附上連結
    suffix = {"review": "｜本週回顧", "preview": "｜下週前瞻"}.get(mode, "")
    title = f"{disp} {SHOW_NAME}{suffix}"
    print("④-b 儲存全文頁...")
    transcript_url = publish_transcript(base_url, date_str, title, script, items, episode_url)
    if transcript_url:
        print(f"   全文頁：{transcript_url}")

    # ⑤ 組成 episode dict（符合 publish.py 的格式）
    notes_text, notes_html, truncated = build_notes(script, transcript_url, DESC_MAX_CHARS)
    print(f"   說明欄 {len(notes_text)} / {DESC_MAX_CHARS} 字符"
          f"（{'已在句界截斷' if truncated else '完整收錄，未截斷'}；全文 {len(script)} 字）")
    episode = {
        "title":            title,
        "url":              episode_url,
        "size":             Path(mp3_path).stat().st_size,
        "content_type":     "audio/mpeg",
        "pubDate":          format_datetime(now),
        "description":      notes_text,
        "description_html": notes_html,
        "guid":             f"ep_{date_str}",
    }

    # ⑥ 寫入本地 feed.xml（publish.py：同 guid 取代，不重複追加）
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
    print(f"   RSS 已上傳：{base_url}/feed.xml（{len(xml.encode('utf-8')) // 1024} KB）")

    # ⑧ 更新 episodes_queue.json 歷史紀錄（同 guid 只保留最新一筆）
    #    歷史紀錄只留 300 字摘要，完整說明欄與 HTML 不寫進 repo，避免檔案越來越大
    queue = load_queue()
    published = [e for e in queue.get("published", [])
                 if e.get("guid") != episode["guid"]]
    entry = {k: v for k, v in episode.items() if k != "description_html"}
    entry["description"] = script[:300]
    published.append(entry)
    queue["published"] = published
    save_queue(queue)

    print(f"\n✅ 完成！")
    print(f"   MP3 : {base_url}/{mp3_key}")
    print(f"   RSS : {base_url}/feed.xml")


if __name__ == "__main__":
    asyncio.run(main())

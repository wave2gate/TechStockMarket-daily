"""
試跑（v1.8.3）：完整跑一遍「抓新聞 → 筆記 → 統稿 → 防幻覺 → 加開場結尾」，
但不做 TTS、不上傳、不改 feed、不 commit。結果寫進 Actions 的 Summary 頁。

環境變數：
  EPISODE_MODE   daily / holiday / review / preview（空白＝依時間自動判斷）
  FAKE_NOW       假裝現在是這個 UTC 時間（例如 2026-11-06T22:00:00），用來測試週末／休市日；空白＝現在
  AUDIT=0        關閉 AI 審稿（只留程式核對數字）
  AUDIO=1        另外用 Edge TTS 合成語音，存成 ../trial_out/trial_episode.mp3（工作流程會附成可下載檔，不發布）
"""
import os, time, logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(message)s")
import analyzer, pipeline, fetcher, market, numcheck, episode, topics
from weekly import gather_digest


def main():
    fake = (os.environ.get("FAKE_NOW") or "").strip()
    now = datetime.fromisoformat(fake).replace(tzinfo=timezone.utc) if fake else datetime.now(timezone.utc)
    mode = market.episode_mode(now)
    slot = market.slot_date(now)
    digest, n_eps = "", 0
    if mode in ("review", "preview"):
        base = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")
        if base:
            digest, n_eps = gather_digest(base, slot, 7, 4000 if mode == "review" else 1500)
        if n_eps < 1:
            print("讀不到本週播報稿（試跑環境可能沒設 R2_PUBLIC_URL），改測 holiday 模式")
            mode, digest = "holiday", ""
    items = [] if mode == "review" else topics.tag_items(numcheck.prepare_items(fetcher.fetch_all()))
    counts: dict[str, int] = {}
    for it in items:
        counts[it["source"]] = counts.get(it["source"], 0) + 1
    print(f"模式 {mode}；美東交易日 {slot}；素材 {len(items)} 則；週彙整 {n_eps} 集")

    trace: list = []
    t0 = time.time()
    try:
        r = episode.build(now, mode, items, digest, trace)
        err = ""
    except Exception as e:
        r, err = None, f"{type(e).__name__}: {str(e)[:200]}"
    dt = time.time() - t0

    import re as _re, pathlib
    mods = []                       # 直接讀檔案裡的版本號（不 import，避免缺套件造成誤報）
    for m in ("main", "episode", "pipeline", "analyzer", "guard", "frame", "numcheck", "market", "topics", "fetcher", "weekly", "tts"):
        try:
            txt = (pathlib.Path(__file__).parent / f"{m}.py").read_text(encoding="utf-8")
            v = _re.search(r'__version__\s*=\s*"([^"]+)"', txt)
            mods.append(f"{m} {v.group(1) if v else '(無版本號)'}")
        except FileNotFoundError:
            mods.append(f"{m} 【檔案不存在】")
    out = [f"# 試跑結果（未發布）", "", "- 各模組版本：" + "、".join(mods),
           f"- 模式：**{mode}**　美東交易日：{slot}　假裝時間：{now:%Y-%m-%d %H:%M} UTC",
           f"- 版本：analyzer {analyzer.__version__} / pipeline {pipeline.__version__} / episode {episode.__version__}",
           f"- 耗時：{dt:.0f} 秒"]
    if err:
        out += ["", f"**失敗：{err}**"]
    else:
        u = r["used"]
        out += [f"- AI 原稿 {r['raw_len']} 字 → 清理後主體 {len(r['body'])} 字 → 全稿 {len(r['script'])} 字"
                f"（約 {len(r['script'])/300:.1f} 分鐘）",
                f"- 審稿狀態：{u['audit_status']}；審稿員：{u['auditor']}；刪除句數：{u['removed']}；保底稿：{u['safe_mode']}",
                f"- 統稿：{u['writer']}"]
        out += ["", "## 各組筆記提供商", ""] + [f"- {g['name']}：{g['provider']}（{g['model']}）" for g in u["groups"]]
        rep = r["report"]
        if rep.get("num_removed") or rep.get("ai_removed"):
            out += ["", "## 被刪除的句子（防幻覺關卡）", ""]
            out += [f"- 【數字】{x['sentence']}（{x['numbers']}）" for x in rep.get("num_removed", [])]
            out += [f"- 【審稿員】{x['sentence']}" for x in rep.get("ai_removed", [])]
        if r.get("english_words"):
            out += ["", "## 稿中殘留的小寫英文單字（觀察用，之後可加進置換表）", "", "、".join(r["english_words"])]
        out += ["", "## 完整稿件（朗讀內容）", "", r["script"]]
    if r and r.get("stats"):
        out += ["", r["stats"]["md"]]
        out += ["", "## 每則筆記是否進入成稿", ""] + [
            f"- {'✅' if c['covered'] else '❌'} [{c['bucket']}] ({c['source']}) {c['fact'][:110]}" for c in r["cov_rows"]]
    out += ["", "## 抓到的新聞分類結果（每個細項的標題）", ""]
    for k in topics.PRIORITY:
        ts = [it for it in items if it.get("bucket") == k]
        if ts:
            out.append(f"- **{k} {topics.NAMES[k]}**（{len(ts)}）：" + " ｜ ".join(f"{it['title'][:60]}（{it['source'].replace('Google News｜','GN:')}）" for it in ts[:6]))
    out += ["", "## 各來源抓到幾則", "", "| 來源 | 則數 |", "|---|---|"]
    out += [f"| {lab} | {counts.get(lab, 0)} |" for lab, _ in fetcher.SOURCES]
    out += ["", "## 來源診斷", "", "| 來源 | HTTP | 條目 | 時間窗內 | 最新一則 | 錯誤 |", "|---|---|---|---|---|---|"]
    for lab, d in fetcher.DIAG.items():
        out.append(f"| {lab} | {d['status']} | {d['entries']} | {d['fresh']} | {d['newest']} | {d['error']} |")
    for t in trace:
        if t.get("notes"):
            out += ["", f"## 筆記：{t['group']}（{t['provider']}）", ""]
            out += [f"- ({n['source']}, 重要度{n['score']}) {n['fact']} ／ 背景：{n['background']} ／ 影響：{n['impact']}" for n in t["notes"]]
    if os.environ.get("AUDIO") == "1" and r:
        import asyncio, tts
        os.makedirs("../trial_out", exist_ok=True)
        try:
            sec = asyncio.run(tts.to_mp3(r["script"], "../trial_out/trial_episode.mp3"))
            out.insert(4, f"- 語音：已合成 trial_episode.mp3（估算 {sec // 60} 分 {sec % 60} 秒），請到本頁最下方 Artifacts 下載收聽")
        except Exception as e:
            out.insert(4, f"- 語音合成失敗：{type(e).__name__}: {str(e)[:150]}")
    md = "\n".join(out)
    print(md)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        open(path, "a", encoding="utf-8").write(md + "\n")


if __name__ == "__main__":
    main()

"""
試跑（v1.5.0）：只測 AI，不做 TTS、不上傳、不改 feed、不 commit。
對每個已設定 Key 的提供商各生成一次播報稿，結果寫進 Actions 的 Summary 頁。
用環境變數 TRIAL_PROVIDERS 指定要測哪些：gemini / groq / cloudflare 各自單獨寫一份稿；
"pipeline" 則測兩階段流程（分組筆記 → 統稿），並列出各組筆記。
用環境變數 EPISODE_MODE 指定要測 daily / review / preview（空白＝依今天的星期自動判斷）。
"""
import os, sys, time, logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(message)s")
import analyzer
import pipeline
from fetcher import fetch_all
from weekly import episode_mode, gather_digest

KEYS = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY",
        "cloudflare": "CLOUDFLARE_API_TOKEN", "openrouter": "OPENROUTER_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY"}


def main():
    disp = datetime.now(timezone.utc).strftime("%Y年%-m月%-d日")
    now = datetime.now(timezone.utc)
    mode = episode_mode(now)
    digest, n_eps = "", 0
    if mode in ("review", "preview"):
        base = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")
        if base:
            digest, n_eps = gather_digest(base, now, 7, 4000 if mode == "review" else 1500)
        if n_eps < (3 if mode == "review" else 2):
            print(f"本週只讀到 {n_eps} 集播報稿，改測 daily")
            mode, digest = "daily", ""
    items = [] if mode == "review" else fetch_all()
    counts: dict[str, int] = {}
    for it in items:
        counts[it["source"]] = counts.get(it["source"], 0) + 1
    print(f"模式 {mode}；素材 {len(items)} 則；週彙整 {n_eps} 集")
    wanted = [x.strip() for x in os.environ.get("TRIAL_PROVIDERS", "pipeline").split(",") if x.strip()]
    rows, texts, extra_md = [], [], []
    for name in wanted:
        if name == "pipeline":
            os.environ.pop("PROVIDER_ORDER", None)
            trace: list = []
            t0 = time.time()
            try:
                text = pipeline.build_daily(items, disp, trace)
                rows.append(("pipeline（兩階段）", "成功", f"{len(text)}（約 {len(text)/300:.1f} 分鐘）", f"{time.time()-t0:.0f}s"))
                texts.append(("pipeline（兩階段）", text))
            except Exception as e:
                rows.append(("pipeline（兩階段）", f"失敗：{str(e)[:120]}", "-", f"{time.time()-t0:.0f}s"))
            stage = ["", "## 兩階段：各組筆記", "", "| 組別 | 提供商 | 結果 | 耗時 |", "|---|---|---|---|"]
            for t in trace:
                stage.append(f"| {t['group']} | {t['provider']} | {t['status']} | {t.get('seconds', '-')} |")
            for t in trace:
                for i, r in enumerate(t.get("notes", []), 1):
                    stage.append("")
                    stage.append(f"- **{t['group']} #{i}**（{r['source']}，重要度 {r['score']}）{r['fact']} ／ {r['background']} ／ {r['impact']}")
            extra_md.extend(stage)
            continue
        if not os.environ.get(KEYS.get(name, "")):
            rows.append((name, "未設定 Key", "-", "-")); continue
        os.environ["PROVIDER_ORDER"] = name        # 只用這一家，不降級
        t0 = time.time()
        try:
            text = analyzer.build_script(items, disp, mode, digest)
            rows.append((name, "成功", f"{len(text)}（約 {len(text)/300:.1f} 分鐘）", f"{time.time()-t0:.0f}s"))
            texts.append((name, text))
        except Exception as e:
            rows.append((name, f"失敗：{str(e)[:120]}", "-", f"{time.time()-t0:.0f}s"))
    out = [f"# AI 試跑結果（未發布）　模式：{mode}", "", "| 提供商 | 結果 | 字數 | 耗時 |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    src_rows = ["", "## 各來源抓到幾則（0 代表該 RSS 讀不到或太舊）", "", "| 來源 | 則數 |", "|---|---|"]
    all_src = [lab for lab, _ in __import__("fetcher").SOURCES]
    src_rows += [f"| {lab} | {counts.get(lab, 0) + counts.get(lab + '(alt)', 0)} |" for lab in all_src]
    out += src_rows + extra_md
    for name, text in texts:
        out += ["", f"## {name}", "", text]
    md = "\n".join(out)
    print(md)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        open(path, "a", encoding="utf-8").write(md + "\n")


if __name__ == "__main__":
    main()

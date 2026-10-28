"""
試跑（v1.3.0）：只測 AI，不做 TTS、不上傳、不改 feed、不 commit。
對每個已設定 Key 的提供商各生成一次播報稿，結果寫進 Actions 的 Summary 頁。
用環境變數 TRIAL_PROVIDERS 指定要測哪些（預設 "gemini,groq,cloudflare"）。
"""
import os, sys, time, logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(message)s")
import analyzer
from fetcher import fetch_all

KEYS = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY",
        "cloudflare": "CLOUDFLARE_API_TOKEN", "openrouter": "OPENROUTER_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY"}


def main():
    disp = datetime.now(timezone.utc).strftime("%Y年%-m月%-d日")
    items = fetch_all()
    print(f"素材 {len(items)} 則")
    wanted = [x.strip() for x in os.environ.get("TRIAL_PROVIDERS", "gemini,groq,cloudflare").split(",") if x.strip()]
    rows, texts = [], []
    for name in wanted:
        if not os.environ.get(KEYS.get(name, "")):
            rows.append((name, "未設定 Key", "-", "-")); continue
        os.environ["PROVIDER_ORDER"] = name        # 只用這一家，不降級
        t0 = time.time()
        try:
            text = analyzer.build_script(items, disp)
            rows.append((name, "成功", str(len(text)), f"{time.time()-t0:.0f}s"))
            texts.append((name, text))
        except Exception as e:
            rows.append((name, f"失敗：{str(e)[:120]}", "-", f"{time.time()-t0:.0f}s"))
    out = ["# AI 試跑結果（未發布）", "", "| 提供商 | 結果 | 字數 | 耗時 |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    for name, text in texts:
        out += ["", f"## {name}", "", text]
    md = "\n".join(out)
    print(md)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        open(path, "a", encoding="utf-8").write(md + "\n")


if __name__ == "__main__":
    main()

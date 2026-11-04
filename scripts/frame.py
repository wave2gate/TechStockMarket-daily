"""
節目的固定框架（v1.6.0）：開場、風險提醒、AI 署名、結尾祝福，全部由程式寫，不交給 AI。
這樣三地時間、日期、署名都不會被 AI 寫錯，而且署名反映的是「這一集實際上誰做了什麼」。
"""
from datetime import date, datetime

import market

__version__ = "1.6.0"

RISK = "市場波動來自技術面、消息面、機構資金等多重因素，請勿單憑新聞買賣股票，投資需謹慎。"
HEALTH = "無論走勢如何，請保持規律的作息與適度的運動，長期的心態比短線的漲跌更重要。"


def opening(now_utc: datetime, mode: str, slot: date) -> str:
    parts = ["各位聽眾朋友好，歡迎收聽美股科技收盤簡報。", market.three_zone_line(now_utc) + "。"]
    if mode == "daily":
        parts.append(f"這一集整理的是美東時間{market.date_zh(slot)}的美股收盤重點。")
        if slot in market.EARLY_CLOSE:
            parts.append(f"今天是{market.EARLY_CLOSE[slot]}，美股提早在下午一點收盤。")
        if market.is_after_hours_window(now_utc):
            parts.append("目前仍在盤後交易時段，盤後的價格與數字還可能變動。")
    elif mode == "holiday":
        parts.append(f"今天是美東時間{market.date_zh(slot)}，美股因{market.holiday_name(slot) or ('週末' if slot.weekday() >= 5 else '假日')}休市，"
                     "這一集是休市日的簡短簡報。")
        parts.append(f"下一個交易日是{market.date_zh(market.next_trading_day(slot))}。")
    elif mode == "review":
        parts.append("這一集是本週回顧，整理本週各個交易日的重點。")
    elif mode == "preview":
        parts.append("這一集是下週前瞻，整理本週的脈絡與下週值得留意的事件。")
    return "".join(parts)


def vendor(provider: str, model: str = "") -> str:
    p, m = (provider or "").lower(), (model or "").lower()
    if p == "gemini":
        return "Google 的 Gemini 模型"
    if p == "groq":
        return "OpenAI 開源的 gpt-oss 模型（在 Groq 平台上執行）" if "gpt-oss" in m else "Groq 平台上的開源模型"
    if p == "cloudflare":
        return "Meta 的 Llama 模型（在 Cloudflare 平台上執行）" if "llama" in m else "Cloudflare 平台上的開源模型"
    if p == "openrouter":
        return "OpenRouter 平台上的免費模型"
    if p == "deepseek":
        return "DeepSeek 模型"
    return provider or "人工智慧模型"


def credits(used: dict) -> str:
    """used 的格式見 episode.py。只講實際發生的事。"""
    parts: list[str] = []
    groups = used.get("groups") or []
    if groups:
        bits = []
        for g in groups:
            s = f"{g['name']}由{vendor(g['provider'], g.get('model', ''))}整理"
            if g.get("planned") and g["planned"] != g["provider"]:
                s += f"（原本由{vendor(g['planned'])}負責，因故改由它接手）"
            bits.append(s)
        parts.append("；".join(bits))
    w = used.get("writer")
    if used.get("safe_mode"):
        parts.append("這一集的稿件沒有交給人工智慧撰寫，是程式直接依據新聞筆記組成，所以文字比較樸素")
    elif w:
        parts.append(("全文由" if groups else "稿件由") + vendor(w["provider"], w.get("model", "")) + ("統稿" if groups else "撰寫"))
    a = used.get("auditor")
    status = used.get("audit_status", "")
    if a and status == "ok":
        parts.append(f"成稿再由{vendor(a['provider'], a.get('model', ''))}對照新聞審查")
    elif a and status == "same_model":
        parts.append("成稿由同一個模型自我審查，獨立性較低")
    elif status in ("skipped", "unreliable"):
        parts.append("這一集的交叉審查未能完成或結果不可靠，沒有採用")
    parts.append("另外由程式逐句核對數字" + (f"，並刪除了{used['removed']}句無法對照新聞的內容" if used.get("removed") else ""))
    parts.append("語音由微軟 Edge 的合成語音朗讀")
    return "最後交代一下這一集的製作。" + "；".join(parts) + "。內容僅供參考，如有疏漏，歡迎指正。"


def closing(mode: str, used: dict) -> str:
    wish_tail = {"review": "我們下週見！", "preview": "我們下週見！", "holiday": "我們下個交易日見！"}.get(mode, "我們明天見！")
    return "\n\n".join([RISK, HEALTH, credits(used),
                        "祝各位身體健康、投資順利，闔家平安，神愛世人，耶穌愛您，" + wish_tail])

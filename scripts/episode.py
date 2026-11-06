"""
一集稿件的總流程（v1.6.0）：主體（AI）→ 防幻覺關卡（guard）→ 加上開場與結尾（frame）。
任何一步失敗都有退路，最差也會產出「誠實但很短」的一集，不會編造。
環境變數：TWO_STAGE=0 關閉兩階段；AUDIT=0 關閉 AI 審稿（數字核對仍會執行）。
"""
import logging, os
from datetime import datetime

import analyzer as A
import frame
import guard
import market
import numcheck as N
import pipeline as P
import re
import topics as T

log = logging.getLogger(__name__)
__version__ = "1.8.2"

MINIMAL_BODY = "這一集的新聞整理沒有順利完成。我們不憑空補充內容，新聞來源請參考文字版頁面的連結。"
MIN_DAILY = guard.MIN_BODY_CHARS
MIN_OTHER = 100


_STOP = {"the", "and", "for", "with", "from", "that", "this", "its", "has", "have", "are", "was", "will", "new", "over",
         "after", "into", "more", "than", "about", "amid", "says", "said"}


MARK = r"[【\[（(]\s*N\d+(?:\s*[,、，/及和]\s*N?\d+)*\s*[】\]）)]"


def _normalize_marks(body: str) -> str:
    """AI 偶爾把標記放在句號後面：移到句號前面，才會跟著正確的句子（被刪句時標記一起消失）。"""
    return re.sub(r"([。！？])\s*((?:" + MARK + r"\s*)+)", lambda m: m.group(2).strip() + m.group(1), body)


def _marked_ids(body: str) -> set[int]:
    ids: set[int] = set()
    for m in re.finditer(MARK, body):
        ids |= {int(x) for x in re.findall(r"\d+", m.group(0))}
    return ids


def _strip_marks(body: str) -> str:
    return re.sub(r"\s*" + MARK, "", body)


def _is_covered(body: str, fact: str) -> bool:
    """這則筆記是否真的出現在成稿裡：比對事實中的專有名詞與數字；純中文事實改比對相鄰兩字。"""
    low = body.lower()
    toks = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9\.\-&]{2,}|\d[\d,\.]*\d|\d", fact)} - _STOP
    if toks:
        hit = sum(1 for t in toks if t in low)
        return hit >= min(2, len(toks))
    grams = {fact[i:i + 2] for i in range(len(fact) - 1)}
    return bool(grams) and sum(1 for g in grams if g in body) / len(grams) >= 0.4


def _source_text(items: list[dict], digest: str) -> str:
    parts = [digest] if digest else []
    for it in items:
        parts += [it.get("title", ""), it.get("summary", "") or "", it.get("ai_title", ""), it.get("ai_summary", "") or ""]
    return "\n".join(parts)


def build(now: datetime, mode: str, items: list[dict], digest: str = "", trace: list | None = None) -> dict:
    trace = trace if trace is not None else []
    slot = market.slot_date(now)
    date_zh = market.date_zh(slot)
    used: dict = {"groups": [], "writer": None, "auditor": None, "audit_status": "off",
                  "removed": 0, "safe_mode": False}
    pipe = None
    body = ""

    # ① 主體
    if mode in ("daily",) and os.environ.get("TWO_STAGE", "1") != "0":
        try:
            pipe = P.build_daily(items, date_zh, trace)
            body = pipe["body"]
            used["groups"], used["writer"] = pipe["groups"], pipe["writer"]
            if not body:        # 統稿失敗：不再用「一次寫完」重試，直接走保底稿（筆記已有）
                log.warning("⚠️ 統稿失敗，將使用保底稿")
        except Exception as ex:
            log.warning(f"⚠️ 兩階段流程失敗，退回一次寫完：{str(ex)[:200]}")
            pipe = None
    if not body and pipe is None:
        try:
            body = A.build_body(items, date_zh, mode, digest)
            w = A.LAST_WINNER["provider"]
            if body:
                used["writer"] = {"provider": w, "model": A.LAST_MODEL.get(w, "")}
        except Exception as ex:
            log.warning(f"⚠️ 稿件生成失敗：{str(ex)[:200]}")
            body = ""
    raw_len = len(body)

    if pipe and body:
        body = _normalize_marks(body)

    # ② 防幻覺：程式核對數字 + 另一個 AI 審稿，可疑句子直接刪除
    report: dict = {}
    if body:
        notes_text = pipe["notes_compact"] if pipe else (digest[:12000] if digest else A._items_block(items, date_zh))
        writer_key = (used["writer"] or {}).get("provider", "")
        body, report = guard.clean_body(body, [_source_text(items, digest)], notes_text, writer_key,
                                        enable_audit=os.environ.get("AUDIT", "1") != "0")
        used["auditor"], used["audit_status"], used["removed"] = (
            report.get("auditor"), report.get("audit_status", "off"), report.get("removed", 0))

    # ③ 太短 → 保底
    need = MIN_DAILY if mode == "daily" else MIN_OTHER
    if len(body) < need:
        safe = guard.safe_script(pipe["groups_notes"]) if pipe else ""
        if len(safe) > len(body):
            log.warning(f"⚠️ 清理後只剩 {len(body)} 字，改用保底稿（{len(safe)} 字，不經 AI 撰寫）")
            body, used["safe_mode"] = safe, True
        elif len(body) < 100:
            log.warning("⚠️ 沒有可用的內容，使用最短的誠實版本")
            body, used["safe_mode"], used["writer"] = MINIMAL_BODY, True, None
            used["auditor"], used["audit_status"] = None, "off"

    stats, cov_rows = None, []
    marked = _marked_ids(body)
    body = _strip_marks(body)                    # 標記只用來統計，絕不能被念出來
    if pipe:
        covered: dict[str, int] = {}
        for r in pipe["notes_all"]:
            ok = (r.get("id") in marked) or _is_covered(body, r["fact"])
            cov_rows.append({**r, "covered": ok})
            if ok:
                covered[r["bucket"]] = covered.get(r["bucket"], 0) + 1
        stats = T.render_stats(T.count_by_bucket(items), covered)

    script = "\n\n".join([frame.opening(now, mode, slot), body, frame.closing(mode, used)])
    return {"script": script, "body": body, "used": used, "report": report, "slot": slot,
            "mode": mode, "raw_len": raw_len, "pipe": pipe, "stats": stats, "cov_rows": cov_rows}

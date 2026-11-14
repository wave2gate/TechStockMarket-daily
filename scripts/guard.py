"""
防幻覺三道關（v1.6.0）
  1. 程式核對數字（numcheck）：金額、百分比、大數字必須能在素材找到，找不到的句子刪除。
  2. 另一個 AI 審稿：優先用「不是寫稿的那一家」，對照筆記挑出有筆記沒有的事實、原因、數字的句子，刪除。
  3. 保底：刪完太短、或 AI 全部失敗時，改用程式直接把筆記組成稿（safe_script），完全不經過 AI 撰寫。
設計原則：寧可短，也不要錯。可疑的句子一律「刪除」，不請 AI 改寫（改寫等於再給一次編造的機會）。
"""
import logging, os, re

import analyzer as A
import numcheck as N

log = logging.getLogger(__name__)
__version__ = "1.10.3"

MAX_FLAG_RATIO = 0.4        # 審稿員標記超過這個比例的句子，視為不可靠，整份審稿結果不採用
MIN_BODY_CHARS = int(os.environ.get("MIN_BODY_CHARS", "") or 500)
# 各家審稿時能吃的最大輸入（字元）：Groq 免費層每分鐘 token 有限，Cloudflare 上下文 24k tokens
_AUDIT_LIMIT = {"groq": 9000, "cloudflare": 16000, "gemini": 60000}
CHUNK = {"groq": 18, "cloudflare": 14, "gemini": 60}
_AUDIT_ORDER = ["groq", "cloudflare", "gemini"]

AUDIT_PROMPT = """你是嚴格的事實審稿員。下面有「新聞筆記」與「播報稿」（播報稿每句前面有編號）。
請找出播報稿中符合任一情況的句子，只輸出它們的編號：
1. 含有筆記裡沒有的具體事實、事件、人名、數字或日期；
2. 提出筆記沒有說過的原因、背景、技術指標、市場數據或預測；
3. 數字或單位與筆記不一致。
輸出格式：編號用逗號分隔，例如 3,7,12；完全沒有問題就只輸出 NONE。不要任何解釋。
不算違規：轉場句、開頭綜述的概括、以「可能」「值得留意」描述影響且沒有加入新事實的句子。"""


# ── 切句 ──────────────────────────────────────────────────────────────
def split_body(body: str) -> list[list[str]]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", body.replace("\r\n", "\n")) if p.strip()]
    return [[s.strip() for s in re.findall(r"[^。！？\n]+[。！？]?", p) if s.strip()] for p in paras]


def join_body(paras: list[list[str]]) -> str:
    return "\n\n".join("".join(p) for p in paras if p)


# ── AI 審稿 ───────────────────────────────────────────────────────────
def _available(provider: str) -> bool:
    if provider == "cloudflare":
        return bool(os.environ.get("CLOUDFLARE_API_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID"))
    return bool(os.environ.get(A._REGISTRY[provider][2]))


def _notes_for_chunk(notes_text: str, sents: list[str]) -> str:
    """只留這一批句子標記到的筆記（每行以 N編號. 開頭）；找不到標記就給全部。"""
    ids = {int(x) for s in sents for m in re.finditer(r"[【\[（(]\s*N[\d、,，/及和N\s]+[】\]）)]", s) for x in re.findall(r"\d+", m.group(0))}
    if not ids:
        return notes_text
    keep = [ln for ln in notes_text.splitlines() if not re.match(r"N\d+\.", ln) or int(re.match(r"N(\d+)\.", ln).group(1)) in ids]
    return "\n".join(keep)


def _audit_chunk(prov: str, numbered: list[str], notes_text: str, start: int) -> set[int]:
    script_block = "\n".join(f"[{start + i + 1}] {s}" for i, s in enumerate(numbered))
    prompt = f"{AUDIT_PROMPT}\n\n【新聞筆記】\n{_notes_for_chunk(notes_text, numbered)}\n\n【播報稿】\n{script_block}"
    if len(prompt) > _AUDIT_LIMIT.get(prov, 9000):
        raise ValueError(f"輸入太長（{len(prompt)} 字元）")
    text = A._REGISTRY[prov][1](prompt, 200)
    return {int(x) - 1 for x in re.findall(r"\d+", text) if start < int(x) <= start + len(numbered)}


def audit_ai(numbered: list[str], notes_text: str, writer: str) -> tuple[set[int], dict | None, str]:
    """v1.10.3 分段審稿：句子切成小批，每批只附相關筆記，Groq 也吃得下。
    回傳 (被標記的句子索引集合, 審稿者資訊, 狀態)。狀態：ok / same_model / skipped"""
    order = [p for p in _AUDIT_ORDER if p != writer and _available(p)]
    status = "ok"
    if not order and _available(writer):
        order, status = [writer], "same_model"
    for prov in order:
        size = CHUNK.get(prov, 20)
        flagged: set[int] = set()
        try:
            for st in range(0, len(numbered), size):
                flagged |= _audit_chunk(prov, numbered[st:st + size], notes_text, st)
        except Exception as ex:
            log.warning(f"   審稿：{prov} 失敗或輸入太長：{str(ex)[:150]}，換下一家")
            continue
        log.info(f"   審稿：{prov} 標記 {len(flagged)} 句（分 {-(-len(numbered) // size)} 批）")
        return flagged, {"provider": prov, "model": A.LAST_MODEL.get(prov, "")}, status
    return set(), None, "skipped"


# ── 主流程 ────────────────────────────────────────────────────────────
def clean_body(body: str, allowed_texts: list[str], notes_text: str, writer: str,
               enable_audit: bool = True) -> tuple[str, dict]:
    paras = split_body(body)
    flat = [(pi, si, s) for pi, p in enumerate(paras) for si, s in enumerate(p)]
    report = {"num_removed": [], "ai_removed": [], "auditor": None, "audit_status": "off",
              "sentences": len(flat), "removed": 0}
    if not flat:
        return body, report

    allowed = N.allowed_values(*allowed_texts, notes_text)
    drop: set[int] = set()
    for idx, (_, _, s) in enumerate(flat):
        bad = N.check_text(s, allowed)
        if bad:
            drop.add(idx)
            report["num_removed"].append({"sentence": s, "numbers": bad})

    if enable_audit:
        flagged, auditor, status = audit_ai([s for _, _, s in flat], notes_text, writer)
        report["auditor"], report["audit_status"] = auditor, status
        if len(flagged) > MAX_FLAG_RATIO * len(flat):
            log.warning(f"   審稿員標記 {len(flagged)}/{len(flat)} 句，太多，視為不可靠，未採用")
            report["audit_status"] = "unreliable"
        else:
            for i in sorted(flagged):
                if i not in drop:
                    drop.add(i)
                    report["ai_removed"].append({"sentence": flat[i][2]})

    for idx in drop:
        pi, si, _ = flat[idx]
        paras[pi][si] = ""
    report["removed"] = len(drop)
    return join_body([[s for s in p if s] for p in paras]), report


# ── 保底稿：完全不經過 AI 撰寫 ───────────────────────────────────────────
def safe_script(groups_notes: list[tuple[str, list[dict], str]]) -> str:
    """groups_notes: [(組名, 筆記列表, 語言)]；只用中文筆記（英文的不唸，避免半中半英）。"""
    out = []
    for name, notes, lang in groups_notes:
        if lang != "zh" or not notes:
            continue
        lines = [f"先來看{name}。"]
        for r in notes:
            fact = r["fact"].rstrip("。.")
            impact = r["impact"].rstrip("。.")
            bg = r.get("background", "").rstrip("。.")
            extra = "".join(f"{x}。" for x in (bg, impact) if x and x != "無")
            lines.append(f"{fact}。{extra}")
        out.append("".join(lines))
    return "\n\n".join(out)

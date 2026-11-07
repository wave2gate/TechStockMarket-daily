"""
TTS：Edge TTS 台灣女聲，返回音頻時長（秒）
"""
__version__ = "1.7.4"
import asyncio, logging, re
from pathlib import Path

import edge_tts

log     = logging.getLogger(__name__)
VOICE   = "zh-TW-HsiaoChenNeural"   # 台灣女聲
RATE    = "+0%"                      # 語速（+10% 稍快）
VOLUME  = "+0%"

def _clean(text: str) -> str:
    """移除 TTS 不該念的符號"""
    text = re.sub(r"[#*`~]",          "",  text)
    text = re.sub(r"\[([^\]]+)\]\S+", r"\1", text)   # markdown link
    text = re.sub(r"https?://\S+",    "",  text)       # URL
    text = re.sub(r"\n{3,}",          "\n\n", text)
    return text.strip()

async def to_mp3(script: str, out_path: str) -> int:
    """
    生成 MP3，返回估計時長（秒）。
    Edge TTS 不直接給時長，用字元數估算（中文與英數字分開計）。
    """
    clean = _clean(script)
    comm  = edge_tts.Communicate(clean, voice=VOICE, rate=RATE, volume=VOLUME)
    await comm.save(out_path)

    size_kb  = Path(out_path).stat().st_size // 1024
    char_cnt = len(clean)
    # 中文字約 4.8 字/秒，英數字（公司名、金額單位）念得快得多：依兩種字元分開估算（以實測 7:03 校正）
    cjk = len(re.findall(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]", clean))
    asc = len(re.findall(r"[A-Za-z0-9]", clean))
    duration = int(cjk * 0.223 + asc * 0.088)   # 估算秒數
    log.info(f"   TTS: {char_cnt} 字 → {size_kb} KB，估算 {duration//60}分{duration%60}秒")
    return duration

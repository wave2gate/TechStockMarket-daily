"""
TTS：Edge TTS 台灣女聲，返回音頻時長（秒）
"""
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
    Edge TTS 不直接給時長，用字數估算（實測台灣女聲約 280 字/分鐘）。
    """
    clean = _clean(script)
    comm  = edge_tts.Communicate(clean, voice=VOICE, rate=RATE, volume=VOLUME)
    await comm.save(out_path)

    size_kb  = Path(out_path).stat().st_size // 1024
    char_cnt = len(clean)
    duration = int(char_cnt / 280 * 60)   # 估算秒數
    log.info(f"   TTS: {char_cnt} 字 → {size_kb} KB，估算 {duration//60}分{duration%60}秒")
    return duration

import asyncio
import os
import re
import edge_tts
from src import config

def vtt_to_srt(vtt_content: str) -> str:
    """Converts WebVTT subtitle format to SRT format."""
    lines = vtt_content.strip().split('\n')
    srt_lines = []
    block_idx = 1
    
    # Skip the WEBVTT header and optional empty lines
    skip_header = True
    
    for line in lines:
        if skip_header:
            if line.startswith("WEBVTT") or line.strip() == "":
                continue
            skip_header = False
            
        # Match time range line: e.g. 00:00:01.000 --> 00:00:03.000
        time_match = re.match(r"(\d{2}:\d{2}:\d{2})\.(\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2})\.(\d{3})", line)
        if time_match:
            # VTT uses dot (.) for milliseconds, SRT uses comma (,)
            start_hms, start_ms, end_hms, end_ms = time_match.groups()
            srt_lines.append(str(block_idx))
            srt_lines.append(f"{start_hms},{start_ms} --> {end_hms},{end_ms}")
            block_idx += 1
        elif line.strip() != "":
            srt_lines.append(line)
        else:
            srt_lines.append("") # empty line separator between blocks
            
    return "\n".join(srt_lines)

def sanitize_voice_name(voice: str) -> str:
    """Extract short voice name from Microsoft full voice name if needed."""
    match = re.search(r"\(([^,]+),\s*([^)]+)\)", voice)
    if match:
        lang, name = match.groups()
        return f"{lang.strip()}-{name.strip()}"
    return voice

async def _run_tts_async(text: str, voice: str, rate: str, pitch: str, audio_path: str, srt_path: str):
    """Internal async runner for edge-tts using plain text."""
    voice = sanitize_voice_name(voice)
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch
    )
    submaker = edge_tts.SubMaker()
    
    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "Metadata":
                submaker.feed(chunk)
                
    # Save SRT subtitles directly using native submaker.get_srt()
    with open(srt_path, "w", encoding="utf-8") as srt_file:
        srt_file.write(submaker.get_srt())

def generate_voice_and_subs(text: str, chapter_id: str) -> tuple:
    """
    Generate MP3 voice file and SRT subtitles for a chapter.
    """
    audio_path = os.path.join(config.OUTPUT_DIR, f"{chapter_id}_raw.mp3")
    srt_path = os.path.join(config.OUTPUT_DIR, f"{chapter_id}.srt")
    
    print(f"[INFO] Synthesizing speech for chapter using voice {config.DEFAULT_VOICE}...")
    
    # Run the async loop inside the sync wrapper to generate audio and srt directly
    asyncio.run(_run_tts_async(
        text=text,
        voice=config.DEFAULT_VOICE,
        rate=config.DEFAULT_RATE,
        pitch=config.DEFAULT_PITCH,
        audio_path=audio_path,
        srt_path=srt_path
    ))
    
    return audio_path, srt_path

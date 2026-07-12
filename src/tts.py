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

async def _run_tts_async(text: str, audio_path: str, vtt_path: str, voice: str, rate: str, pitch: str):
    """Internal async runner for edge-tts."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    submaker = edge_tts.SubMaker()
    
    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "Metadata":
                submaker.feed(chunk)
                
    # Save VTT subtitles
    with open(vtt_path, "w", encoding="utf-8") as vtt_file:
        vtt_file.write(submaker.generate_subs())

def generate_voice_and_subs(text: str, chapter_id: str) -> tuple:
    """
    Generate MP3 voice file and SRT subtitles for a chapter.
    
    Args:
        text (str): Chapter content text.
        chapter_id (str): ID of the chapter.
        
    Returns:
        tuple: (audio_file_path, srt_file_path)
    """
    audio_path = os.path.join(config.OUTPUT_DIR, f"{chapter_id}_raw.mp3")
    vtt_path = os.path.join(config.OUTPUT_DIR, f"{chapter_id}.vtt")
    srt_path = os.path.join(config.OUTPUT_DIR, f"{chapter_id}.srt")
    
    print(f"[INFO] Synthesizing speech for chapter using voice {config.DEFAULT_VOICE}...")
    
    # Run the async loop inside the sync wrapper
    asyncio.run(_run_tts_async(
        text=text,
        audio_path=audio_path,
        vtt_path=vtt_path,
        voice=config.DEFAULT_VOICE,
        rate=config.DEFAULT_RATE,
        pitch=config.DEFAULT_PITCH
    ))
    
    # Convert VTT to SRT
    try:
        with open(vtt_path, 'r', encoding='utf-8') as vtt_file:
            vtt_content = vtt_file.read()
        srt_content = vtt_to_srt(vtt_content)
        with open(srt_path, 'w', encoding='utf-8') as srt_file:
            srt_file.write(srt_content)
        print("[INFO] Subtitles converted to SRT successfully.")
    except Exception as e:
        print(f"[WARNING] Failed to convert VTT to SRT: {e}. Keeping WebVTT only.")
        srt_path = vtt_path
        
    return audio_path, srt_path

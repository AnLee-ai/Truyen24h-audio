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

def get_proper_noun_words(chapter_id: str) -> list:
    """Fetch proper nouns (character names and lore keywords) from database for a chapter's novel."""
    words = ["Kaelen", "Vance", "Aegis", "Veridia", "Neo-Veridia", "Marcus"] # Default fallback
    try:
        from src import database
        client = database.get_client()
        res = client.table("chapters").select("novel_id").eq("id", chapter_id).execute()
        if not res.data:
            return words
        novel_id = res.data[0]["novel_id"]
        
        # Fetch character names
        chars = client.table("characters").select("name").eq("novel_id", novel_id).execute().data
        # Fetch world lore keywords
        lores = client.table("world_lore").select("keyword").eq("novel_id", novel_id).execute().data
        
        db_words = []
        if chars:
            for c in chars:
                db_words.extend([w.strip() for w in c["name"].split() if len(w.strip()) > 2])
        if lores:
            for l in lores:
                db_words.extend([w.strip() for w in l["keyword"].split() if len(w.strip()) > 2])
                
        if db_words:
            words.extend(db_words)
    except Exception as e:
        print(f"[WARNING] Failed to fetch proper nouns from database: {e}")
        
    unique_words = list(set(words))
    unique_words.sort(key=len, reverse=True)
    return unique_words

def get_full_voice_name(voice: str) -> str:
    """Map short voice name (e.g. vi-VN-HoaiMyNeural) to Microsoft full voice name."""
    if voice.startswith("Microsoft Server Speech"):
        return voice
    if len(voice) >= 7 and voice[5] == '-':
        lang = voice[:5]
        name = voice[6:]
        return f"Microsoft Server Speech Text to Speech Voice ({lang}, {name})"
    return voice

def text_to_ssml(text: str, chapter_id: str, voice: str, rate: str, pitch: str) -> str:
    """Wrap text in SSML and slow down English proper nouns."""
    # Escape XML special characters
    escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    try:
        words = get_proper_noun_words(chapter_id)
        for word in words:
            pattern = re.compile(r'(<[^>]+>)|(\b' + re.escape(word) + r'\b)', re.IGNORECASE)
            def subst(match):
                if match.group(1):
                    return match.group(1)
                else:
                    # Slow down English name pronunciation rate specifically by -25%
                    return f'<prosody rate="-25%">{match.group(2)}</prosody>'
            escaped_text = pattern.sub(subst, escaped_text)
    except Exception as e:
        print(f"[WARNING] Failed to format SSML: {e}")
        
    full_voice = get_full_voice_name(voice)
    return (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='vi-VN'>"
        f"<voice name='{full_voice}'>"
        f"<prosody rate='{rate}' pitch='{pitch}'>"
        f"{escaped_text}"
        f"</prosody>"
        f"</voice>"
        f"</speak>"
    )

async def _run_tts_async(ssml: str, audio_path: str, srt_path: str):
    """Internal async runner for edge-tts using SSML."""
    communicate = edge_tts.Communicate(ssml)
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
    
    Args:
        text (str): Chapter content text.
        chapter_id (str): ID of the chapter.
        
    Returns:
        tuple: (audio_file_path, srt_file_path)
    """
    audio_path = os.path.join(config.OUTPUT_DIR, f"{chapter_id}_raw.mp3")
    srt_path = os.path.join(config.OUTPUT_DIR, f"{chapter_id}.srt")
    
    print(f"[INFO] Synthesizing speech for chapter using voice {config.DEFAULT_VOICE}...")
    
    # Generate the customized SSML structure
    ssml = text_to_ssml(
        text=text,
        chapter_id=chapter_id,
        voice=config.DEFAULT_VOICE,
        rate=config.DEFAULT_RATE,
        pitch=config.DEFAULT_PITCH
    )
    
    # Run the async loop inside the sync wrapper to generate audio and srt directly
    asyncio.run(_run_tts_async(
        ssml=ssml,
        audio_path=audio_path,
        srt_path=srt_path
    ))
    
    return audio_path, srt_path

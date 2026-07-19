import json
import time
import re
import google.generativeai as genai
import sys
from src import config
from src import database
from templates import prompts

def safe_print(*args, **kwargs):
    """Override built-in print to prevent UnicodeEncodeError on Windows terminals."""
    msg = " ".join(str(arg) for arg in args)
    try:
        sys.stdout.write(msg + kwargs.get("end", "\n"))
        sys.stdout.flush()
    except UnicodeEncodeError:
        try:
            encoding = sys.stdout.encoding or 'utf-8'
            sys.stdout.write(msg.encode(encoding, errors='replace').decode(encoding) + kwargs.get("end", "\n"))
            sys.stdout.flush()
        except Exception:
            sys.stdout.write(msg.encode('ascii', errors='replace').decode('ascii') + kwargs.get("end", "\n"))
            sys.stdout.flush()

print = safe_print

# Configure Gemini API
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)

def safe_loads(text: str):
    """Safely parse JSON string, stripping markdown code block wrappers if present."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    return json.loads(cleaned)

def remove_repetitive_sentences(text: str) -> str:
    """Clean duplicate consecutive sentences or paragraphs."""
    paragraphs = text.split("\n")
    cleaned_paragraphs = []
    
    for para in paragraphs:
        if not para.strip():
            cleaned_paragraphs.append("")
            continue
        # Split paragraph into sentences
        # Matches ending punctuation followed by spaces or end of string
        sentences = re.split(r'(?<=[.?!])\s+', para)
        cleaned_sentences = []
        for sentence in sentences:
            s_strip = sentence.strip()
            if not s_strip:
                continue
            # Check if this sentence is a duplicate of the last added sentence
            if cleaned_sentences and cleaned_sentences[-1].strip().lower() == s_strip.lower():
                continue
            cleaned_sentences.append(sentence)
        cleaned_paragraphs.append(" ".join(cleaned_sentences))
        
    # Filter duplicate consecutive paragraphs
    final_paragraphs = []
    last_non_empty = None
    for p in cleaned_paragraphs:
        if not p.strip():
            if final_paragraphs and final_paragraphs[-1] == "":
                continue
            final_paragraphs.append("")
            continue
            
        if last_non_empty and last_non_empty.strip().lower() == p.strip().lower():
            continue # Skip duplicate paragraph
            
        final_paragraphs.append(p)
        last_non_empty = p
        
    return "\n".join(final_paragraphs)

def clean_chapter_content(text: str) -> str:
    """Clean draft content, stripping markdown and prefix headers like 'Dẫn lược:', 'Chương X:', etc."""
    cleaned = text.strip()
    
    # Remove markdown formatting and prefix headers at the start
    # e.g. **Dẫn lược:** or *Dẫn lược:* or Dẫn lược: or **Prologue:**
    pattern = r"^\s*(?:\*\*|\*|__|_)*\s*(?:Dẫn lược|Giới thiệu|Phần dẫn lược|Tóm tắt bối cảnh|Prologue|Introduction)\s*(?:\*\*|\*|__|_)*\s*[:：\-–—]\s*(?:\*\*|\*|__|_)*\s*"
    cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    
    # Clean consecutive duplicate sentences/paragraphs
    cleaned = remove_repetitive_sentences(cleaned)
    return cleaned

def call_gemini(prompt: str, json_mode: bool = False, retries: int = 3) -> str:
    """Helper to call LLM (Groq if key configured, otherwise Gemini API) with backoff."""
    use_groq = bool(config.GROQ_API_KEY)
    
    if use_groq:
        import requests
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": config.GROQ_MODEL_WRITER,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        if json_mode:
            data["response_format"] = {"type": "json_object"}
            
        groq_failed = False
        max_tokens_options = [3200, 2400, 1800] if not json_mode else [1000]
        
        for attempt in range(retries + 2):  # Increase retries for Groq to handle TPM limits
            current_max_tokens = max_tokens_options[min(attempt, len(max_tokens_options)-1)]
            data["max_tokens"] = current_max_tokens
            try:
                response = requests.post(url, json=data, headers=headers, timeout=120)  # type: ignore[arg-type]
                if response.status_code == 200:
                    resp_json = response.json()
                    content = resp_json["choices"][0]["message"]["content"]
                    if content:
                        return content.strip()
                
                # If rate limit (429) or payload too large / TPM limit (413) is hit:
                if response.status_code in (413, 429):
                    if not json_mode and current_max_tokens > 1800:
                        next_tokens = max_tokens_options[min(attempt+1, len(max_tokens_options)-1)]
                        print(f"[WARNING] Groq returned status {response.status_code}. Retrying with smaller max_tokens ({current_max_tokens} -> {next_tokens})...")
                        time.sleep(3)
                        continue
                    else:
                        print(f"[WARNING] Groq returned status {response.status_code} (Rate Limit/TPM Limit). Falling back to Gemini API...")
                        groq_failed = True
                        break
                
                raise RuntimeError(f"Groq API returned status {response.status_code}: {response.text}")
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "413" in err_msg:
                    if not json_mode and current_max_tokens > 1800:
                        print(f"[WARNING] Groq rate/TPM limit hit. Retrying with smaller max_tokens...")
                        time.sleep(3)
                        continue
                    else:
                        print(f"[WARNING] Groq rate/TPM limit hit: {err_msg}. Falling back to Gemini API...")
                        groq_failed = True
                        break
                else:
                    wait_time = (attempt + 1) * 5
                    print(f"[WARNING] Groq call failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        else:
            groq_failed = True
            
        if groq_failed:
            print("[INFO] Initiating automatic fallback to Gemini API...")
            # Fall through to Gemini API execution below!

    # Fallback to Gemini API
    model_name = config.GEMINI_MODEL_WRITER
    generation_config = {
        "max_output_tokens": 8192  # Allow up to 8192 output tokens for complete long chapters
    }
    
    if json_mode:
        generation_config["response_mime_type"] = "application/json"
        
    model = genai.GenerativeModel(model_name, generation_config=generation_config)
    
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            if response.text:
                return response.text.strip()
            raise ValueError("Empty response from Gemini API.")
        except Exception as e:
            wait_time = (attempt + 1) * 10
            print(f"[WARNING] Gemini call failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            
    raise RuntimeError("Max retries exceeded calling Gemini API.")

def get_embedding(text: str) -> list:
    """Generate vector embedding for semantic search using text-embedding-004."""
    try:
        result = genai.embed_content(
            model=f"models/{config.GEMINI_MODEL_EMBED}",
            content=text,
            task_type="retrieval_document"
        )
        emb = result['embedding']
        # Force exactly 1536 dimensions to match database schema
        if len(emb) > 1536:
            return emb[:1536]
        elif len(emb) < 1536:
            return emb + [0.0] * (1536 - len(emb))
        return emb
    except Exception as e:
        print(f"[ERROR] Failed to generate embedding: {e}")
        # Return a dummy 1536-dim vector if it fails
        return [0.0] * 1536

# Novel Lifecycle Operations
def init_novel_pipeline(title: str, description: str) -> dict:
    """Initialize a novel: create Supabase record and generate global outline."""
    print(f"[INFO] Initializing new novel: '{title}'...")
    
    # 1. Save novel metadata to Supabase
    novel = database.init_novel(title, description)
    novel_id = novel["id"]
    print(f"[INFO] Created novel record in database. ID: {novel_id}")
    
    # Generate expanded plot summary in Vietnamese and update description
    try:
        print("[INFO] Generating expanded plot summary in Vietnamese...")
        plot_prompt = prompts.PLOT_EXPANSION_PROMPT.format(title=title, description=description)
        detailed_plot = call_gemini(plot_prompt)
        database.update_novel_description(novel_id, detailed_plot)
        novel["description"] = detailed_plot  # Update local novel object description
        print("[INFO] Expanded plot summary stored in novels table.")
    except Exception as e:
        print(f"[WARNING] Failed to generate/store expanded plot summary: {e}")
    
    # 2. Generate Global Outline (JSON of Arcs) using the detailed plot context
    prompt = prompts.OUTLINE_PROMPT.format(title=title, description=novel["description"])
    outline_json = call_gemini(prompt, json_mode=True)
    
    try:
        outline = safe_loads(outline_json)
        # Update novel description to store the structured outline
        database.upsert_narrative_thread(
            novel_id=novel_id,
            thread_name="Global Outline",
            description=json.dumps(outline, ensure_ascii=False)
        )
        print("[INFO] Global Outline generated and stored successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to parse global outline JSON: {e}. Raw content: {outline_json}")
        # Store as raw text if parsing fails
        database.upsert_narrative_thread(
            novel_id=novel_id,
            thread_name="Global Outline",
            description=outline_json
        )
        
    return novel

def generate_arc_blueprints(novel_id: str, arc: dict) -> list:
    """Generate chapter-by-chapter blueprints for a specific story arc."""
    arc_num = arc.get("arc_number")
    arc_title = arc.get("title")
    start_ch = arc.get("start_chapter")
    end_ch = arc.get("end_chapter")
    arc_summary = arc.get("summary", "Tiếp tục diễn biến của bối cảnh học viện.")
    
    print(f"[INFO] Generating blueprints for Arc {arc_num}: '{arc_title}' (Chapters {start_ch} - {end_ch})...")
    
    # Fetch novel info for context
    novel = database.get_novel(novel_id)
    novel_title = novel.get("title", "Truyện mới")
    novel_description = novel.get("description", "")
    
    # Fetch existing chapters to inform the arc planner of current status
    existing_chapters = database.get_all_chapters(novel_id)
    status_summary = f"Written {len(existing_chapters)} chapters."
    if existing_chapters:
        status_summary += f" Latest chapter was: {existing_chapters[-1]['title']}"
        
    prompt = prompts.ARC_PROMPT.format(
        novel_title=novel_title,
        novel_description=novel_description,
        arc_summary=arc_summary,
        arc_number=arc_num,
        arc_title=arc_title,
        start_chapter=start_ch,
        end_chapter=end_ch,
        global_status=status_summary
    )
    
    blueprints_json = call_gemini(prompt, json_mode=True)
    
    try:
        try:
            blueprints = safe_loads(blueprints_json)
            if not isinstance(blueprints, list):
                raise ValueError("Parsed blueprints is not a list")
        except Exception as e:
            print(f"[WARNING] Failed to parse blueprints JSON: {e}. Attempting recovery...")
            blueprints = []
            # Find complete JSON blocks for chapters in the raw response
            matches = re.findall(r"\{\s*\"chapter_number\"[\s\S]*?\}", blueprints_json)
            for m in matches:
                try:
                    ch_obj = json.loads(m)
                    if isinstance(ch_obj, dict):
                        blueprints.append(ch_obj)
                except Exception:
                    try:
                        ch_obj = safe_loads(m)
                        if isinstance(ch_obj, dict):
                            blueprints.append(ch_obj)
                    except Exception:
                        pass

        # If still empty, create a default placeholder
        if not blueprints:
            print("[WARNING] Could not recover any blueprints. Creating default placeholder.")
            blueprints = [{
                "chapter_number": start_ch or 1,
                "chapter_title": "Khởi Đầu Mới",
                "blueprint": "Bắt đầu câu chuyện, giới thiệu nhân vật và thế giới học viện.",
                "characters_present": [],
                "narrative_goal": "Giới thiệu bối cảnh"
            }]

        inserted_chapters = []
        for ch_data in blueprints:
            if not isinstance(ch_data, dict):
                continue
            ch_num = ch_data.get("chapter_number")
            ch_title = ch_data.get("chapter_title") or "Chương Tiếp Theo"
            blueprint_text = ch_data.get("blueprint") or "Tiếp tục diễn biến câu chuyện."
            
            # Save chapter blueprint as initial content placeholder
            ch_record = database.create_chapter(
                novel_id=novel_id,
                chapter_number=ch_num,
                title=ch_title,
                content=f"BLUEPRINT: {blueprint_text}"
            )
            inserted_chapters.append(ch_record)
            
        print(f"[INFO] Created {len(inserted_chapters)} chapter blueprints in DB.")
        return inserted_chapters
    except Exception as e:
        print(f"[ERROR] Failed to generate/parse blueprints for Arc {arc_num}: {e}")
        return []

def get_current_arc(novel_id: str, chapter_number: int) -> dict:
    """Find which arc the chapter belongs to based on the stored Global Outline."""
    threads = database.get_narrative_threads(novel_id)
    outline_thread = next((t for t in threads if t["thread_name"] == "Global Outline"), None)
    if not outline_thread:
        return {}
        
    try:
        outline = json.loads(outline_thread["description"])
        for arc in outline.get("arcs", []):
            if arc["start_chapter"] <= chapter_number <= arc["end_chapter"]:
                return arc
    except Exception as e:
        print(f"[ERROR] Failed to load outline JSON: {e}")
        
    # Default fallback arc definition
    return {
        "arc_number": 1,
        "title": "Default Arc",
        "start_chapter": 1,
        "end_chapter": 25
    }

def write_next_chapter(novel_id: str) -> dict:
    """Orchestrate the generation and database sync of the next chapter."""
    # 1. Determine next chapter number by finding the first blueprint placeholder
    all_chapters = database.get_all_chapters(novel_id)
    next_ch_record = next((c for c in all_chapters if c["content"].startswith("BLUEPRINT:")), None)
    
    if next_ch_record:
        next_ch_number = next_ch_record["chapter_number"]
    else:
        if all_chapters:
            next_ch_number = all_chapters[-1]["chapter_number"] + 1
        else:
            next_ch_number = 1
        
    print(f"[INFO] Initiating writing process for Chapter {next_ch_number}...")
    
    # 2. Get current arc and verify if chapter blueprints need to be generated
    current_arc = get_current_arc(novel_id, next_ch_number)
    
    # Fetch the chapter record for next_ch_number
    chapter_record = next((c for c in all_chapters if c["chapter_number"] == next_ch_number), None)
    
    # If chapter record doesn't exist, we might have crossed into a new Arc
    if not chapter_record:
        # Generate blueprints for the new arc
        generate_arc_blueprints(novel_id, current_arc)
        all_chapters = database.get_all_chapters(novel_id)
        chapter_record = next((c for c in all_chapters if c["chapter_number"] == next_ch_number), None)
        
    if not chapter_record:
        raise ValueError(f"Could not initialize blueprint for chapter {next_ch_number}")
        
    blueprint_text = chapter_record["content"]
    
    # 3. Retrieve database entities for Context Injection
    # A. Characters
    chars = database.get_characters(novel_id)
    # Filter protagonist (assume first character is protagonist or name contains 'Jack'/'Protagonist')
    protagonist = next((c for c in chars if c.get("failure_flag") is not None), None)
    if not protagonist and chars:
        protagonist = chars[0]
        
    protagonist_name = protagonist["name"] if protagonist else "Jack"
    protagonist_power = protagonist["power_tier"] if protagonist else "Ordinary"
    protagonist_stats = json.dumps(protagonist["combat_stats"]) if protagonist else "{}"
    failure_flag = protagonist["failure_flag"] if protagonist else False
    last_breakthrough_ch = protagonist["last_breakthrough_chapter"] if protagonist else 0
    
    # B. World Lore
    lores = database.get_world_lore(novel_id)
    world_lore_text = "\n".join([f"- {lore['keyword']}: {lore['description']}" for lore in lores])
    
    # C. History Vector Search (Semantic RAG)
    query_embed = get_embedding(blueprint_text)
    semantic_history = database.search_episodes(novel_id, query_embed, limit=3)
    history_text = "\n".join([f"- Chapter {h['chapter_id']}: {h['event_summary']}" for h in semantic_history])
    
    # D. Working Memory (Last 2 written chapters content)
    previous_chapters = [c for c in all_chapters if c["chapter_number"] < next_ch_number and not c["content"].startswith("BLUEPRINT:")]
    working_memory_text = ""
    for ch in previous_chapters[-2:]:
        working_memory_text += f"\n--- Chapter {ch['chapter_number']}: {ch['title']} ---\n{ch['content'][:800]}...\n"
        
    # 4. Generate Chapter Content with Editor Review loop
    attempt = 0
    max_attempts = 3
    final_content = ""
    
    prompt = prompts.WRITING_PROMPT.format(
        chapter_number=next_ch_number,
        chapter_title=chapter_record["title"],
        title="Truyện 24h Audio",
        blueprint=blueprint_text,
        world_lore=world_lore_text,
        characters=json.dumps(chars, ensure_ascii=False, indent=2),
        history=history_text,
        previous_content=working_memory_text,
        protagonist_name=protagonist_name,
        protagonist_power=protagonist_power,
        protagonist_stats=protagonist_stats,
        failure_flag=str(failure_flag)
    )
    
    if next_ch_number == 1:
        prologue_instruction = (
            "- Phần dẫn lược (Prologue): BẮT BUỘC phải mở đầu chương bằng một phần Dẫn lược cực kỳ chi tiết, dài và sống động (khoảng 300 - 500 từ). "
            "Phần này phải giới thiệu sâu sắc và hấp dẫn về bối cảnh thế giới linh hồn, hệ thống Tinh Thần Ấn, lịch sử cấm kỵ của chiếc hộp đồng Đông Sơn, "
            "các nhân vật chính (Trần Lam, Linh Vy, Minh Đức, Thùy Linh, Cao Bá) và mốc thời gian hiện tại trước thềm Giờ Khai Mạc. "
            "**QUAN TRỌNG**: KHÔNG viết các tiêu đề như 'Dẫn lược:', 'Giới thiệu:', 'Prologue:', hay các ký hiệu markdown, "
            "mà hãy viết thẳng vào nội dung truyện một cách tự nhiên như các đoạn văn mở đầu câu chuyện."
        )
        prompt = prompt.replace("Constraints:", f"Constraints:\n{prologue_instruction}")
    
    while attempt < max_attempts:
        attempt += 1
        print(f"[INFO] Writing chapter draft (Attempt {attempt}/{max_attempts})...")
        
        # Enforce length restriction at drafting phase
        draft_attempt = 0
        current_prompt = prompt
        final_content = ""
        while draft_attempt < 3:
            draft_attempt += 1
            final_content = call_gemini(current_prompt)
            word_count = len(final_content.split())
            print(f"[INFO] Generated draft length: {word_count} words.")
            ends_abruptly = not final_content.strip().endswith((".", "?", "!", '"', "”", "»", "*"))
            
            if word_count >= 1800 and not ends_abruptly:
                break
                
            if ends_abruptly:
                print(f"[WARNING] Draft ends abruptly (no punctuation at the end). Requesting completion (Attempt {draft_attempt}/3)...")
                current_prompt = prompt + (
                    f"\n\n**CẢNH BÁO CỰC KỲ QUAN TRỌNG**: Bản thảo trước của bạn bị cắt cụt đột ngột ở cuối (chưa hết câu, chưa có dấu chấm câu kết thúc). "
                    f"Bạn BẮT BUỘC phải viết trọn vẹn câu chuyện, mở rộng chi tiết các phân cảnh, hội thoại và kết thúc chương một cách trọn vẹn bằng dấu chấm câu."
                )
            else:
                print(f"[WARNING] Draft too short ({word_count} words). Requesting longer expansion (Attempt {draft_attempt}/3)...")
                current_prompt = prompt + (
                    f"\n\n**CẢNH BÁO CỰC KỲ QUAN TRỌNG VỀ ĐỘ DÀI (BẮT BUỘC)**:\n"
                    f"Bản thảo bạn vừa viết quá ngắn (chỉ có {word_count} từ), trong khi yêu cầu tối thiểu là 2200 từ để đạt 10 phút nói.\n"
                    f"Để sửa lỗi này, bạn phải viết cực kỳ chi tiết theo hướng dẫn sau:\n"
                    f"1. Chia chương truyện thành ít nhất 5 phân cảnh lớn riêng biệt (Mỗi phân cảnh viết tối thiểu 5-6 đoạn văn dài).\n"
                    f"2. Đi sâu miêu tả cực kỳ tỉ mỉ: cảnh sắc không gian học viện, thời tiết, âm thanh gió thổi, biểu cảm nét mặt từng nhân vật, cử chỉ tay chân, và dòng suy nghĩ nội tâm kéo dài.\n"
                    f"3. Viết các đoạn đối thoại dài, thực tế và sâu sắc giữa các nhân vật (Trần Lam, Linh Vy, Minh Đức, v.v.). Không được viết lướt qua.\n"
                    f"4. TUYỆT ĐỐI không tóm tắt hay kết thúc chương truyện sớm khi chưa đủ độ dài yêu cầu."
                )
            
        # Editor Review
        review_prompt = prompts.REVIEW_PROMPT.format(
            chapter_number=next_ch_number,
            chapter_title=chapter_record["title"],
            chapter_content=final_content,
            world_lore=world_lore_text,
            characters=json.dumps(chars, ensure_ascii=False, indent=2),
            failure_flag=str(failure_flag),
            last_breakthrough_chapter=last_breakthrough_ch
        )
        
        review_json = call_gemini(review_prompt, json_mode=True)
        try:
            review = safe_loads(review_json)
            if review.get("pass_review") or attempt == max_attempts:
                print(f"[INFO] Chapter passed review with score {review.get('score', 8)}/10.")
                break
            else:
                print(f"[WARNING] Review failed: {review.get('feedback')}. Re-writing...")
                # Inject feedback into prompt for next try
                prompt = prompt + f"\n\nPrevious Editor Feedback (MUST address this in rewrite): {review.get('feedback')}"
        except Exception as e:
            print(f"[WARNING] Failed to parse editor review: {e}. Skipping review loop.")
            break
            
    # 5. Save written chapter to Supabase
    # Update content of chapter_record (cleaning consecutive repetitions and header labels first)
    cleaned_content = clean_chapter_content(final_content)
    client = database.get_client()
    response = client.table("chapters")\
        .update({"content": cleaned_content})\
        .eq("id", chapter_record["id"])\
        .execute()
    updated_chapter = response.data[0] if response.data else {}
    
    # 6. Post-writing Database Sync (Extract Entities & Update Story Bible)
    sync_story_bible(novel_id, updated_chapter, chars)
    
    return updated_chapter

def sync_story_bible(novel_id: str, chapter: dict, current_chars: list):
    """Parse the written chapter to extract status updates and write them to Supabase."""
    print("[INFO] Syncing Story Bible and updating character stats...")
    
    prompt = prompts.EXTRACT_ENTITIES_PROMPT.format(
        chapter_content=chapter["content"],
        current_characters=json.dumps(current_chars, ensure_ascii=False)
    )
    
    extract_json = call_gemini(prompt, json_mode=True)
    try:
        data = safe_loads(extract_json)
        
        # 1. Update Character states (stats, failure flag, breakthrough)
        for char_up in data.get("character_updates", []):
            name = char_up["name"]
            # Fetch existing to avoid wiping missing fields
            exist = database.get_character_by_name(novel_id, name)
            
            # Decide if breakthrough resetting the failure_flag is needed
            new_failure_flag = char_up.get("failure_flag")
            if new_failure_flag is None:
                new_failure_flag = exist.get("failure_flag", False) if exist else False
                
            last_bt = exist.get("last_breakthrough_chapter", 0) if exist else 0
            
            # If protagonist had a breakthrough, reset failure_flag and record chapter number
            if char_up.get("breakthrough_written"):
                new_failure_flag = False
                last_bt = chapter["chapter_number"]
                print(f"[INFO] Protagonist breakthrough recorded in Chapter {last_bt}! Resetting failure_flag.")
                
            # Safely resolve schema fields to prevent null violations
            description = char_up.get("description") or (exist.get("description", "") if exist else "")
            power_tier = char_up.get("power_tier") or (exist.get("power_tier", "Ordinary") if exist else "Ordinary")
            combat_stats = char_up.get("combat_stats") or (exist.get("combat_stats", {}) if exist else {})
            relationships = char_up.get("relationships") or (exist.get("relationships", {}) if exist else {})
            
            database.upsert_character(
                novel_id=novel_id,
                name=name,
                description=description,
                power_tier=power_tier,
                combat_stats=combat_stats,
                relationships=relationships,
                failure_flag=new_failure_flag,
                last_breakthrough_chapter=last_bt
            )
            
        # 2. Insert new world lores
        for lore in data.get("new_lore", []):
            database.upsert_world_lore(
                novel_id=novel_id,
                keyword=lore["keyword"],
                description=lore["description"]
            )
            print(f"[INFO] New lore added: {lore['keyword']}")
            
        # 3. Insert new narrative threads
        for thread in data.get("new_threads", []):
            database.upsert_narrative_thread(
                novel_id=novel_id,
                thread_name=thread["thread_name"],
                description=thread["description"],
                status="open"
            )
            print(f"[INFO] New narrative thread added: {thread['thread_name']}")
            
        # 4. Generate Episodic Summary and Embedding
        # Create event list
        events_list = [c.get("event_summary", "") for c in data.get("character_updates", []) if c.get("event_summary")]
        chapter_events = " ".join(events_list) if events_list else f"Chapter {chapter['chapter_number']}: {chapter['title']}"
        
        embed_vector = get_embedding(chapter["content"])
        database.create_episode_summary(
            chapter_id=chapter["id"],
            event_summary=chapter_events,
            embedding=embed_vector
        )
        print("[INFO] Episodic summary and Vector embedding saved.")
        
    except Exception as e:
        print(f"[ERROR] Story bible sync failed: {e}. Raw JSON: {extract_json}")

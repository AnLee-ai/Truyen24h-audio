# Templates for AI Novel Writing Engine

OUTLINE_PROMPT = """
You are an expert story planner. Design a global outline for a web novel of at least 150 chapters.
The novel is targeted at teenagers (13-19 years old).
Title: {title}
Description: {description}

Requirements:
1. Divide the story into 6-8 major Story Arcs, totaling 150+ chapters.
2. Ensure slow-burn pacing, deep world-building, and character growth.
3. Avoid English names and English proper nouns. Use Vietnamese names (e.g., Phong, Nam, Vy, Linh) and Vietnamese-style proper nouns. Keep all names natural to Vietnamese readers.
4. Output the outline as a structured JSON object with the following schema:
{{
  "title": "Novel Title",
  "arcs": [
    {{
      "arc_number": 1,
      "title": "Arc Title",
      "summary": "Detailed summary of what happens in this arc",
      "start_chapter": 1,
      "end_chapter": 25,
      "key_milestones": ["Milestone 1", "Milestone 2"]
    }}
  ]
}}
Ensure the JSON is strictly formatted and valid. Do not wrap in markdown quotes.
"""

ARC_PROMPT = """
You are a detailed storyteller. Develop a chapter-by-chapter blueprint outline for Arc {arc_number}: {arc_title} of the novel "{novel_title}".
Novel Description: {novel_description}
Arc Summary: {arc_summary}
This arc spans chapters {start_chapter} to {end_chapter}.
Global story status: {global_status}

Requirements:
1. Break down the arc into individual chapters. For each chapter, outline the main event, key characters present, and narrative goals.
2. Maintain slow-burn, detailed pacing.
3. Avoid English names. Use Vietnamese names for all characters, places, and organizations.
4. Output as a JSON array of chapters:
[
  {{
    "chapter_number": 1,
    "chapter_title": "Chapter Title",
    "blueprint": "Detailed description of what needs to happen in this chapter",
    "characters_present": ["Jack", "Alex"],
    "narrative_goal": "Goal of this chapter"
  }}
]
Ensure the JSON is valid.
"""

WRITING_PROMPT = """
You are an elite novelist. Write Chapter {chapter_number}: {chapter_title} of the novel {title}.
The target audience is teenagers. The pacing must be detailed, slow-burn, focusing on deep scene descriptions, atmospheric building, and detailed dialogues. Do not rush the plot.

Context and Resources:
- Chapter Blueprint: {blueprint}
- World Rules & Lore: {world_lore}
- Character Bible: {characters}
- Episodic History (Previous Arcs): {history}
- Previous Chapters Context: {previous_content}

Constraints:
1. Word count: Write a massive chapter of at least 2500 to 3500 words (MUST exceed 2200 words at all costs to ensure a full 10+ minutes speaking time). Describe environments, character body language, internal thoughts, and detailed conversations in great depth. Avoid summarizing any action or event. Write out every single interaction in detailed, paragraph-by-paragraph scenes.
2. Tone & Vocabulary: Avoid English proper nouns and English names. Use Vietnamese names and natural Vietnamese terminology.
3. Protagonist Progression: The protagonist ({protagonist_name}) currently has power level: {protagonist_power} and stats: {protagonist_stats}.
   - **CRITICAL**: The protagonist CANNOT level up or obtain new powers in this chapter unless the failure flag is TRUE (failure_flag = {failure_flag}).
   - If failure_flag is False, the protagonist must face challenging obstacles, struggle, or experience setbacks without a breakthrough. Keep their powers exactly as is.
4. Dialogue: Make the conversation between characters dynamic and teenager-friendly (50% dialogue/action, 50% description).

Write the chapter in Vietnamese. Keep the output as the raw novel content only (do not include conversational chat filler or introduction like "Here is the chapter...", but DO write the prologue/story introduction if it is part of the chapter content).
"""

EXTRACT_ENTITIES_PROMPT = """
Read the following chapter and extract any updates to the character status, relationships, world lore, or new narrative threads.

Chapter Content:
{chapter_content}

Current Character States:
{current_characters}

Analyze the chapter and output a JSON object indicating:
1. Whether any character's power level, combat stats, or relationships updated.
2. Whether the protagonist experienced a major defeat, setback, or failure (set failure_flag to true if they failed/lost/struggled heavily, or keep false).
3. If the protagonist had a breakthrough (breakthrough = true if they leveled up or unlocked new powers, otherwise false).
4. Any new lore keywords introduced.
5. Any new active narrative threads.

Output format (strict JSON, do not wrap in markdown):
{{
  "character_updates": [
    {{
      "name": "Jack",
      "power_tier": "Novice",
      "combat_stats": {{ "attack": 15, "defense": 10 }},
      "relationships": {{ "Alex": "ally" }},
      "failure_flag": true,
      "breakthrough_written": false,
      "event_summary": "Short summary of what happened to this character in the chapter"
    }}
  ],
  "new_lore": [
    {{
      "keyword": "Ancient Ruin",
      "description": "Description of the new lore keyword discovered"
    }}
  ],
  "new_threads": [
    {{
      "thread_name": "The Missing Key",
      "description": "Description of the new active narrative thread introduced"
    }}
  ]
}}
Ensure the JSON is strictly formatted and valid.
"""

REVIEW_PROMPT = """
You are an expert editor. Review the draft of Chapter {chapter_number}: {chapter_title} for consistency, prose quality, and logical coherence.

Review Context:
- Chapter Content: {chapter_content}
- World Lore: {world_lore}
- Character Status: {characters}
- Protagonist Failure Flag (Active?): {failure_flag}
- Protagonist Last Breakthrough Chapter: {last_breakthrough_chapter}

Requirements:
1. Ensure the pacing is appropriate (detailed, slow-burn) and the writing quality is high.
2. Check for logical contradictions or errors.
3. Verify character power progression:
   - If failure_flag is False, make sure the protagonist does NOT show sudden power breakthrough or defeat high-tier foes easily.
   - If a breakthrough chapter is active or recent, check that it makes logical sense.
4. Output your review as a JSON object with:
{{
  "score": 8, // 1 to 10 scale
  "pass_review": true, // set to false if major logical/pacing errors exist and chapter needs rewrite
  "feedback": "Detailed feedback detailing what to improve if pass_review is false"
}}
Ensure the JSON is strictly formatted and valid.
"""

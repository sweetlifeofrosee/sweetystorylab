# ============================================================
# post.py — SweetyStoryLab Horror Reels Bot
# ============================================================
# 3-scene cinematic slideshow Reel with synced subtitles
# Pipeline:
#   1. Groq → horror story split into 3 scenes + 3 image prompts
#   2. Pollinations → 3 horror images (one per scene)
#   3. Edge TTS → voice narration + .vtt subtitle file
#   4. FFmpeg → 3-image slideshow + voice + burned subtitles
#   5. Facebook Graph API → upload as Reel
#   6. SQLite → log result

import os, random, requests, time, json, sqlite3, subprocess, re, textwrap
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io

# ============================================================
# SECRETS
# ============================================================
FB_ACCESS_TOKEN    = os.environ["FB_PAGE_ACCESS_TOKEN"]
FB_PAGE_ID         = os.environ["FB_PAGE_ID"]
GROQ_API_KEY       = os.environ["GROQ_API_KEY"]
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")

# ============================================================
# PATHS
# ============================================================
WORK_DIR    = "/tmp/horrorbot"
VOICE_FILE  = f"{WORK_DIR}/voice.mp3"
VTT_FILE    = f"{WORK_DIR}/voice.vtt"
SRT_FILE    = f"{WORK_DIR}/voice.srt"
VIDEO_FILE  = f"{WORK_DIR}/reel.mp4"
MUSIC_MP3   = f"{WORK_DIR}/music.mp3"
DB_FILE     = "horror_log.db"
os.makedirs(WORK_DIR, exist_ok=True)

# ============================================================
# EDGE TTS VOICE MAP
# Male and female horror-appropriate voices
# ============================================================
EDGE_TTS_VOICES = {
    "male":   "en-US-GuyNeural",
    "female": "en-US-AriaNeural"
}

# ============================================================
# FALLBACK
# ============================================================
FALLBACK = {
    "title": "The Third Floor",
    "caption": "He went up for ten minutes. He never came back the same. 👻",
    "hashtags": "#Horror #ScaryStories #GhostStories #Paranormal #Supernatural #HauntedPlace #TrueHorror #NightmareFuel #Creepy #Unexplained #DarkStories #HorrorShorts #StoryTime #Eerie #Thriller #SweetyStoryLab",
    "question": "Have you ever heard footsteps when nobody was there?",
    "narrator_gender": "male",
    "scenes": [
        {
            "narration": "We moved into a new apartment last June. The neighbor warned us the moment we arrived. Nobody had lived on the third floor for years, she said, and nobody lasted more than a week when they tried. We laughed it off. The first week was quiet.",
            "image_prompt": "dark apartment building hallway at night, flickering light, eerie fog, no people, cinematic horror"
        },
        {
            "narration": "The second week, we heard footsteps every midnight. Slow, deliberate steps above us, though the floor was supposed to be empty. My husband Mark decided to go up and check. Ten minutes, he promised. He took his phone and the flashlight and headed up the stairwell alone.",
            "image_prompt": "dark staircase leading up into darkness, single light at top, abandoned building, horror atmosphere"
        },
        {
            "narration": "We found him two hours later, sitting in the corner of an empty room on the third floor. He was staring at the wall, completely still, not answering when we called his name. He came home with us without a word. To this day, he will not tell us what he saw up there.",
            "image_prompt": "dark empty room corner with single dim light, eerie shadow on wall, abandoned, psychological horror"
        }
    ]
}

# ============================================================
# STEP 1: GENERATE STORY WITH GROQ
# ============================================================
def generate_story():
    print("Generating fresh horror theme and story with Groq...")

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a world-class horror story writer for Facebook and TikTok Reels. "
                    "You write immersive, narrative-driven horror stories set anywhere in the world — "
                    "Japan, USA, Philippines, UK, Mexico, Indonesia, Korea, Brazil, India, Europe, Africa, Middle East, and beyond. "
                    "You draw from horror traditions worldwide: "
                    "Japanese urban legends (kuchisake-onna, teke-teke), American ghost stories, Filipino folklore (aswang, white lady), "
                    "Korean horror, Latin American mythology (la llorona, el silbon), European dark fairy tales, "
                    "African supernatural stories, haunted hotels, abandoned hospitals, cursed highways, and unexplained phenomena. "
                    "IMPORTANT: Vary the setting every single time — do NOT repeat the same country or location type. "
                    "Always write in ENGLISH ONLY. "
                    "Write in first-person, true story style. Use complete sentences with proper narrative flow. "
                    "Build atmosphere slowly. Include character names, specific locations, and real emotions. "
                    "No gore. Psychological fear only. Always end with an unanswered mystery or chilling twist."
                )
            },
            {
                "role": "user",
                "content": """First, pick a country or culture from anywhere in the world (Japan, Korea, USA, Mexico, UK, Brazil, Indonesia, India, Philippines, Thailand, Russia, Nigeria, etc.) and invent a unique horror theme inspired by that culture.
Avoid repeating the same country. Each story should feel like it comes from a different part of the world.
Be creative — mix creatures, settings, and situations in unexpected ways.
Avoid repeating common themes. Think of something fresh and specific.

Then write a complete 3-scene horror story based on your invented theme.
Write in first-person ("I", "we"). Use character names. Include specific details.
Each scene should be 60-80 words — enough to tell a real story, not just fragments.
Use complete sentences with natural flow. Build dread slowly across all 3 scenes.

Scene 1 = introduce the character, setting, and first sign something is wrong
Scene 2 = tension builds, the character investigates or something disturbing is discovered
Scene 3 = terrifying climax or chilling twist — leave an unanswered mystery

CRITICAL RULES:
- Everything in ENGLISH ONLY. No Tagalog. No Filipino words ever.
- Write like a real person sharing a true experience — immersive and believable
- NO fragmented sentences like "broken lights. shattered dreams." — write full narratives
- Use a DIFFERENT character name every single story — never reuse names like Maria, John, etc.
- Character names should match the country/culture of the story (Japanese story = Japanese name, etc.)
- Hashtags must be relevant to THIS specific story

Output ONLY this exact format, nothing else:
Theme: (your invented horror theme, 1 line, English only)
Title: (max 5 words, mysterious, English only)
Caption: (1 punchy hook line, max 15 words, add 👻, English only)
Hashtags: (15-20 hashtags relevant to THIS story. Mix broad and niche.
  Always include: #Horror #SweetyStoryLab
  Pick relevant ones from these categories based on story content:
  - Broad: #ScaryStories #CreepyStories #GhostStories #Paranormal #Supernatural #Thriller #Mystery
  - Setting: #HauntedHouse #AbandonedPlace #DarkForest #Hospital #Highway #Hotel
  - Creature: #Ghost #Demon #Aswang #WhiteLady #UrbanLegend #FolklorHorror
  - Style: #TrueHorror #TrueStory #NightmareFuel #Creepy #Eerie #Unexplained #DarkStories
  - Platform: #HorrorTok #HorrorShorts #ScaryTok #StoryTime #HorrorReels
  - Filipino: #HorrorPH #PinoyHorror #FilipinoPH (only if story has Filipino elements)
  Return as one line of hashtags, no explanations)
NarratorGender: (male or female — based on the first-person narrator's gender in the story)
Scene1Narration: (60-80 words, first person, full sentences, ENGLISH ONLY)
Scene1Image: (cinematic dark horror scene, no people, no text, eerie atmosphere)
Scene2Narration: (60-80 words, first person, full sentences, ENGLISH ONLY)
Scene2Image: (cinematic dark horror scene, no people, no text)
Scene3Narration: (60-80 words, first person, full sentences, ENGLISH ONLY)
Scene3Image: (cinematic dark horror scene, no people, no text, dramatic)
Question: (1 engaging question for viewers, max 12 words, makes them comment. Examples: "Have you ever experienced something you cannot explain?" "What would you have done in this situation?" "Do you believe this really happened?")"""
            }
        ],
        "temperature": 0.95,
        "max_tokens": 1200
    }

    res = requests.post("https://api.groq.com/openai/v1/chat/completions",
                        headers=headers, json=payload, timeout=30)
    res.raise_for_status()
    text = res.json()["choices"][0]["message"]["content"].strip()
    print("Groq response received")
    return parse_story(text)

def parse_story(text):
    result = {
        "title": "Night Terror",
        "caption": "Some things are better left unseen. 👻",
        "hashtags": "#Horror #ScaryStories #GhostStories #Paranormal #SweetyStoryLab",
        "narrator_gender": "male",
        "scenes": [{"narration": "", "image_prompt": ""} for _ in range(3)],
        "question": "Have you ever experienced something you cannot explain?"
    }
    text = text.replace("**", "").replace("*", "")
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        if line.startswith("Theme:"):
            print(f"AI invented theme: {line.replace('Theme:', '').strip()}")
        elif line.startswith("Title:"):
            result["title"] = line.replace("Title:", "").strip().strip('"')
        elif line.startswith("Caption:"):
            result["caption"] = line.replace("Caption:", "").strip().strip('"')
        elif line.startswith("Hashtags:"):
            result["hashtags"] = line.replace("Hashtags:", "").strip()
        elif line.startswith("NarratorGender:"):
            gender = line.replace("NarratorGender:", "").strip().lower()
            result["narrator_gender"] = "female" if "female" in gender else "male"
        elif line.startswith("Scene1Narration:"):
            result["scenes"][0]["narration"] = line.replace("Scene1Narration:", "").strip()
        elif line.startswith("Scene1Image:"):
            result["scenes"][0]["image_prompt"] = line.replace("Scene1Image:", "").strip()
        elif line.startswith("Scene2Narration:"):
            result["scenes"][1]["narration"] = line.replace("Scene2Narration:", "").strip()
        elif line.startswith("Scene2Image:"):
            result["scenes"][1]["image_prompt"] = line.replace("Scene2Image:", "").strip()
        elif line.startswith("Scene3Narration:"):
            result["scenes"][2]["narration"] = line.replace("Scene3Narration:", "").strip()
        elif line.startswith("Scene3Image:"):
            result["scenes"][2]["image_prompt"] = line.replace("Scene3Image:", "").strip()
        elif line.startswith("Question:"):
            result["question"] = line.replace("Question:", "").strip().strip('"')
    return result

def get_content():
    try:
        content = generate_story()
        if all(s["narration"] for s in content["scenes"]):
            print(f"Story: {content['title']} (narrator: {content['narrator_gender']})")
            return content
    except Exception as e:
        print(f"Groq failed: {e}")
    print("Using fallback...")
    return FALLBACK

# ============================================================
# STEP 2: GENERATE 3 HORROR IMAGES WITH POLLINATIONS.AI
# ============================================================
def generate_image(prompt, index):
    print(f"Generating image {index+1}/3...")
    full_prompt = (
        f"{prompt}, dark cinematic horror, eerie atmosphere, "
        "dramatic lighting, photorealistic, high quality, "
        "no text, no watermark, no faces"
    )
    encoded = requests.utils.quote(full_prompt)
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true&seed={seed}"

    for attempt in range(3):
        try:
            res = requests.get(url, timeout=90)
            res.raise_for_status()
            path = f"{WORK_DIR}/image_{index}.jpg"
            with open(path, "wb") as f:
                f.write(res.content)
            print(f"Image {index+1} saved!")
            return path
        except Exception as e:
            print(f"Image {index+1} attempt {attempt+1} failed: {e}")
            if attempt < 2:
                print(f"Retrying in 10s...")
                time.sleep(10)
                seed = random.randint(1, 99999)
                url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true&seed={seed}"

    # All retries failed — use pre-made fallback image
    fallback_path = f"images/fallback_{index}.jpg"
    if os.path.exists(fallback_path):
        print(f"Using fallback image: {fallback_path}")
        path = f"{WORK_DIR}/image_{index}.jpg"
        import shutil
        shutil.copy(fallback_path, path)
        return path

    raise Exception(f"Image {index+1} failed after 3 attempts and no fallback found")

# ============================================================
# STEP 3: GENERATE VOICE + SUBTITLES
# ============================================================
# Auto-detects narrator gender from story and picks
# matching Edge TTS voice:
#   Female narrator → en-US-AriaNeural
#   Male narrator   → en-US-GuyNeural
# ============================================================

def generate_voice_elevenlabs(text, gender="male"):
    print("Trying ElevenLabs voice (emotional)...")
    try:
        voices_res = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=10
        )
        voices = voices_res.json().get("voices", [])
        # Pick voice based on gender
        if gender == "female":
            preferred = ["Rachel", "Domi", "Bella", "Elli", "Dorothy"]
        else:
            preferred = ["Daniel", "Adam", "Antoni", "Josh", "Arnold", "Thomas"]
        VOICE_ID = None
        for name in preferred:
            match = next((v for v in voices if v["name"] == name), None)
            if match:
                VOICE_ID = match["voice_id"]
                print(f"Using ElevenLabs voice: {name}")
                break
        if not VOICE_ID and voices:
            VOICE_ID = voices[0]["voice_id"]
            print(f"Using ElevenLabs voice: {voices[0]['name']}")
        if not VOICE_ID:
            print("No voices found on ElevenLabs account")
            return False
    except Exception as e:
        print(f"Could not fetch voices: {e}")
        return False

    try:
        res = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.4,
                    "similarity_boost": 0.8,
                    "style": 0.5,
                    "use_speaker_boost": True
                }
            },
            timeout=60
        )
        if res.status_code == 429:
            print("⚠️ ElevenLabs quota exceeded — falling back to Edge TTS")
            return False
        res.raise_for_status()
        with open(VOICE_FILE, "wb") as f:
            f.write(res.content)
        print("✅ ElevenLabs voice generated!")
        return True
    except Exception as e:
        print(f"⚠️ ElevenLabs failed: {e} — falling back to Edge TTS")
        return False

def generate_voice_edgetts(text, gender="male"):
    voice = EDGE_TTS_VOICES.get(gender, EDGE_TTS_VOICES["male"])
    print(f"Generating voice with Edge TTS ({voice})...")
    result = subprocess.run(
        ["edge-tts", "--voice", voice, "--rate=-10%",
         "--text", text, "--write-media", VOICE_FILE, "--write-subtitles", VTT_FILE],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise Exception(f"Edge TTS failed: {result.stderr}")
    print(f"✅ Edge TTS voice generated! (gender: {gender})")

def generate_srt_from_voice(text):
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", VOICE_FILE],
        capture_output=True, text=True
    )
    duration = float(json.loads(probe.stdout)["streams"][0]["duration"])
    words = text.split()
    total_words = len(words)
    time_per_word = duration / total_words if total_words > 0 else 0.4
    srt_blocks = []
    counter = 1
    chunk_size = 3

    for i in range(0, total_words, chunk_size):
        chunk = words[i:i + chunk_size]
        start_time = i * time_per_word
        end_time = min((i + chunk_size) * time_per_word, duration)

        def fmt(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        block = f"{counter}\n{fmt(start_time)} --> {fmt(end_time)}\n{' '.join(chunk)}"
        srt_blocks.append(block)
        counter += 1

    with open(SRT_FILE, "w", encoding="utf-8") as f:
        f.write("\n\n".join(srt_blocks))
    print(f"✅ SRT generated ({counter-1} blocks)")

def generate_voice(scenes, gender="male"):
    full_narration = " ".join(s["narration"] for s in scenes)
    clean = full_narration.replace("#", "").replace("👻", "").replace("...", ". ").strip()
    used_elevenlabs = False
    if ELEVENLABS_API_KEY:
        used_elevenlabs = generate_voice_elevenlabs(clean, gender)
    if used_elevenlabs:
        generate_srt_from_voice(clean)
    else:
        generate_voice_edgetts(clean, gender)
        vtt_to_srt(VTT_FILE, SRT_FILE)
    print(f"Voice ready! ({'ElevenLabs' if used_elevenlabs else 'Edge TTS'} — {gender})")
    return VOICE_FILE, SRT_FILE

def vtt_to_srt(vtt_path, srt_path):
    with open(vtt_path, "r", encoding="utf-8") as f:
        raw = f.read()
    raw = re.sub(r"WEBVTT\n", "", raw)
    raw = re.sub(r"NOTE[^\n]*\n[^\n]*\n", "", raw)
    blocks = raw.strip().split("\n\n")
    srt_out = []
    counter = 1
    for block in blocks:
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if not lines: continue
        timing_line = next((l for l in lines if "-->" in l), None)
        if not timing_line: continue
        timing = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", timing_line)
        timing = re.sub(r"\s+(align|position|line|size):\S+", "", timing).strip()
        text_lines = [l for l in lines if "-->" not in l]
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text).strip()
        text = re.sub(r"^\d+[\s\.]+", "", text).strip()
        if text:
            srt_out.append(f"{counter}\n{timing}\n{text}")
            counter += 1
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(srt_out))
    print(f"SRT created: {counter-1} subtitle blocks")

# ============================================================
# STEP 3.5: BACKGROUND MUSIC
# ============================================================
def generate_music(title, scenes):
    if os.path.exists("sounds/suspense.mp3"):
        print("Using suspense.mp3 for background music")
        return "sounds/suspense.mp3"
    print("No music found — posting without music")
    return None

# ============================================================
# STEP 4: BUILD VIDEO
# ============================================================
def build_video(image_paths, voice_path, srt_path, scenes, title, question, music_path=None):
    print("Building video with FFmpeg...")

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", voice_path],
        capture_output=True, text=True
    )
    total_duration = float(json.loads(probe.stdout)["streams"][0]["duration"])
    scene_duration = total_duration / 3
    print(f"Total: {total_duration:.1f}s — Each scene: {scene_duration:.1f}s")

    scene_frames = []
    for i, (img_path, scene) in enumerate(zip(image_paths, scenes)):
        frame_path = build_frame(img_path, title, i)
        scene_frames.append((frame_path, scene_duration))

    question_frame = build_question_frame(question, image_paths[-1])
    scene_frames.append((question_frame, 4.0))

    concat_file = f"{WORK_DIR}/concat.txt"
    with open(concat_file, "w") as f:
        for frame_path, duration in scene_frames:
            f.write(f"file '{frame_path}'\n")
            f.write(f"duration {duration:.3f}\n")
        f.write(f"file '{scene_frames[-1][0]}'\n")

    temp_video = f"{WORK_DIR}/temp_video.mp4"
    padded_voice = f"{WORK_DIR}/voice_padded.mp3"

    pad_result = subprocess.run([
        "ffmpeg", "-y", "-i", voice_path,
        "-af", "apad=pad_dur=4",
        "-codec:a", "libmp3lame", "-q:a", "2", padded_voice
    ], capture_output=True)
    if pad_result.returncode != 0:
        print("⚠️ Audio padding failed — using original voice")
        padded_voice = voice_path
    else:
        print("✅ Audio padded with 4s silence for question slide")

    num_frames = len(scene_frames)
    fade_duration = 0.8

    if num_frames == 1:
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", scene_frames[0][0],
            "-t", str(scene_frames[0][1]),
            "-vf", "scale=1080:1920,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", temp_video
        ], check=True, capture_output=True)
    else:
        inputs = []
        for frame_path, duration in scene_frames:
            inputs += ["-loop", "1", "-t", str(duration + fade_duration), "-i", frame_path]

        filter_parts = []
        cumulative = 0.0
        prev_label = "[0:v]"

        for i in range(1, num_frames):
            cumulative += scene_frames[i-1][1]
            offset = max(0.1, cumulative - fade_duration)
            out_label = f"[fade{i}]" if i < num_frames - 1 else ""
            filter_parts.append(
                f"{prev_label}[{i}:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}{out_label}"
            )
            prev_label = f"[fade{i}]"

        filter_complex = ",".join(filter_parts) if len(filter_parts) == 1 else ";".join(filter_parts)
        filter_complex += ",scale=1080:1920,fps=30"

        result = subprocess.run([
            "ffmpeg", "-y",
        ] + inputs + [
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", "30", temp_video
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"⚠️ Crossfade failed — falling back to hard cuts")
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                "-vf", "scale=1080:1920,fps=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", temp_video
            ], check=True, capture_output=True)
        else:
            print("✅ Slideshow with crossfade transitions built!")

    subtitle_style = (
        "FontName=Arial,FontSize=9,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BackColour=&H80000000,"
        "Bold=1,Outline=3,Shadow=2,Alignment=2,MarginV=80"
    )

    has_music = music_path is not None and os.path.exists(music_path)

    if has_music:
        print(f"Mixing in background music at 15% volume...")
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", padded_voice,
            "-stream_loop", "-1", "-i", music_path,
            "-c:v", "libx264",
            "-vf", f"subtitles={srt_path}:force_style='{subtitle_style}'",
            "-filter_complex", "[1:a][2:a]amix=inputs=2:weights=1 0.15:duration=first:normalize=0[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-shortest", "-movflags", "+faststart",
            VIDEO_FILE
        ], capture_output=True, text=True, timeout=180)
    else:
        print("No music — posting voice only...")
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", padded_voice,
            "-c:v", "libx264",
            "-vf", f"subtitles={srt_path}:force_style='{subtitle_style}'",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-shortest", "-movflags", "+faststart",
            VIDEO_FILE
        ], capture_output=True, text=True, timeout=180)

    if result.returncode != 0:
        raise Exception(f"FFmpeg final failed: {result.stderr[-500:]}")

    size_mb = os.path.getsize(VIDEO_FILE) / 1024 / 1024
    print(f"Video built! ({size_mb:.1f}MB)")
    return VIDEO_FILE

def build_frame(img_path, title, scene_index):
    img = Image.open(img_path).convert("RGB")
    bg = img.resize((1080, 1920), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=25))
    darkener = Image.new("RGB", (1080, 1920), (0, 0, 0))
    bg = Image.blend(bg, darkener, 0.6)
    img_main = img.resize((1080, 1080), Image.LANCZOS)
    grad = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(grad)
    for i in range(500):
        alpha = int((i / 500) * 220)
        grad_draw.rectangle([0, 580 + i, 1080, 581 + i], fill=(0, 0, 0, alpha))
    img_rgba = img_main.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, grad)
    img_main = img_rgba.convert("RGB")
    canvas = bg.copy()
    canvas.paste(img_main, (0, 420))
    canvas_rgba = canvas.convert("RGBA")
    top_bar = Image.new("RGBA", (1080, 380), (0, 0, 0, 200))
    canvas_rgba.paste(top_bar, (0, 0), top_bar)
    canvas = canvas_rgba.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    try:
        font_title = ImageFont.truetype("/tmp/Lora-Italic.ttf", 48)
        font_brand = ImageFont.truetype("/tmp/Lora-Italic.ttf", 26)
        font_scene = ImageFont.truetype("/tmp/Lora-Italic.ttf", 22)
    except:
        font_title = font_brand = font_scene = ImageFont.load_default()
    display_title = title if len(title) <= 28 else title[:25] + "..."
    draw.text((542, 152), display_title, font=font_title, fill=(0,0,0,200), anchor="mm")
    draw.text((540, 150), display_title, font=font_title, fill=(255,255,255,255), anchor="mm")
    draw.rectangle([300, 200, 780, 203], fill=(255,255,255,140))
    dots = "● " * (scene_index + 1) + "○ " * (2 - scene_index)
    draw.text((540, 230), dots.strip(), font=font_scene, fill=(255,255,255,180), anchor="mm")
    draw.text((542, 1882), "SweetyStoryLab", font=font_brand, fill=(0,0,0,180), anchor="mm")
    draw.text((540, 1880), "SweetyStoryLab", font=font_brand, fill=(255,255,255,160), anchor="mm")
    frame_path = f"{WORK_DIR}/frame_{scene_index}.jpg"
    canvas.save(frame_path, "JPEG", quality=95)
    return frame_path

def build_question_frame(question, last_image_path):
    try:
        img = Image.open(last_image_path).convert("RGB")
        bg = img.resize((1080, 1920), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
        darkener = Image.new("RGB", (1080, 1920), (0, 0, 0))
        canvas = Image.blend(bg, darkener, 0.80)
    except:
        canvas = Image.new("RGB", (1080, 1920), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font_question = ImageFont.truetype("/tmp/Lora-Italic.ttf", 52)
        font_brand = ImageFont.truetype("/tmp/Lora-Italic.ttf", 26)
    except:
        font_question = font_brand = ImageFont.load_default()
    wrapped = textwrap.wrap(question, width=22)
    line_height = 72
    total_height = len(wrapped) * line_height
    start_y = 960 - total_height // 2
    for i, line in enumerate(wrapped):
        y = start_y + (i * line_height)
        for offset in [(3, 3), (2, 2), (1, 1)]:
            draw.text((540 + offset[0], y + offset[1]), line, font=font_question,
                      fill=(0, 0, 0, 180), anchor="mm")
        draw.text((540, y), line, font=font_question, fill=(255, 255, 255, 255), anchor="mm")
    draw.text((542, 1882), "SweetyStoryLab", font=font_brand, fill=(150,150,150,180), anchor="mm")
    draw.text((540, 1880), "SweetyStoryLab", font=font_brand, fill=(255,255,255,160), anchor="mm")
    frame_path = f"{WORK_DIR}/frame_question.jpg"
    canvas.save(frame_path, "JPEG", quality=95)
    print("✅ Question slide built!")
    return frame_path

# ============================================================
# STEP 5: UPLOAD TO FACEBOOK AS REEL
# ============================================================
def upload_reel(video_path, caption):
    print("Uploading Reel...")
    file_size = os.path.getsize(video_path)

    init = requests.post(
        f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/video_reels",
        data={"upload_phase": "start", "access_token": FB_ACCESS_TOKEN}
    )
    print(f"Init: {init.status_code} - {init.text}")
    init.raise_for_status()
    video_id = init.json()["video_id"]

    with open(video_path, "rb") as f:
        video_data = f.read()
    upload = requests.post(
        f"https://rupload.facebook.com/video-upload/v21.0/{video_id}",
        headers={
            "Authorization": f"OAuth {FB_ACCESS_TOKEN}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "video/mp4"
        },
        data=video_data, timeout=300
    )
    print(f"Upload: {upload.status_code} - {upload.text}")
    upload.raise_for_status()

    time.sleep(8)

    pub = requests.post(
        f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/video_reels",
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "title": "Horror Story",
            "description": caption,
            "video_state": "PUBLISHED",
            "access_token": FB_ACCESS_TOKEN
        }
    )
    print(f"Publish: {pub.status_code} - {pub.text}")
    pub.raise_for_status()
    print(f"Reel published! ID: {video_id}")
    return video_id

# ============================================================
# STEP 6: LOG TO SQLITE
# ============================================================
def log_result(title, video_id, status, error=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, title TEXT, video_id TEXT, status TEXT, error TEXT
    )""")
    c.execute("INSERT INTO posts (timestamp, title, video_id, status, error) VALUES (?,?,?,?,?)",
              (datetime.now().isoformat(), title, video_id or "", status, error or ""))
    conn.commit()
    conn.close()
    print(f"Logged: {status} — {title}")

# ============================================================
# MAIN
# ============================================================
def main():
    print(f"\nSweetyStoryLab Horror Bot — {datetime.now()}")
    video_id = None
    content = None

    try:
        content = get_content()
        title   = content["title"]
        scenes  = content["scenes"]
        gender  = content.get("narrator_gender", "male")
        caption = f"{content['caption']}\n\n{content['hashtags']}"

        print(f"Title: {title} | Narrator: {gender}")

        image_paths = []
        for i, scene in enumerate(scenes):
            try:
                path = generate_image(scene["image_prompt"], i)
            except Exception as e:
                print(f"Image {i+1} failed after retries: {e}")
                fallback = f"images/fallback_{i}.jpg"
                path = f"{WORK_DIR}/image_{i}.jpg"
                if os.path.exists(fallback):
                    import shutil
                    shutil.copy(fallback, path)
                    print(f"Using fallback image {i+1}")
                else:
                    Image.new("RGB", (1080, 1080), (5, 5, 10)).save(path, "JPEG")
                    print(f"Using dark fallback for image {i+1}")
            image_paths.append(path)
            time.sleep(2)

        voice_path, srt_path = generate_voice(scenes, gender)

        question   = content.get("question", "Have you ever experienced something you cannot explain?")
        music_path = generate_music(title, scenes)
        video_path = build_video(image_paths, voice_path, srt_path, scenes, title, question, music_path)

        video_id = upload_reel(video_path, caption)
        log_result(title, video_id, "success")
        print(f"\nDone! {title}")

    except Exception as e:
        print(f"\nError: {e}")
        log_result(content["title"] if content else "unknown", video_id, "failed", str(e))
        raise

if __name__ == "__main__":
    main()
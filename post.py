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
# ElevenLabs is optional — falls back to Edge TTS if missing or quota exceeded
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")

# ============================================================
# PATHS
# ============================================================
WORK_DIR    = "/tmp/horrorbot"
VOICE_FILE  = f"{WORK_DIR}/voice.mp3"
VTT_FILE    = f"{WORK_DIR}/voice.vtt"
SRT_FILE    = f"{WORK_DIR}/voice.srt"
VIDEO_FILE  = f"{WORK_DIR}/reel.mp4"
DB_FILE     = "horror_log.db"
os.makedirs(WORK_DIR, exist_ok=True)

# ============================================================
# HORROR THEMES
# ============================================================
# No static list needed — Groq inventsi a fresh unique theme
# every single run based on Filipino horror culture.
# This means zero repetition, infinite variety, always fresh.
# ============================================================

# ============================================================
# FALLBACK
# ============================================================
FALLBACK = {
    "title": "The Third Floor",
    "caption": "He went up for ten minutes. He never came back the same. 👻",
    "hashtags": "#Horror #ScaryStories #GhostStories #Paranormal #Supernatural #HauntedPlace #TrueHorror #NightmareFuel #Creepy #Unexplained #DarkStories #HorrorShorts #StoryTime #Eerie #Thriller #SweetyStoryLab",
    "question": "Have you ever heard footsteps when nobody was there?",
    "scenes": [
        {
            "narration": "We moved into a new apartment last June. The neighbor warned us. Nobody lives on the third floor. First week was quiet. Second week, we heard footsteps every midnight.",
            "image_prompt": "dark apartment building hallway at night, flickering light, eerie fog, no people, cinematic horror"
        },
        {
            "narration": "One night Mark decided to go up. Ten minutes, he said. He never came back in ten minutes. We searched every corner of that floor.",
            "image_prompt": "dark staircase leading up into darkness, single light at top, abandoned building, horror atmosphere"
        },
        {
            "narration": "We found him sitting in the corner. Staring at the wall. Not moving. Not answering. Until now, he will not tell us what he saw up there.",
            "image_prompt": "dark empty room corner with single dim light, eerie shadow on wall, abandoned, psychological horror"
        }
    ]
}

# ============================================================
# STEP 1: GENERATE STORY WITH GROQ
# ============================================================
def generate_story():
    # No theme passed in — Groq picks its own fresh theme every time
    print("Generating fresh horror theme and story with Groq...")

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Filipino horror story writer for Facebook Reels. "
                    "You are a master horror storyteller with knowledge of horror from around the world: "
                    "Filipino folklore (aswang, manananggal, tikbalang, white lady, multo, engkanto), "
                    "urban legends, haunted places, paranormal encounters, ghost stories, "
                    "creepy mysteries, supernatural events, psychological horror, and unexplained phenomena. "
                    "Stories can be set anywhere — provinces, cities, hospitals, highways, hotels, forests, "
                    "schools, old houses, beaches, or any eerie location worldwide. "
                    "IMPORTANT: Always write in ENGLISH ONLY. No Tagalog or Filipino words ever. "
                    "Short punchy sentences. Max 10 words per sentence. "
                    "No gore. Psychological fear only. True story style. "
                    "Always end with an unanswered mystery or twist."
                )
            },
            {
                "role": "user",
                "content": """First, invent a unique and original Filipino horror theme.
Be creative — mix creatures, settings, and situations in unexpected ways.
Avoid repeating common themes. Think of something fresh and specific.

Then write a complete 3-scene horror story based on your invented theme.

Each scene is ~25-30 words. Short sentences. Build fear slowly.
Scene 1 = hook and setup
Scene 2 = tension and discovery
Scene 3 = twist or unanswered mystery

CRITICAL RULES:
- Everything in ENGLISH ONLY. No Tagalog. No Filipino words ever.
- Hashtags must be relevant to THIS specific story — not generic every time.

Output ONLY this exact format, nothing else:
Theme: (your invented horror theme, 1 line, English only)
Title: (max 5 words, mysterious, English only)
Caption: (1 punchy Facebook line, max 15 words, add 👻, English only)
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
Scene1Narration: (25-30 words, ENGLISH ONLY, short sentences)
Scene1Image: (cinematic dark horror scene, no people, no text, eerie atmosphere)
Scene2Narration: (25-30 words, ENGLISH ONLY, short sentences)
Scene2Image: (cinematic dark horror scene, no people, no text)
Scene3Narration: (25-30 words, ENGLISH ONLY, short sentences)
Scene3Image: (cinematic dark horror scene, no people, no text, dramatic)
Question: (1 engaging question for viewers, max 12 words, makes them comment. Examples: "Have you ever experienced something you cannot explain?" "What would you have done in this situation?" "Do you believe this really happened?")"""
            }
        ],
        "temperature": 0.95,
        "max_tokens": 700
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
        "hashtags": "#HorrorPH #PinoyHorror #TrueStoryPH #GabiNgMulto #SweetyStoryLab",
        "scenes": [{"narration": "", "image_prompt": ""} for _ in range(3)],
        "question": "Have you ever experienced something you cannot explain?"
    }
    text = text.replace("**", "").replace("*", "")
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        if line.startswith("Theme:"):
            # Log the AI-invented theme for transparency
            print(f"AI invented theme: {line.replace('Theme:', '').strip()}")
        elif line.startswith("Title:"):
            result["title"] = line.replace("Title:", "").strip().strip('"')
        elif line.startswith("Caption:"):
            result["caption"] = line.replace("Caption:", "").strip().strip('"')
        elif line.startswith("Hashtags:"):
            result["hashtags"] = line.replace("Hashtags:", "").strip()
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
            print(f"Story: {content['title']}")
            return content
    except Exception as e:
        print(f"Groq failed: {e}")
    print("Using fallback...")
    return FALLBACK

# ============================================================
# STEP 2: GENERATE 3 HORROR IMAGES WITH POLLINATIONS.AI
# ============================================================
# Pollinations.ai is a completely free AI image generator.
# No API key needed — just call a URL with the prompt.
# We generate one image per scene with a random seed each time
# so every post gets unique images even with similar prompts.
# Falls back to a plain dark image if Pollinations is down.
# ============================================================
def generate_image(prompt, index):
    print(f"Generating image {index+1}/3...")
    # Add cinematic horror keywords to boost image quality
    full_prompt = (
        f"{prompt}, dark cinematic horror, eerie atmosphere, "
        "dramatic lighting, photorealistic, high quality, "
        "no text, no watermark, no faces"
    )
    encoded = requests.utils.quote(full_prompt)
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true&seed={seed}"
    res = requests.get(url, timeout=90)
    res.raise_for_status()
    path = f"{WORK_DIR}/image_{index}.jpg"
    with open(path, "wb") as f:
        f.write(res.content)
    print(f"Image {index+1} saved!")
    return path

# ============================================================
# STEP 3: GENERATE VOICE + SUBTITLES
# ============================================================
# We use a hybrid approach for best quality + zero cost:
#
# PRIMARY — ElevenLabs (emotional, dramatic, horror-perfect)
#   - Uses "Daniel" voice: deep, storytelling, expressive
#   - Free tier: 10,000 chars/month (resets monthly)
#   - Generates voice.mp3 directly
#   - Falls back to Edge TTS if quota exceeded or key missing
#
# FALLBACK — Edge TTS (Microsoft neural voices, always free)
#   - Uses en-US-GuyNeural: deep, clear, dramatic male voice
#   - No quota, no API key, runs forever
#   - Also generates .vtt subtitle file for synced captions
#
# Both paths produce voice.mp3 + voice.srt for FFmpeg.
# ============================================================

def generate_voice_elevenlabs(text):
    """
    Generate voice using ElevenLabs API.
    Uses 'Daniel' voice — deep, expressive, perfect for horror.
    Returns True if successful, False if quota exceeded or error.
    """
    print("Trying ElevenLabs voice (emotional)...")

    # Fetch available voices from account and pick best one for horror
    # This avoids hardcoded IDs that may not exist on free accounts
    try:
        voices_res = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=10
        )
        voices = voices_res.json().get("voices", [])
        # Prefer deep/dramatic voices for horror
        preferred = ["Daniel", "Adam", "Antoni", "Josh", "Arnold", "Thomas"]
        VOICE_ID = None
        for name in preferred:
            match = next((v for v in voices if v["name"] == name), None)
            if match:
                VOICE_ID = match["voice_id"]
                print(f"Using ElevenLabs voice: {name}")
                break
        # Fall back to first available voice if none of preferred found
        if not VOICE_ID and voices:
            VOICE_ID = voices[0]["voice_id"]
            print(f"Using ElevenLabs voice: {voices[0]['name']}")
        if not VOICE_ID:
            print("No voices found on ElevenLabs account")
            return False
    except Exception as e:
        print(f"Could not fetch voices: {e}")
        return False

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.4,        # Lower = more expressive/emotional
            "similarity_boost": 0.8, # Higher = stays true to voice character
            "style": 0.5,            # Style exaggeration for drama
            "use_speaker_boost": True
        }
    }

    try:
        res = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers=headers,
            json=payload,
            timeout=60
        )

        # 429 = quota exceeded, fall back to Edge TTS
        if res.status_code == 429:
            print("⚠️ ElevenLabs quota exceeded — falling back to Edge TTS")
            return False

        res.raise_for_status()

        # Save the audio file
        with open(VOICE_FILE, "wb") as f:
            f.write(res.content)

        print("✅ ElevenLabs voice generated!")
        return True

    except Exception as e:
        print(f"⚠️ ElevenLabs failed: {e} — falling back to Edge TTS")
        return False

def generate_voice_edgetts(text):
    """
    Generate voice using Edge TTS (free, no quota).
    Also generates .vtt subtitle file for synced captions.
    """
    print("Generating voice with Edge TTS (GuyNeural)...")

    result = subprocess.run(
        [
            "edge-tts",
            "--voice", "en-US-GuyNeural",
            "--rate=-10%",
            "--text", text,
            "--write-media", VOICE_FILE,
            "--write-subtitles", VTT_FILE
        ],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise Exception(f"Edge TTS failed: {result.stderr}")

    print("✅ Edge TTS voice generated!")

def generate_srt_from_voice(text):
    """
    Generate SRT subtitles by estimating word timing from audio duration.
    Used when ElevenLabs generates the voice (no .vtt file available).
    We estimate timing based on average speaking pace (~2.5 words/second).
    """
    # Get actual audio duration
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", VOICE_FILE],
        capture_output=True, text=True
    )
    duration = float(json.loads(probe.stdout)["streams"][0]["duration"])

    words = text.split()
    total_words = len(words)
    # Time per word based on actual audio length
    time_per_word = duration / total_words if total_words > 0 else 0.4

    srt_blocks = []
    counter = 1
    chunk_size = 6  # Words per subtitle line

    for i in range(0, total_words, chunk_size):
        chunk = words[i:i + chunk_size]
        start_time = i * time_per_word
        end_time = min((i + chunk_size) * time_per_word, duration)

        # Format as SRT timestamp 00:00:00,000
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
    print(f"✅ SRT generated from timing estimate ({counter-1} blocks)")

def generate_voice(scenes):
    """
    Main voice generation function.
    Tries ElevenLabs first, falls back to Edge TTS.
    Always produces voice.mp3 + voice.srt for FFmpeg.
    """
    # Combine all 3 scene narrations
    full_narration = " ".join(s["narration"] for s in scenes)
    clean = full_narration.replace("#", "").replace("👻", "").replace("...", ". ").strip()

    used_elevenlabs = False

    # Try ElevenLabs if API key is available
    if ELEVENLABS_API_KEY:
        used_elevenlabs = generate_voice_elevenlabs(clean)

    if used_elevenlabs:
        # ElevenLabs doesn't give us a subtitle file
        # so we estimate subtitle timing from audio duration
        generate_srt_from_voice(clean)
    else:
        # Edge TTS — free fallback, generates .vtt which we convert to .srt
        generate_voice_edgetts(clean)
        vtt_to_srt(VTT_FILE, SRT_FILE)

    print(f"Voice ready! ({'ElevenLabs' if used_elevenlabs else 'Edge TTS'})")
    return VOICE_FILE, SRT_FILE

def vtt_to_srt(vtt_path, srt_path):
    """
    Convert WebVTT (.vtt) subtitle file to SRT (.srt) format.

    Why: Edge TTS outputs .vtt format but FFmpeg's subtitle
    filter works best with .srt format.

    VTT format:                    SRT format:
    WEBVTT                         1
                                   00:00:01,000 --> 00:00:03,000
    00:00:01.000 --> 00:00:03.000  First subtitle text
    First subtitle text
                                   2
                                   00:00:03,500 --> 00:00:05,000
    00:00:03.500 --> 00:00:05.000  Second subtitle text
    Second subtitle text

    Key differences:
    - VTT uses dots for milliseconds, SRT uses commas
    - VTT has positioning tags we need to remove
    - VTT has word-level timing tags like <00:00:01.500><c>word</c>
    """
    with open(vtt_path, "r", encoding="utf-8") as f:
        raw = f.read()

    raw = re.sub(r"WEBVTT\n", "", raw)
    raw = re.sub(r"NOTE[^\n]*\n[^\n]*\n", "", raw)

    blocks = raw.strip().split("\n\n")
    srt_out = []
    counter = 1

    for block in blocks:
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if not lines:
            continue
        timing_line = next((l for l in lines if "-->" in l), None)
        if not timing_line:
            continue

        # VTT uses dots, SRT uses commas for milliseconds
        timing = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", timing_line)
        timing = re.sub(r"\s+(align|position|line|size):\S+", "", timing).strip()

        # Extract text, remove all VTT tags
        text_lines = [l for l in lines if "-->" not in l]
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text).strip()
        # Remove any leading number artifacts like "4 " or "12."
        text = re.sub(r"^\d+[\s\.]+", "", text).strip()

        if text:
            srt_out.append(f"{counter}\n{timing}\n{text}")
            counter += 1

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(srt_out))
    print(f"SRT created: {counter-1} subtitle blocks")

# ============================================================
# STEP 3.5: GENERATE BACKGROUND MUSIC WITH MUSICGEN
# ============================================================
# MusicGen is Meta's free AI music model hosted on Hugging Face.
# No API key needed — uses the free inference API.
# We ask Groq to generate a music prompt based on the story theme,
# then MusicGen creates a unique suspense track for each post.
# This means zero copyright risk — every track is AI generated.
#
# Model: facebook/musicgen-small (fast, free, good quality)
# Output: WAV file, ~30 seconds, converted to MP3 for FFmpeg
# Fallback: uses sounds/suspense.mp3 if MusicGen fails
# ============================================================

MUSIC_FILE = f"{WORK_DIR}/music.wav"
MUSIC_MP3  = f"{WORK_DIR}/music.mp3"

def generate_music_prompt(title, scenes):
    """
    Ask Groq to write a MusicGen prompt based on the story.
    Different stories get different music moods:
    - Ghost story → eerie strings, slow piano
    - Aswang → dark Filipino folk, tension
    - Haunted house → orchestral horror, building dread
    """
    print("Generating music prompt with Groq...")
    story_summary = f"Title: {title}. " + " ".join(s["narration"][:50] for s in scenes)

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {
                "role": "system",
                "content": "You write short music prompts for AI music generation. Max 20 words. Describe mood, instruments, tempo only."
            },
            {
                "role": "user",
                "content": f"Write a MusicGen prompt for background horror music that fits this story: {story_summary}. Focus on mood and instruments. No lyrics. Max 20 words."
            }
        ],
        "temperature": 0.7,
        "max_tokens": 50
    }
    res = requests.post("https://api.groq.com/openai/v1/chat/completions",
                        headers=headers, json=payload, timeout=15)
    res.raise_for_status()
    prompt = res.json()["choices"][0]["message"]["content"].strip()
    print(f"Music prompt: {prompt}")
    return prompt

def generate_music(title, scenes):
    """
    Generate unique background music using MusicGen via Hugging Face.
    Falls back to local suspense.mp3 if generation fails.
    """
    print("Generating background music with MusicGen...")

    try:
        # Get story-specific music prompt from Groq
        music_prompt = generate_music_prompt(title, scenes)

        # Call Hugging Face MusicGen API
        # musicgen-small is fast and free on HF inference API
        headers = {"Content-Type": "application/json"}
        payload = {
            "inputs": music_prompt,
            "parameters": {
                "max_new_tokens": 512,  # ~30 seconds of music
                "duration": 30          # 30 second track
            }
        }

        print("Calling MusicGen on Hugging Face...")
        res = requests.post(
            "https://api-inference.huggingface.co/models/facebook/musicgen-small",
            headers=headers,
            json=payload,
            timeout=120  # MusicGen can be slow on free tier
        )

        if res.status_code == 503:
            print("⚠️ MusicGen model loading — retrying in 20s...")
            time.sleep(20)
            res = requests.post(
                "https://api-inference.huggingface.co/models/facebook/musicgen-small",
                headers=headers,
                json=payload,
                timeout=120
            )

        res.raise_for_status()

        # Save WAV file
        with open(MUSIC_FILE, "wb") as f:
            f.write(res.content)

        # Convert WAV to MP3 for FFmpeg mixing
        subprocess.run([
            "ffmpeg", "-y", "-i", MUSIC_FILE,
            "-codec:a", "libmp3lame", "-q:a", "2",
            MUSIC_MP3
        ], check=True, capture_output=True)

        print(f"✅ AI music generated!")
        return MUSIC_MP3

    except Exception as e:
        print(f"⚠️ MusicGen failed: {e}")
        # Fallback to local suspense music if it exists
        if os.path.exists("sounds/suspense.mp3"):
            print("Using local suspense.mp3 as fallback")
            return "sounds/suspense.mp3"
        print("No fallback music available — posting without music")
        return None

# ============================================================
# STEP 4: BUILD VIDEO — 3-IMAGE SLIDESHOW + VOICE + SUBTITLES
# ============================================================
# FFmpeg is a free, powerful video processing tool.
# Pre-installed on GitHub Actions ubuntu runners — no setup needed.
#
# Our video building process:
#   A. Build one 1080x1920 frame per scene using Pillow
#      - Blurred dark background from the horror image
#      - Original image centered in the middle
#      - Dark gradient overlay for text readability
#      - Title at top, scene dots, brand name at bottom
#   B. Create a concat file listing each frame + its duration
#      (total audio duration / 3 scenes = seconds per frame)
#   C. FFmpeg stitches frames into a slideshow video
#   D. FFmpeg adds voice audio + burns subtitles onto video
#
# Output: 1080x1920 MP4, H.264 video + AAC audio
# Facebook Reels requires exactly this format.
# ============================================================
def build_video(image_paths, voice_path, srt_path, scenes, title, question, music_path=None):
    print("Building video with FFmpeg...")

    # Get total audio duration
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", voice_path],
        capture_output=True, text=True
    )
    total_duration = float(json.loads(probe.stdout)["streams"][0]["duration"])
    scene_duration = total_duration / 3
    print(f"Total: {total_duration:.1f}s — Each scene: {scene_duration:.1f}s")

    # Build one background frame per scene
    scene_frames = []
    for i, (img_path, scene) in enumerate(zip(image_paths, scenes)):
        frame_path = build_frame(img_path, title, i)
        scene_frames.append((frame_path, scene_duration))

    # Add question slide at the end — 4 seconds using last horror image
    # Heavily darkened so question text stands out
    question_frame = build_question_frame(question, image_paths[-1])
    scene_frames.append((question_frame, 4.0))  # 4 seconds for question

    # Create FFmpeg concat file for slideshow
    concat_file = f"{WORK_DIR}/concat.txt"
    with open(concat_file, "w") as f:
        for frame_path, duration in scene_frames:
            f.write(f"file '{frame_path}'\n")
            f.write(f"duration {duration:.3f}\n")
        # FFmpeg needs last file repeated without duration
        f.write(f"file '{scene_frames[-1][0]}'\n")

    # Temp video without audio
    temp_video = f"{WORK_DIR}/temp_video.mp4"
    padded_voice = f"{WORK_DIR}/voice_padded.mp3"

    # Pad voice audio with 4 seconds of silence at the end
    # This ensures the question slide (4s) plays fully before video ends
    # Without this, -shortest cuts the video when narration ends
    # We use libmp3lame codec since input is mp3
    pad_result = subprocess.run([
        "ffmpeg", "-y",
        "-i", voice_path,
        "-af", "apad=pad_dur=4",
        "-codec:a", "libmp3lame",
        "-q:a", "2",
        padded_voice
    ], capture_output=True)
    if pad_result.returncode != 0:
        # If padding fails just use original voice
        print("⚠️ Audio padding failed — using original voice")
        padded_voice = voice_path
    else:
        print("✅ Audio padded with 4s silence for question slide")

    # Step A: Build slideshow with smooth crossfade transitions between scenes
    # We use FFmpeg's xfade filter to blend frames smoothly.
    # Each transition = 0.8 second crossfade overlap between slides.
    # Process: load each frame separately, chain xfade filters together.
    num_frames = len(scene_frames)
    fade_duration = 0.8  # seconds for each crossfade

    if num_frames == 1:
        # Only one frame — no transitions needed
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", scene_frames[0][0],
            "-t", str(scene_frames[0][1]),
            "-vf", "scale=1080:1920,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            temp_video
        ], check=True, capture_output=True)
    else:
        # Build xfade filter chain for smooth crossfades
        # Each frame is loaded as separate input with its duration
        # xfade filter blends them: offset = cumulative time - fade_duration
        inputs = []
        for frame_path, duration in scene_frames:
            inputs += ["-loop", "1", "-t", str(duration + fade_duration), "-i", frame_path]

        # Build filter chain: [0][1]xfade=offset=T1, [fade1][2]xfade=offset=T2, etc.
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
        filter_complex += f",scale=1080:1920,fps=30"

        result = subprocess.run([
            "ffmpeg", "-y",
        ] + inputs + [
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", "30", temp_video
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"⚠️ Crossfade failed: {result.stderr[-300:]} — falling back to hard cuts")
            # Fallback to simple concat if xfade fails
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-vf", "scale=1080:1920,fps=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-r", "30", temp_video
            ], check=True, capture_output=True)
        else:
            print("✅ Slideshow with crossfade transitions built!")

    # Step B: Add voice + background music + burned subtitles
    # Subtitle style: white text, black outline, centered bottom
    subtitle_style = (
        "FontName=Arial,"
        "FontSize=11,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&H80000000,"
        "Bold=1,"
        "Outline=3,"
        "Shadow=2,"
        "Alignment=2,"      # Bottom center
        "MarginV=120"       # Above brand name
    )

    # Use AI generated music or fallback
    has_music = music_path is not None and os.path.exists(music_path)

    if has_music:
        print(f"Mixing in background music at 15% volume: {music_path}")
        # FFmpeg audio mixing explanation:
        # -i temp_video   = our slideshow video (no audio)
        # -i voice_path   = the narration voice (foreground)
        # -i music_path   = suspense music (background)
        # -stream_loop -1 = loop music infinitely if shorter than video
        # amix filter:
        #   inputs=2      = mix voice + music together
        #   weights=1 0.15 = voice at 100%, music at 15%
        #   duration=first = stop when voice ends
        # normalize=0    = don't auto-normalize (keeps our volumes)
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", padded_voice,
            "-stream_loop", "-1", "-i", music_path,
            "-c:v", "libx264",
            "-vf", f"subtitles={srt_path}:force_style='{subtitle_style}'",
            "-filter_complex",
            "[1:a][2:a]amix=inputs=2:weights=1 0.15:duration=first:normalize=0[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            VIDEO_FILE
        ], capture_output=True, text=True, timeout=180)
    else:
        print("No suspense music found — posting voice only...")
        # Fallback: no background music, just voice
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", padded_voice,
            "-c:v", "libx264",
            "-vf", f"subtitles={srt_path}:force_style='{subtitle_style}'",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            VIDEO_FILE
        ], capture_output=True, text=True, timeout=180)

    if result.returncode != 0:
        raise Exception(f"FFmpeg final failed: {result.stderr[-500:]}")

    size_mb = os.path.getsize(VIDEO_FILE) / 1024 / 1024
    print(f"Video built! ({size_mb:.1f}MB)")
    return VIDEO_FILE

def build_frame(img_path, title, scene_index):
    """Build a single 1080x1920 frame for one scene"""
    img = Image.open(img_path).convert("RGB")

    # Blurred dark background
    bg = img.resize((1080, 1920), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=25))
    darkener = Image.new("RGB", (1080, 1920), (0, 0, 0))
    bg = Image.blend(bg, darkener, 0.6)

    # Main image centered
    img_main = img.resize((1080, 1080), Image.LANCZOS)

    # Gradient overlay on image bottom for subtitle readability
    grad = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(grad)
    for i in range(500):
        alpha = int((i / 500) * 220)
        grad_draw.rectangle([0, 580 + i, 1080, 581 + i], fill=(0, 0, 0, alpha))
    img_rgba = img_main.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, grad)
    img_main = img_rgba.convert("RGB")

    canvas = bg.copy()
    canvas.paste(img_main, (0, 420))  # Centered vertically

    # Dark top bar for title
    canvas_rgba = canvas.convert("RGBA")
    top_bar = Image.new("RGBA", (1080, 380), (0, 0, 0, 200))
    canvas_rgba.paste(top_bar, (0, 0), top_bar)
    canvas = canvas_rgba.convert("RGB")

    draw = ImageDraw.Draw(canvas)

    try:
        font_title = ImageFont.truetype("/tmp/Lora-Italic.ttf", 48)  # Smaller title
        font_brand = ImageFont.truetype("/tmp/Lora-Italic.ttf", 26)  # Smaller brand
        font_scene = ImageFont.truetype("/tmp/Lora-Italic.ttf", 22)  # Smaller dots
    except:
        font_title = font_brand = font_scene = ImageFont.load_default()

    # Title — truncate if too long so it fits on screen
    display_title = title if len(title) <= 28 else title[:25] + "..."
    draw.text((542, 152), display_title, font=font_title, fill=(0,0,0,200), anchor="mm")
    draw.text((540, 150), display_title, font=font_title, fill=(255,255,255,255), anchor="mm")

    # Decorative line under title
    draw.rectangle([300, 200, 780, 203], fill=(255,255,255,140))

    # Scene indicator
    dots = "● " * (scene_index + 1) + "○ " * (2 - scene_index)
    draw.text((540, 230), dots.strip(), font=font_scene,
              fill=(255,255,255,180), anchor="mm")

    # Brand at very bottom
    draw.text((542, 1882), "SweetyStoryLab", font=font_brand,
              fill=(0,0,0,180), anchor="mm")
    draw.text((540, 1880), "SweetyStoryLab", font=font_brand,
              fill=(255,255,255,160), anchor="mm")

    frame_path = f"{WORK_DIR}/frame_{scene_index}.jpg"
    canvas.save(frame_path, "JPEG", quality=95)
    return frame_path

def build_question_frame(question, last_image_path):
    """
    Build a 4th slide — uses the last horror image as background.
    Heavily darkened so the question text stands out clearly.
    No narration, just eerie music + question text.
    This drives comments which boosts Facebook reach significantly.
    """
    # Use last horror image as background, heavily darkened
    try:
        img = Image.open(last_image_path).convert("RGB")
        # Blurred dark background
        bg = img.resize((1080, 1920), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
        # Very dark overlay — 80% dark so question text is readable
        darkener = Image.new("RGB", (1080, 1920), (0, 0, 0))
        canvas = Image.blend(bg, darkener, 0.80)
    except:
        # Fallback to black if image fails
        canvas = Image.new("RGB", (1080, 1920), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    try:
        font_question = ImageFont.truetype("/tmp/Lora-Italic.ttf", 52)
        font_brand = ImageFont.truetype("/tmp/Lora-Italic.ttf", 26)
        font_comment = ImageFont.truetype("/tmp/Lora-Italic.ttf", 32)
    except:
        font_question = font_brand = font_comment = ImageFont.load_default()

    # Wrap question text — centered vertically on screen
    import textwrap
    wrapped = textwrap.wrap(question, width=22)
    line_height = 72
    total_height = len(wrapped) * line_height
    start_y = 960 - total_height // 2  # Perfectly centered

    # Draw question text — bold white with strong shadow for standout effect
    for i, line in enumerate(wrapped):
        y = start_y + (i * line_height)
        # Strong multi-layer shadow for depth
        for offset in [(3, 3), (2, 2), (1, 1)]:
            draw.text((540 + offset[0], y + offset[1]), line, font=font_question,
                      fill=(0, 0, 0, 180), anchor="mm")
        # Main bright white text
        draw.text((540, y), line, font=font_question,
                  fill=(255, 255, 255, 255), anchor="mm")

    end_y = start_y + len(wrapped) * line_height

    # Brand name at very bottom
    draw.text((542, 1882), "SweetyStoryLab", font=font_brand,
              fill=(150, 150, 150, 180), anchor="mm")
    draw.text((540, 1880), "SweetyStoryLab", font=font_brand,
              fill=(255, 255, 255, 160), anchor="mm")

    frame_path = f"{WORK_DIR}/frame_question.jpg"
    canvas.save(frame_path, "JPEG", quality=95)
    print("✅ Question slide built!")
    return frame_path

# ============================================================
# STEP 5: UPLOAD TO FACEBOOK AS REEL
# ============================================================
# Facebook Reels upload is a 3-step process via Graph API:
#
# Step A — Initialize upload session:
#   POST to /video_reels with upload_phase=start
#   Facebook returns a video_id for this upload session
#
# Step B — Upload the actual video binary:
#   POST the raw MP4 bytes to Facebook's upload server
#   (rupload.facebook.com) using the video_id
#   We send file size and offset in headers so Facebook
#   knows how much data to expect
#
# Step C — Publish the Reel:
#   POST to /video_reels with upload_phase=finish
#   Include the caption (story text + hashtags)
#   Set video_state=PUBLISHED to make it live immediately
#
# Note: Facebook processes the video after upload so there
# may be a short delay before it appears on the page.
# ============================================================
def upload_reel(video_path, caption):
    print("Uploading Reel...")
    file_size = os.path.getsize(video_path)

    # Init
    init = requests.post(
        f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/video_reels",
        data={"upload_phase": "start", "access_token": FB_ACCESS_TOKEN}
    )
    print(f"Init: {init.status_code} - {init.text}")
    init.raise_for_status()
    video_id = init.json()["video_id"]

    # Upload
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

    # Publish
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
# We keep a simple local log of every post attempt.
# SQLite is a lightweight database built into Python —
# no setup needed, stores everything in one file (horror_log.db).
#
# Each row records:
#   - timestamp: when the post was attempted
#   - title: the horror story title
#   - video_id: Facebook's ID for the posted Reel
#   - status: "success" or "failed"
#   - error: error message if it failed
#
# The log file is saved as a GitHub Actions artifact
# so you can download and review it anytime.
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
        # Step 1: Story
        content = get_content()
        title   = content["title"]
        scenes  = content["scenes"]
        caption = f"{content['caption']}\n\n{content['hashtags']}"

        print(f"Title: {title}")

        # Step 2: 3 images (one per scene)
        image_paths = []
        for i, scene in enumerate(scenes):
            try:
                path = generate_image(scene["image_prompt"], i)
            except Exception as e:
                print(f"Image {i+1} failed: {e} — using dark fallback")
                path = f"{WORK_DIR}/image_{i}.jpg"
                Image.new("RGB", (1080, 1080), (5, 5, 10)).save(path, "JPEG")
            image_paths.append(path)
            time.sleep(2)

        # Step 3: Voice + subtitles
        voice_path, srt_path = generate_voice(scenes)

        # Step 4: Build video
        question   = content.get("question", "Have you ever experienced something you cannot explain?")
        # Generate unique AI music based on story theme
        music_path = generate_music(title, scenes)
        video_path = build_video(image_paths, voice_path, srt_path, scenes, title, question, music_path)

        # Step 5: Upload
        video_id = upload_reel(video_path, caption)

        # Step 6: Log
        log_result(title, video_id, "success")
        print(f"\nDone! {title}")

    except Exception as e:
        print(f"\nError: {e}")
        log_result(content["title"] if content else "unknown", video_id, "failed", str(e))
        raise

if __name__ == "__main__":
    main()

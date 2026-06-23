# ============================================================
# post.py — Daily Facebook Reels Horror Bot for SweetyStoryLab
# ============================================================
# Runs 3x daily via GitHub Actions: 8AM / 2PM / 8PM PHT
# Full pipeline:
#   1. Generate Taglish horror story (Groq)
#   2. Generate voice narration (Edge TTS - natural voice)
#   3. Generate horror image (Pollinations.ai)
#   4. Build 1080x1920 vertical video (FFmpeg)
#   5. Upload as Facebook Reel (Graph API)
#   6. Log result (SQLite)

import os
import random
import requests
import time
import base64
import io
import json
import sqlite3
import subprocess
import textwrap
import asyncio
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ============================================================
# SECRETS
# ============================================================
FB_ACCESS_TOKEN = os.environ["FB_PAGE_ACCESS_TOKEN"]
FB_PAGE_ID = os.environ["FB_PAGE_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# ============================================================
# PATHS
# ============================================================
WORK_DIR = "/tmp/horrorbot"
VOICE_FILE = f"{WORK_DIR}/voice.mp3"
IMAGE_FILE = f"{WORK_DIR}/image.jpg"
BG_FILE = f"{WORK_DIR}/bg.jpg"
VIDEO_FILE = f"{WORK_DIR}/reel.mp4"
DB_FILE = "horror_log.db"

os.makedirs(WORK_DIR, exist_ok=True)

# ============================================================
# HORROR THEMES
# ============================================================
HORROR_THEMES = [
    "aswang sa probinsya ng Capiz",
    "white lady sa NLEX highway",
    "multo sa lumang ospital sa Maynila",
    "tikbalang sa bundok ng Rizal",
    "manananggal sa probinsya",
    "haunted dormitory sa Maynila",
    "mysterious passenger sa Grab late at night",
    "abandoned house sa subdivision",
    "engineer na nakakita ng multo sa gabi shift",
    "nawawalang bata sa palengke",
    "kwarto sa hotel na hindi dapat puntahan",
    "driver na may naranasang hindi maipaliwanag sa SLEX",
    "babae sa puting damit sa gitna ng bukid",
    "bata na nakikita ang hindi dapat makita",
    "matanda sa probinsya na may lihim",
]

# ============================================================
# FALLBACK CONTENT
# ============================================================
FALLBACK = {
    "title": "The Third Floor",
    "story": "We moved into a new apartment last June. The neighbor said not to worry about the noise upstairs. Nobody lives on the third floor. First week, quiet. Second week, we heard footsteps. Every midnight. Up. Down. Up. Down. One night, Mark decided to go up. Ten minutes, he said. He never came back in ten minutes. We found him sitting in the corner. Staring at the wall. Not moving. Not answering. Until now, he won't tell us what he saw up there.",
    "voice": "We moved into a new apartment last June. The neighbor said not to worry about the noise upstairs. Nobody lives on the third floor. First week, quiet. Second week, we heard footsteps. Every midnight. Mark decided to go up. Ten minutes, he said. We found him sitting in the corner. Staring at the wall. Not moving. Not answering. Until now, he won't tell us what he saw up there.",
    "caption": "He went up for ten minutes. He never came back the same. 👻",
    "hashtags": "#HorrorPH #TrueStoryPH #GabiNgMulto #PinoyHorror #SweetyStoryLab #CreepyPH #ParanormalPH",
    "image_prompt": "dark abandoned apartment building hallway at night, eerie fog, single flickering light, no people, cinematic horror atmosphere"
}

# ============================================================
# STEP 1: GENERATE HORROR STORY WITH GROQ
# ============================================================
def generate_story():
    theme = random.choice(HORROR_THEMES)
    print(f"Generating horror story about: {theme}")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Filipino horror story writer for SweetyStoryLab Facebook Reels. "
                    "Write stories in ENGLISH ONLY — clear, natural, conversational English. "
                    "Short punchy sentences. Maximum 10 words per sentence. "
                    "No gore. Psychological horror only. "
                    "Sound like a true story being told by a friend. "
                    "Always end with an unanswered mystery or twist."
                )
            },
            {
                "role": "user",
                "content": f"""Write a short English horror story inspired by this Filipino theme: {theme}

RULES:
- English only (no Tagalog words)
- Total story: 80-100 words only
- Max 10 words per sentence
- Hook in first sentence
- Build tension slowly
- End with unanswered mystery
- Sound like a true personal story

Output Format (exactly these labels):
Title: (short mysterious title, max 5 words)
Story: (full story 80-100 words, English only)
Voice: (same story, clean for text-to-speech, natural pace)
Caption: (1 punchy line for Facebook, max 15 words, add 👻)
Hashtags: (#HorrorPH #PinoyHorror #TrueStoryPH #GabiNgMulto #CreepyPH #SweetyStoryLab plus 3 more)
Image Prompt: (dark cinematic horror scene, no people, eerie setting, for AI image generation)"""
            }
        ],
        "temperature": 0.95,
        "max_tokens": 600
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"].strip()
    print(f"Groq response received")
    return parse_story(text)

def parse_story(text):
    result = {
        "title": "Night Terror",
        "story": "",
        "voice": "",
        "caption": "Don't read this alone. 👻",
        "hashtags": "#HorrorPH #PinoyHorror #TrueStoryPH #GabiNgMulto #SweetyStoryLab",
        "image_prompt": "dark eerie abandoned house night fog cinematic horror no people"
    }

    text = text.replace("**", "").replace("*", "")
    lines = text.strip().split("\n")
    current_key = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("Title:"):
            result["title"] = line.replace("Title:", "").strip().strip('"')
            current_key = "title"
        elif line.startswith("Story:"):
            result["story"] = line.replace("Story:", "").strip()
            current_key = "story"
        elif line.startswith("Voice:"):
            result["voice"] = line.replace("Voice:", "").strip()
            current_key = "voice"
        elif line.startswith("Caption:"):
            result["caption"] = line.replace("Caption:", "").strip().strip('"')
            current_key = "caption"
        elif line.startswith("Hashtags:"):
            result["hashtags"] = line.replace("Hashtags:", "").strip()
            current_key = "hashtags"
        elif line.startswith("Image Prompt:"):
            result["image_prompt"] = line.replace("Image Prompt:", "").strip()
            current_key = "image"
        else:
            if current_key == "story":
                result["story"] += " " + line
            elif current_key == "voice":
                result["voice"] += " " + line
            elif current_key == "image":
                result["image_prompt"] += " " + line

    if not result["voice"]:
        result["voice"] = result["story"]

    return result

def get_content():
    try:
        content = generate_story()
        if content["story"]:
            print(f"Story generated: {content['title']}")
            return content
    except Exception as e:
        print(f"Groq failed: {e}")
    print("Using fallback content...")
    return FALLBACK

# ============================================================
# STEP 2: GENERATE VOICE WITH EDGE TTS
# ============================================================
# Edge TTS uses Microsoft's neural voices — sounds very natural.
# Completely free, no API key needed.
# Voice: en-US-AriaNeural (warm, clear, great for storytelling)
# ============================================================
def generate_voice(text):
    print("Generating voice with Edge TTS...")

    # Install edge-tts if not available
    subprocess.run(
        ["pip", "install", "edge-tts", "-q"],
        check=True, capture_output=True
    )

    # Clean text for TTS
    clean_text = (text
        .replace("#", "")
        .replace("👻", "")
        .replace("...", ". ")
        .strip()
    )

    # Use edge-tts CLI to generate voice
    # en-US-AriaNeural = warm natural female voice, great for horror storytelling
    result = subprocess.run(
        [
            "edge-tts",
            "--voice", "en-US-AriaNeural",
            "--rate", "-10%",        # Slightly slower = more dramatic
            "--pitch", "-5Hz",       # Slightly lower pitch = creepier
            "--text", clean_text,
            "--write-media", VOICE_FILE
        ],
        capture_output=True,
        text=True,
        timeout=60
    )

    if result.returncode != 0:
        raise Exception(f"Edge TTS failed: {result.stderr}")

    print(f"Voice generated: {VOICE_FILE}")
    return VOICE_FILE

# ============================================================
# STEP 3: GENERATE HORROR IMAGE WITH POLLINATIONS.AI
# ============================================================
def generate_image(image_prompt):
    print("Generating horror image...")

    full_prompt = (
        f"{image_prompt}, "
        "dark horror atmosphere, cinematic, eerie, "
        "dramatic shadows, foggy night, abandoned, photorealistic, "
        "high quality, no text, no watermark, no people faces"
    )

    encoded = requests.utils.quote(full_prompt)
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true&seed={seed}"

    print("Calling Pollinations...")
    response = requests.get(url, timeout=90)
    response.raise_for_status()

    with open(IMAGE_FILE, "wb") as f:
        f.write(response.content)

    print(f"Image saved!")
    return IMAGE_FILE

# ============================================================
# STEP 4: BUILD VIDEO WITH FFMPEG
# ============================================================
def build_video(image_path, voice_path, story_text, title):
    print("Building video with FFmpeg...")

    # Get audio duration
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", voice_path],
        capture_output=True, text=True
    )
    probe_data = json.loads(probe.stdout)
    duration = float(probe_data["streams"][0]["duration"])
    print(f"Audio duration: {duration:.1f}s")

    # ---- Build background frame with Pillow ----
    img = Image.open(image_path).convert("RGB")

    # 1. Blurred dark background fills full 1080x1920
    bg = img.resize((1080, 1920), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=20))
    darkener = Image.new("RGB", (1080, 1920), (0, 0, 0))
    bg = Image.blend(bg, darkener, 0.55)

    # 2. Original image centered in middle (1080x1080)
    img_main = img.resize((1080, 1080), Image.LANCZOS)

    # 3. Dark gradient overlay on image for text readability
    gradient = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for i in range(400):
        alpha = int((i / 400) * 200)
        grad_draw.rectangle([0, 680 + i, 1080, 681 + i], fill=(0, 0, 0, alpha))
    img_main_rgba = img_main.convert("RGBA")
    img_main_rgba = Image.alpha_composite(img_main_rgba, gradient)
    img_main = img_main_rgba.convert("RGB")

    # 4. Paste image into background centered vertically
    canvas = bg.copy()
    y_offset = (1920 - 1080) // 2  # = 420
    canvas.paste(img_main, (0, y_offset))

    # 5. Dark overlay top and bottom for text areas
    canvas_rgba = canvas.convert("RGBA")
    top_bar = Image.new("RGBA", (1080, 400), (0, 0, 0, 210))
    canvas_rgba.paste(top_bar, (0, 0), top_bar)
    bottom_bar = Image.new("RGBA", (1080, 440), (0, 0, 0, 220))
    canvas_rgba.paste(bottom_bar, (0, 1480), bottom_bar)
    canvas = canvas_rgba.convert("RGB")

    draw = ImageDraw.Draw(canvas)

    # ---- Load fonts ----
    try:
        font_title = ImageFont.truetype("/tmp/Lora-Italic.ttf", 72)
        font_story = ImageFont.truetype("/tmp/Lora-Italic.ttf", 54)  # BIGGER TEXT
        font_brand = ImageFont.truetype("/tmp/Lora-Italic.ttf", 32)
        font_swipe = ImageFont.truetype("/tmp/Lora-Italic.ttf", 36)
    except:
        font_title = ImageFont.load_default()
        font_story = ImageFont.load_default()
        font_brand = ImageFont.load_default()
        font_swipe = ImageFont.load_default()

    # ---- Draw title at top ----
    # Shadow
    draw.text((542, 122), title, font=font_title, fill=(0, 0, 0, 200), anchor="mm")
    # Main
    draw.text((540, 120), title, font=font_title, fill=(255, 255, 255, 255), anchor="mm")

    # Decorative line under title
    draw.rectangle([340, 165, 740, 168], fill=(255, 255, 255, 150))

    # ---- Draw story text at bottom ----
    # Word wrap at ~28 chars per line for BIG readable text
    wrapped_lines = textwrap.wrap(story_text, width=28)
    max_lines = 6  # Show max 6 lines
    display_lines = wrapped_lines[:max_lines]
    if len(wrapped_lines) > max_lines:
        display_lines[-1] = display_lines[-1] + "..."

    line_height = 68
    total_text_height = len(display_lines) * line_height
    start_y = 1510

    for i, line in enumerate(display_lines):
        y = start_y + (i * line_height)
        # Shadow
        draw.text((542, y + 2), line, font=font_story, fill=(0, 0, 0, 200), anchor="mm")
        # Main text
        draw.text((540, y), line, font=font_story, fill=(255, 255, 255, 255), anchor="mm")

    # ---- Brand name ----
    draw.text((542, 1882), "SweetyStoryLab", font=font_brand, fill=(0, 0, 0, 180), anchor="mm")
    draw.text((540, 1880), "SweetyStoryLab", font=font_brand, fill=(255, 255, 255, 180), anchor="mm")

    # Save background frame
    canvas.save(BG_FILE, "JPEG", quality=95)
    print("Background frame built!")

    # ---- FFmpeg: image + audio → MP4 ----
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", BG_FILE,
        "-i", voice_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-movflags", "+faststart",
        "-vf", "scale=1080:1920",
        VIDEO_FILE
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise Exception(f"FFmpeg failed: {result.stderr}")

    size_mb = os.path.getsize(VIDEO_FILE) / 1024 / 1024
    print(f"Video built! ({size_mb:.1f}MB)")
    return VIDEO_FILE

# ============================================================
# STEP 5: UPLOAD TO FACEBOOK AS REEL
# ============================================================
def upload_reel(video_path, caption):
    print("Uploading Reel to Facebook...")
    file_size = os.path.getsize(video_path)

    # Step A: Initialize upload
    init_res = requests.post(
        f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/video_reels",
        data={
            "upload_phase": "start",
            "access_token": FB_ACCESS_TOKEN
        }
    )
    print(f"Init: {init_res.status_code} - {init_res.text}")
    init_res.raise_for_status()
    video_id = init_res.json()["video_id"]
    print(f"Video ID: {video_id}")

    # Step B: Upload video binary
    print("Uploading video file...")
    with open(video_path, "rb") as f:
        video_data = f.read()

    upload_res = requests.post(
        f"https://rupload.facebook.com/video-upload/v21.0/{video_id}",
        headers={
            "Authorization": f"OAuth {FB_ACCESS_TOKEN}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "video/mp4"
        },
        data=video_data,
        timeout=300
    )
    print(f"Upload: {upload_res.status_code} - {upload_res.text}")
    upload_res.raise_for_status()

    time.sleep(8)

    # Step C: Publish
    print("Publishing Reel...")
    pub_res = requests.post(
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
    print(f"Publish: {pub_res.status_code} - {pub_res.text}")
    pub_res.raise_for_status()
    print(f"Reel published!")
    return video_id

# ============================================================
# STEP 6: LOG TO SQLITE
# ============================================================
def log_result(title, video_id, status, error=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            title TEXT,
            video_id TEXT,
            status TEXT,
            error TEXT
        )
    """)
    c.execute(
        "INSERT INTO posts (timestamp, title, video_id, status, error) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), title, video_id or "", status, error or "")
    )
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
        # Step 1: Generate story
        content = get_content()
        title = content["title"]
        story = content["story"]
        voice_text = content.get("voice", story)
        caption = f"{content['caption']}\n\n{content['hashtags']}"
        image_prompt = content["image_prompt"]

        print(f"\nTitle: {title}")
        print(f"Story: {story[:80]}...")

        # Step 2: Generate voice
        voice_path = generate_voice(voice_text)

        # Step 3: Generate image
        try:
            image_path = generate_image(image_prompt)
        except Exception as e:
            print(f"Pollinations failed: {e} — using dark fallback")
            img = Image.new("RGB", (1080, 1080), (5, 5, 10))
            img.save(IMAGE_FILE, "JPEG")
            image_path = IMAGE_FILE

        # Step 4: Build video
        video_path = build_video(image_path, voice_path, story, title)

        # Step 5: Upload Reel
        video_id = upload_reel(video_path, caption)

        # Step 6: Log
        log_result(title, video_id, "success")
        print(f"\nDone! Reel posted: {title}")

    except Exception as e:
        print(f"\nError: {e}")
        log_result(
            content["title"] if content else "unknown",
            video_id,
            "failed",
            str(e)
        )
        raise

if __name__ == "__main__":
    main()

# ============================================================
# post.py — Daily Facebook Reels Horror Bot for SweetyStoryLab
# ============================================================
# Runs 3x daily via GitHub Actions: 8AM / 2PM / 8PM PHT
# Full pipeline:
#   1. Generate Taglish horror story (Groq)
#   2. Generate voice narration (Piper TTS)
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
VOICE_FILE = f"{WORK_DIR}/voice.wav"
IMAGE_FILE = f"{WORK_DIR}/image.jpg"
BG_FILE = f"{WORK_DIR}/bg.jpg"
VIDEO_FILE = f"{WORK_DIR}/reel.mp4"
SUBTITLE_FILE = f"{WORK_DIR}/subs.srt"
DB_FILE = "horror_log.db"
PIPER_BIN = f"{WORK_DIR}/piper/piper"
PIPER_MODEL = f"{WORK_DIR}/piper/en_US-lessac-medium.onnx"

os.makedirs(WORK_DIR, exist_ok=True)

# ============================================================
# HORROR THEMES — picked randomly each run
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
    "title": "Ang Babae sa Ikatlong Palapag",
    "story": "Lumipat kami sa bagong apartment noong Hunyo. Sabi ng kapitbahay, huwag kaming mag-alala sa ingay sa itaas. Walang nakatira sa ikatlong palapag. Unang linggo, tahimik. Ikalawang linggo, nagsimula kaming marinig ang mga yapak. Tuwing hatinggabi. Pataas. Pababa. Isang gabi, nagdesisyon si Mark na umakyat. Sampung minuto lang daw siya. Hindi na siya bumalik ng sampung minuto. Nandoon pa rin siya. Nakaupo sa sulok. Nakatingin sa dingding. Hindi sumasagot. Hanggang ngayon, hindi namin alam kung sino ang nakausap niya doon.",
    "caption": "Hindi kami naniwala sa mga kwento ng kapitbahay... hanggang sa isang gabi. 👻",
    "hashtags": "#HorrorPH #TrueStoryPH #GabiNgMulto #PinoyHorror #SweetyStoryLab #CreepyPH #ParanormalPH",
    "image_prompt": "dark abandoned apartment building hallway at night, eerie fog, single flickering light, no people, cinematic horror atmosphere",
    "voice_text": "Lumipat kami sa bagong apartment noong Hunyo. Sabi ng kapitbahay, huwag kaming mag-alala sa ingay sa itaas. Walang nakatira sa ikatlong palapag. Unang linggo, tahimik. Ikalawang linggo, nagsimula kaming marinig ang mga yapak. Tuwing hatinggabi. Isang gabi, nagdesisyon si Mark na umakyat. Sampung minuto lang daw siya. Hindi na siya bumalik. Nandoon pa rin siya. Nakaupo sa sulok. Nakatingin sa dingding. Hindi sumasagot. Hanggang ngayon, hindi namin alam kung sino ang nakausap niya doon."
}

# ============================================================
# STEP 1: GENERATE HORROR STORY WITH GROQ
# ============================================================
def generate_story():
    theme = random.choice(HORROR_THEMES)
    print(f"🎃 Generating horror story about: {theme}")

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
                    "Write in Taglish — natural Filipino-English mix. "
                    "Stories must be short, punchy, suspenseful. "
                    "Each sentence is maximum 10 words. Short sentences create fear. "
                    "No gore. Psychological horror only. Always end with an unanswered mystery."
                )
            },
            {
                "role": "user",
                "content": f"""Write a short Filipino horror story about: {theme}

RULES:
- Total story: 80-120 words only
- Each sentence: maximum 10 words
- Taglish (mix Filipino + English naturally)  
- Hook in first sentence
- Build tension slowly
- End with unanswered mystery or twist
- Sound like a true story from a friend

Output Format (exactly these labels):
Title: (short mysterious title, max 5 words)
Story: (the full story, 80-120 words)
Voice: (same story but cleaner for text-to-speech, remove punctuation drama, natural speaking pace)
Caption: (1 punchy English line for Facebook caption, max 15 words)
Hashtags: (#HorrorPH #PinoyHorror #TrueStoryPH #GabiNgMulto #CreepyPH #SweetyStoryLab plus 3 more relevant)
Image Prompt: (dark cinematic horror scene, no people, eerie Filipino setting, for AI image generation)"""
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
    print(f"✅ Groq response received")
    return parse_story(text)

def parse_story(text):
    result = {
        "title": "Kwentong Gabi",
        "story": "",
        "voice": "",
        "caption": "Huwag basahin ito sa madilim. 👻",
        "hashtags": "#HorrorPH #PinoyHorror #TrueStoryPH #GabiNgMulto #SweetyStoryLab",
        "image_prompt": "dark eerie Filipino province abandoned house night fog cinematic horror"
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
            if current_key == "story" and result["story"]:
                result["story"] += " " + line
            elif current_key == "voice" and result["voice"]:
                result["voice"] += " " + line
            elif current_key == "image" and result["image_prompt"]:
                result["image_prompt"] += " " + line

    # Use story as voice if voice is empty
    if not result["voice"]:
        result["voice"] = result["story"]

    return result

def get_content():
    try:
        content = generate_story()
        if content["story"]:
            print(f"✅ Story: {content['title']}")
            return content
    except Exception as e:
        print(f"⚠️ Groq failed: {e}")
    print("⚠️ Using fallback content...")
    return FALLBACK

# ============================================================
# STEP 2: GENERATE VOICE WITH PIPER TTS
# ============================================================
# Piper is a free, fast, offline text-to-speech engine.
# Runs completely locally inside GitHub Actions — no API needed.
# We download the binary + English voice model on first run.
# ============================================================
def setup_piper():
    if os.path.exists(PIPER_BIN):
        print("✅ Piper already installed")
        return

    print("📥 Installing Piper TTS...")
    piper_dir = f"{WORK_DIR}/piper"
    os.makedirs(piper_dir, exist_ok=True)

    # Download Piper binary
    piper_url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
    r = requests.get(piper_url, timeout=120)
    with open(f"{WORK_DIR}/piper.tar.gz", "wb") as f:
        f.write(r.content)

    subprocess.run(["tar", "-xzf", f"{WORK_DIR}/piper.tar.gz", "-C", WORK_DIR], check=True)
    subprocess.run(["chmod", "+x", PIPER_BIN], check=True)
    print("✅ Piper binary installed")

    # Download English voice model (lessac-medium — clear, natural voice)
    model_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
    config_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"

    print("📥 Downloading voice model...")
    for url, path in [(model_url, PIPER_MODEL), (config_url, f"{PIPER_MODEL}.json")]:
        r = requests.get(url, timeout=180)
        with open(path, "wb") as f:
            f.write(r.content)

    print("✅ Piper voice model ready")

def generate_voice(text):
    print("🎙️ Generating voice with Piper TTS...")
    setup_piper()

    # Clean text for TTS — remove hashtags and emojis
    clean_text = text.replace("#", "").replace("👻", "").replace("...", ". ").strip()

    # Pipe text into Piper, output WAV file
    result = subprocess.run(
        [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", VOICE_FILE],
        input=clean_text.encode("utf-8"),
        capture_output=True,
        timeout=60
    )

    if result.returncode != 0:
        raise Exception(f"Piper failed: {result.stderr.decode()}")

    print(f"✅ Voice generated: {VOICE_FILE}")
    return VOICE_FILE

# ============================================================
# STEP 3: GENERATE HORROR IMAGE WITH POLLINATIONS.AI
# ============================================================
def generate_image(image_prompt):
    print("🖼️ Generating horror image...")

    full_prompt = (
        f"{image_prompt}, "
        "dark horror atmosphere, cinematic, eerie Filipino setting, "
        "dramatic shadows, foggy night, abandoned, photorealistic, "
        "high quality, no text, no watermark, no people"
    )

    encoded = requests.utils.quote(full_prompt)
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true&seed={seed}"

    print(f"Calling Pollinations...")
    response = requests.get(url, timeout=90)
    response.raise_for_status()

    with open(IMAGE_FILE, "wb") as f:
        f.write(response.content)

    print(f"✅ Image saved: {IMAGE_FILE}")
    return IMAGE_FILE

# ============================================================
# STEP 4: BUILD VIDEO WITH FFMPEG
# ============================================================
# FFmpeg combines image + voice into a vertical 1080x1920 Reel.
# Process:
#   1. Resize/blur image to fill 1080x1920 background
#   2. Overlay original image centered
#   3. Add dark vignette for horror mood
#   4. Add story text as burned-in subtitles
#   5. Add voice audio track
#   6. Output as MP4 (H.264) — Facebook Reels format
# ============================================================
def build_video(image_path, voice_path, story_text, title):
    print("🎬 Building video with FFmpeg...")

    # Get audio duration to set video length
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", voice_path],
        capture_output=True, text=True
    )
    probe_data = json.loads(probe.stdout)
    duration = float(probe_data["streams"][0]["duration"])
    print(f"Audio duration: {duration:.1f}s")

    # Prepare background: blur + darken the horror image to fill 1080x1920
    img = Image.open(image_path).convert("RGB")
    # Blur for background
    bg = img.resize((1080, 1080)).filter(ImageFilter.GaussianBlur(radius=15))
    # Create 1080x1920 canvas
    canvas = Image.new("RGB", (1080, 1920), (0, 0, 0))
    # Stretch blurred image to fill height
    bg_stretched = bg.resize((1080, 1920))
    # Darken it
    darkener = Image.new("RGB", (1080, 1920), (0, 0, 0))
    bg_final = Image.blend(bg_stretched, darkener, 0.5)
    canvas.paste(bg_final, (0, 0))
    # Paste original image centered (square, middle of frame)
    img_centered = img.resize((1080, 1080))
    canvas.paste(img_centered, (0, 420))  # Centered vertically

    # Add title text at top
    draw = ImageDraw.Draw(canvas)
    try:
        title_font = ImageFont.truetype("/tmp/Lora-Italic.ttf", 52)
        story_font = ImageFont.truetype("/tmp/Lora-Italic.ttf", 38)
        brand_font = ImageFont.truetype("/tmp/Lora-Italic.ttf", 28)
    except:
        title_font = ImageFont.load_default()
        story_font = ImageFont.load_default()
        brand_font = ImageFont.load_default()

    # Dark overlay on top and bottom areas
    top_overlay = Image.new("RGBA", (1080, 420), (0, 0, 0, 180))
    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba.paste(top_overlay, (0, 0), top_overlay)
    bottom_overlay = Image.new("RGBA", (1080, 420), (0, 0, 0, 200))
    canvas_rgba.paste(bottom_overlay, (0, 1500), bottom_overlay)
    canvas = canvas_rgba.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # Title
    draw.text((540, 160), title, font=title_font, fill=(255, 255, 255, 255), anchor="mm")

    # Brand
    draw.text((540, 1870), "SweetyStoryLab", font=brand_font, fill=(255, 255, 255, 180), anchor="mm")

    # Story text wrapped at bottom
    wrapped = textwrap.fill(story_text[:200] + "...", width=38)
    draw.multiline_text((540, 1600), wrapped, font=story_font,
                        fill=(255, 255, 255, 230), anchor="mm", align="center", spacing=12)

    # Save background frame
    canvas.save(BG_FILE, "JPEG", quality=95)
    print("✅ Background frame built")

    # FFmpeg: combine image + audio into MP4
    # -loop 1: use static image as video source
    # -i: input image and audio
    # -c:v libx264: H.264 video codec (Facebook compatible)
    # -tune stillimage: optimized for static image video
    # -c:a aac: AAC audio (Facebook compatible)
    # -pix_fmt yuv420p: required for Facebook compatibility
    # -shortest: end video when audio ends
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

    file_size = os.path.getsize(VIDEO_FILE)
    print(f"✅ Video built: {VIDEO_FILE} ({file_size/1024/1024:.1f}MB)")
    return VIDEO_FILE

# ============================================================
# STEP 5: UPLOAD TO FACEBOOK AS REEL
# ============================================================
# Facebook Reels upload is a 3-step process:
#
# Step A — Initialize upload session:
#   Tell Facebook the file size, get an upload URL + video_id
#
# Step B — Upload video binary:
#   Send the actual video file to the upload URL
#
# Step C — Publish as Reel:
#   Send video_id + caption to publish endpoint
# ============================================================
def upload_reel(video_path, caption):
    print("📤 Uploading Reel to Facebook...")
    file_size = os.path.getsize(video_path)

    # Step A: Initialize upload session
    print("Initializing upload session...")
    init_res = requests.post(
        f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/video_reels",
        data={
            "upload_phase": "start",
            "access_token": FB_ACCESS_TOKEN
        }
    )
    print(f"Init response: {init_res.status_code} - {init_res.text}")
    init_res.raise_for_status()
    video_id = init_res.json()["video_id"]
    print(f"✅ Upload session started. Video ID: {video_id}")

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
    print(f"Upload response: {upload_res.status_code} - {upload_res.text}")
    upload_res.raise_for_status()
    print("✅ Video uploaded!")

    time.sleep(5)

    # Step C: Publish as Reel
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
    print(f"Publish response: {pub_res.status_code} - {pub_res.text}")
    pub_res.raise_for_status()
    print(f"🎉 Reel published!")
    return video_id

# ============================================================
# STEP 6: LOG RESULT TO SQLITE
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
    print(f"📝 Logged: {status} — {title}")

# ============================================================
# MAIN
# ============================================================
def main():
    print(f"\n👻 SweetyStoryLab Horror Bot starting — {datetime.now()}")

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

        print(f"\n📖 Title: {title}")
        print(f"📝 Story: {story[:80]}...")

        # Step 2: Generate voice
        voice_path = generate_voice(voice_text)

        # Step 3: Generate image
        try:
            image_path = generate_image(image_prompt)
        except Exception as e:
            print(f"⚠️ Pollinations failed: {e} — using dark fallback")
            # Fallback: solid dark image
            img = Image.new("RGB", (1080, 1080), (5, 5, 10))
            img.save(IMAGE_FILE, "JPEG")
            image_path = IMAGE_FILE

        # Step 4: Build video
        video_path = build_video(image_path, voice_path, story, title)

        # Step 5: Upload Reel
        video_id = upload_reel(video_path, caption)

        # Step 6: Log success
        log_result(title, video_id, "success")
        print(f"\n🎉 Done! Reel posted: {title}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        log_result(
            content["title"] if content else "unknown",
            video_id,
            "failed",
            str(e)
        )
        raise

if __name__ == "__main__":
    main()

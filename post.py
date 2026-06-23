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
FB_ACCESS_TOKEN = os.environ["FB_PAGE_ACCESS_TOKEN"]
FB_PAGE_ID      = os.environ["FB_PAGE_ID"]
GROQ_API_KEY    = os.environ["GROQ_API_KEY"]

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
HORROR_THEMES = [
    "aswang sa probinsya ng Capiz",
    "white lady sa NLEX highway",
    "multo sa lumang ospital sa Maynila",
    "tikbalang sa bundok ng Rizal",
    "manananggal sa probinsya",
    "haunted dormitory sa Maynila",
    "mysterious Grab passenger late at night",
    "abandoned house sa subdivision",
    "night shift engineer who saw something",
    "missing child at the palengke",
    "hotel room that should not be entered",
    "SLEX driver with an unexplained experience",
    "woman in white in the middle of the rice field",
    "child who sees things others cannot",
    "old woman in the province with a dark secret",
]

# ============================================================
# FALLBACK
# ============================================================
FALLBACK = {
    "title": "The Third Floor",
    "caption": "He went up for ten minutes. He never came back the same. 👻",
    "hashtags": "#HorrorPH #TrueStoryPH #GabiNgMulto #PinoyHorror #SweetyStoryLab #CreepyPH",
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
    theme = random.choice(HORROR_THEMES)
    print(f"Generating story: {theme}")

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Filipino horror story writer for Facebook Reels. "
                    "Write in clear natural English. Short punchy sentences. Max 10 words per sentence. "
                    "No gore. Psychological fear only. True story style. "
                    "Always end with an unanswered mystery."
                )
            },
            {
                "role": "user",
                "content": f"""Write a 3-scene Filipino horror story about: {theme}

Each scene is ~25-30 words. Short sentences. Build fear slowly.
Scene 1 = hook and setup
Scene 2 = tension and discovery  
Scene 3 = twist or unanswered mystery

Output ONLY this exact format, nothing else:
Title: (max 5 words)
Caption: (1 punchy Facebook line, max 15 words, add 👻)
Hashtags: (#HorrorPH #PinoyHorror #TrueStoryPH #GabiNgMulto #CreepyPH #SweetyStoryLab #ParanormalPH #FilipinoPH)
Scene1Narration: (25-30 words, English, short sentences)
Scene1Image: (cinematic dark horror scene description, no people, no text, eerie setting)
Scene2Narration: (25-30 words, English, short sentences)
Scene2Image: (cinematic dark horror scene description, no people, no text)
Scene3Narration: (25-30 words, English, short sentences)
Scene3Image: (cinematic dark horror scene description, no people, no text, dramatic)"""
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
        "scenes": [{"narration": "", "image_prompt": ""} for _ in range(3)]
    }
    text = text.replace("**", "").replace("*", "")
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        if line.startswith("Title:"):
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
# STEP 2: GENERATE 3 HORROR IMAGES
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
    res = requests.get(url, timeout=90)
    res.raise_for_status()
    path = f"{WORK_DIR}/image_{index}.jpg"
    with open(path, "wb") as f:
        f.write(res.content)
    print(f"Image {index+1} saved!")
    return path

# ============================================================
# STEP 3: GENERATE VOICE + SUBTITLES WITH EDGE TTS
# ============================================================
def generate_voice(scenes):
    print("Generating voice with Edge TTS...")

    # Combine all narrations into one script
    full_narration = " ".join(s["narration"] for s in scenes)
    clean = full_narration.replace("#", "").replace("👻", "").replace("...", ". ").strip()

    result = subprocess.run(
        [
            "edge-tts",
            "--voice", "en-US-DavisNeural",
            "--rate=-15%",
            "--text", clean,
            "--write-media", VOICE_FILE,
            "--write-subtitles", VTT_FILE
        ],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise Exception(f"Edge TTS failed: {result.stderr}")

    # Convert VTT to SRT for FFmpeg
    vtt_to_srt(VTT_FILE, SRT_FILE)
    print("Voice + subtitles generated!")
    return VOICE_FILE, SRT_FILE

def vtt_to_srt(vtt_path, srt_path):
    """Convert WebVTT subtitle format to SRT for FFmpeg"""
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
# STEP 4: BUILD VIDEO — 3-IMAGE SLIDESHOW + VOICE + SUBTITLES
# ============================================================
def build_video(image_paths, voice_path, srt_path, scenes, title):
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

    # Step A: Build slideshow video from images
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-vf", "scale=1080:1920,fps=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", "30", temp_video
    ], check=True, capture_output=True)

    # Step B: Add audio + burned subtitles
    # Subtitle style: large white text, centered, horror font feel
    subtitle_style = (
        "FontName=Arial,"
        "FontSize=16,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&H80000000,"
        "Bold=1,"
        "Outline=3,"
        "Shadow=2,"
        "Alignment=2,"      # Bottom center
        "MarginV=120"       # Above brand name
    )

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", temp_video,
        "-i", voice_path,
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
        font_title = ImageFont.truetype("/tmp/Lora-Italic.ttf", 68)
        font_brand = ImageFont.truetype("/tmp/Lora-Italic.ttf", 30)
        font_scene = ImageFont.truetype("/tmp/Lora-Italic.ttf", 26)
    except:
        font_title = font_brand = font_scene = ImageFont.load_default()

    # Title
    draw.text((542, 152), title, font=font_title, fill=(0,0,0,200), anchor="mm")
    draw.text((540, 150), title, font=font_title, fill=(255,255,255,255), anchor="mm")

    # Decorative line
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

# ============================================================
# STEP 5: UPLOAD TO FACEBOOK AS REEL
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
        video_path = build_video(image_paths, voice_path, srt_path, scenes, title)

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

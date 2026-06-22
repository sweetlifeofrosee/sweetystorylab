# ============================================================
# post.py — Daily Facebook Horror Auto-Poster for SweetyStoryLab
# ============================================================
# Same structure as @thesweetyjournal Instagram bot.
# Runs every day at 7PM PHT via GitHub Actions.
# It does 5 things in order:
#   1. Generates a Taglish horror story using Groq AI
#   2. Splits story into 5 carousel slides
#   3. Generates a creepy image per slide using Pollinations.ai
#   4. Adds story text on top of each image using Pillow
#   5. Posts to Facebook Page as a carousel via Meta Graph API

import os
import random
import requests
import time
import base64
import io
import json
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# SECRETS — loaded from GitHub Actions environment variables
# Set them in: repo → Settings → Secrets → Actions
# ============================================================
FB_ACCESS_TOKEN = os.environ["FB_PAGE_ACCESS_TOKEN"]       # Facebook Page Access Token
FB_PAGE_ID = os.environ["FB_PAGE_ID"]                      # SweetyStoryLab Page ID
GROQ_API_KEY = os.environ["GROQ_API_KEY"]                  # Groq API — generates horror stories
IMGBB_KEY = os.environ["IMGBB_API_KEY"]                    # ImgBB — hosts images for Facebook

# ============================================================
# FALLBACK HORROR CONTENT
# ============================================================
# If Groq fails, bot picks from this list so it never skips a day.
# Each entry has 5 slides for the carousel.
# ============================================================
FALLBACK_CONTENT = [
    {
        "title": "Ang Babae sa Ikatlong Palapag",
        "caption": "Hindi kami naniwala sa mga kwento ng kapitbahay... hanggang sa isang gabi.",
        "slides": [
            "Lumipat kami sa bagong apartment noong Hunyo. Sabi ng kapitbahay — huwag daw kaming mag-alala sa ingay sa itaas. Walang nakatira sa ikatlong palapag.",
            "Unang linggo — tahimik. Ikalawang linggo — nagsimula kaming marinig ang mga yapak. Tuwing hatinggabi. Pataas. Pababa. Pataas. Pababa.",
            "Isinumbong namin sa landlord. Ngumiti lang siya. 'Imahinasyon ninyo iyon,' sabi niya. Pero naging mas malakas ang ingay.",
            "Isang gabi, nagdesisyon si Mark na umakyat. Nagdala siya ng flashlight. Sampung minuto lang daw siya. Hindi na siya bumalik ng sampung minuto.",
            "Nandoon pa rin siya sa ikatlong palapag. Nakaupo sa sulok. Nakatingin sa dingding. Hindi sumasagot. Hindi gumagalaw. Hanggang ngayon — hindi namin alam kung sino ang nakausap niya doon."
        ],
        "hashtags": "#HorrorPH #TrueStoryPH #GabiNgMulto #PinoyHorror #ParanormalPH #CreepyPH #SweetyStoryLab"
    },
    {
        "title": "Ang Pasahero",
        "caption": "Nagod-drive ako ng Grab noong madaling araw... hindi ko dapat tinanggap ang ride na iyon.",
        "slides": [
            "Driver ako ng Grab. Tanggap ako ng booking — 3:17AM. Malayo ang pickup, pero malaki ang bayad. Tinanggap ko.",
            "Dumating ako sa address. Isang babae sa puting damit. Tahimik. Umupo sa likod. Hindi nagbigay ng pangalan.",
            "Sampung minuto ng viyahe — walang nagsalita. Sa rearview mirror, nakita ko siyang nakatingin sa labas ng bintana. Hindi kumikibo.",
            "Biglang nagsalita siya. 'Dito na lang.' Sa gitna ng daan. Walang bahay. Walang ilaw. Diko alam kung bakit — sumunod ako.",
            "Pagbaba niya, tiningnan ko ang aking app. Cancelled na ang booking. Ni-reload ko ang page — walang record ng ride. Walang pasahero. Walang bayad. Walang trace na may sumakay sa kotse ko."
        ],
        "hashtags": "#HorrorPH #GrabHorror #TrueStoryPH #PinoyHorror #CreepyPH #GabiNgMulto #SweetyStoryLab"
    },
    {
        "title": "Kwarto 404",
        "caption": "Nag-check in kami sa hotel na may kakaibang kwarto...",
        "slides": [
            "Pumunta kami sa Baguio para sa team building. Nag-book kami ng hotel. 12 kami — 6 kwarto. Pero may nakapaskil sa elevator: 'Room 404 — Under Maintenance.'",
            "Naging curious si Liza. Tuwing dumadaan kami sa corridor, lagi siyang tumitigil sa harap ng 404. 'May naririnig ako sa loob,' sabi niya. Pinagtawanan namin siya.",
            "Ikatlong gabi — nagising kami sa sigaw ni Liza. Natagpuan namin siya sa corridor, nakatayo sa harap ng 404. Nakabukas ang pinto.",
            "Wala kaming nakita sa loob. Kulay puti ang lahat. Malinis. Pero sa gitna ng kwarto — isang upuan. At sa upuan — isang lumang larawan ng aming grupo. Mula pa noong hindi pa kami nagmimeet.",
            "Umalis kami ng maaga kinabukasan. Hindi na kami nagbalik sa hotel na iyon. Hindi rin kami nagtatanong kung paano napunta ang larawang iyon doon."
        ],
        "hashtags": "#HorrorPH #BaguioHorror #TrueStoryPH #PinoyHorror #CreepyPH #ParanormalPH #SweetyStoryLab"
    }
]

# ============================================================
# HORROR THEMES — Groq picks from these for variety
# ============================================================
HORROR_THEMES = [
    "aswang sa probinsya ng Capiz",
    "white lady sa NLEX highway",
    "multo sa lumang ospital sa Maynila",
    "tikbalang sa bundok ng Rizal",
    "manananggal sa probinsya",
    "haunted dormitory sa Maynila",
    "mysterious passenger sa Grab",
    "abandoned house sa subdivision",
    "engineer na nakakita ng multo sa gabi",
    "nawawalang bata sa palengke",
    "kwarto sa hotel na hindi dapat puntahan",
    "driver na may naranasang hindi maipaliwanag sa SLEX",
]

# ============================================================
# STEP 1: GENERATE HORROR STORY WITH GROQ
# ============================================================
def generate_with_groq():
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
                    "You are a Filipino horror story writer for a Facebook page called SweetyStoryLab. "
                    "You write in Taglish — natural Filipino conversational tone mixed with English. "
                    "Your stories are suspenseful, cinematic, and culturally Filipino. "
                    "No gore. Focus on fear, mystery, and psychological tension. "
                    "Every story must have a twist or unanswered mystery at the end."
                )
            },
            {
                "role": "user",
                "content": f"""Write a Filipino horror story about: {theme}

REQUIREMENTS:
- Written in Taglish (natural mix of Filipino and English)
- Hook in the first sentence — must grab attention immediately
- Build tension slowly — each slide gets scarier
- Ending must be a twist or unanswered mystery
- No gore or violence — psychological fear only
- Feel like a true story being shared by a friend
- Each slide is 2-4 sentences only

Output Format (use exactly these labels, nothing else):
Title: (short, mysterious Filipino title)
Caption: (1 line Facebook caption in English — curiosity-driven, emotional)
Slide1: (hook — sets the scene, 2-3 sentences)
Slide2: (build up tension, 2-3 sentences)
Slide3: (eerie discovery or escalation, 2-3 sentences)
Slide4: (climax — the scariest moment, 2-3 sentences)
Slide5: (twist ending or unanswered mystery, 2-3 sentences)
Hashtags: (8-10 relevant hashtags including #HorrorPH #PinoyHorror #SweetyStoryLab)
Image Prompt: (one cinematic dark horror scene description for AI image generation — no text, no people's faces, dark atmosphere, eerie lighting)"""
            }
        ],
        "temperature": 0.95,
        "max_tokens": 800
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"].strip()
    print(f"Groq generated:\n{text}")
    return text

# ============================================================
# STEP 1b: PARSE GROQ OUTPUT
# ============================================================
def parse_output(text):
    result = {
        "title": "",
        "caption": "",
        "slides": ["", "", "", "", ""],
        "hashtags": "#HorrorPH #PinoyHorror #SweetyStoryLab",
        "image_prompt": "dark abandoned Filipino province house at night, eerie fog, no people, cinematic horror"
    }

    text = text.replace("**", "").replace("*", "")
    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("Title:"):
            result["title"] = line.replace("Title:", "").strip().strip('"')
        elif line.startswith("Caption:"):
            result["caption"] = line.replace("Caption:", "").strip().strip('"')
        elif line.startswith("Slide1:"):
            result["slides"][0] = line.replace("Slide1:", "").strip()
        elif line.startswith("Slide2:"):
            result["slides"][1] = line.replace("Slide2:", "").strip()
        elif line.startswith("Slide3:"):
            result["slides"][2] = line.replace("Slide3:", "").strip()
        elif line.startswith("Slide4:"):
            result["slides"][3] = line.replace("Slide4:", "").strip()
        elif line.startswith("Slide5:"):
            result["slides"][4] = line.replace("Slide5:", "").strip()
        elif line.startswith("Hashtags:"):
            result["hashtags"] = line.replace("Hashtags:", "").strip()
        elif line.startswith("Image Prompt:"):
            result["image_prompt"] = line.replace("Image Prompt:", "").strip()

    return result

# ============================================================
# STEP 1c: GET CONTENT (with fallback)
# ============================================================
def get_content():
    try:
        text = generate_with_groq()
        result = parse_output(text)
        if result["title"] and result["slides"][0]:
            print(f"✅ Horror story generated: {result['title']}")
            return result
    except Exception as e:
        print(f"⚠️ Groq failed: {e}")

    print("⚠️ Using fallback content...")
    return random.choice(FALLBACK_CONTENT)

# ============================================================
# STEP 2: GENERATE HORROR IMAGE WITH POLLINATIONS.AI
# ============================================================
# Pollinations.ai is completely free — no API key needed.
# Just call a URL with the prompt and it returns an image.
# Perfect for GitHub Actions — zero cost, zero setup.
# ============================================================
def generate_horror_image(image_prompt, slide_number):
    print(f"Generating horror image for slide {slide_number}...")

    # Add horror-specific boosters to the prompt
    full_prompt = (
        f"{image_prompt}, "
        f"dark horror atmosphere, cinematic, eerie Filipino setting, "
        f"dramatic shadows, foggy, abandoned, no text, no watermark, "
        f"photorealistic, high quality, 1080x1080"
    )

    # URL encode the prompt
    encoded_prompt = requests.utils.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1080&nologo=true&seed={random.randint(1,9999)}"

    print(f"Calling Pollinations: {url[:100]}...")
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    if response.headers.get("content-type", "").startswith("image"):
        print(f"✅ Horror image generated for slide {slide_number}!")
        return response.content

    raise Exception(f"Pollinations returned unexpected response")

# ============================================================
# STEP 3: ADD TEXT OVERLAY WITH PILLOW
# ============================================================
# Same approach as your Instagram bot —
# adds story text on top of the horror image.
# Slide 5 (twist ending) gets a black background for drama.
# ============================================================
def add_text_overlay(image_bytes, text, slide_number, title, is_last_slide=False):
    print(f"Adding text overlay for slide {slide_number}...")

    if is_last_slide:
        # Black slide for the twist ending — maximum drama
        img = Image.new("RGBA", (1080, 1080), (0, 0, 0, 255))
    else:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        img = img.resize((1080, 1080))
        # Darker overlay for horror — more than the Instagram bot
        darkener = Image.new("RGBA", img.size, (0, 0, 0, 140))
        img = Image.alpha_composite(img, darkener)

    font_path = "/tmp/Lora-Italic.ttf"

    # Dynamic font size based on text length
    if len(text) < 60:
        font_size = 52
    elif len(text) < 100:
        font_size = 44
    elif len(text) < 150:
        font_size = 38
    else:
        font_size = 34

    story_font = ImageFont.truetype(font_path, font_size)
    title_font = ImageFont.truetype(font_path, 24)
    brand_font = ImageFont.truetype(font_path, 17)
    slide_font = ImageFont.truetype(font_path, 20)

    draw = ImageDraw.Draw(img)
    center_x = 540
    center_y = 490

    # Word wrap for story text
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        bbox = draw.textbbox((0, 0), ' '.join(current_line), font=story_font)
        if bbox[2] - bbox[0] > 860:
            lines.append(' '.join(current_line[:-1]))
            current_line = [word]
    lines.append(' '.join(current_line))

    line_height = int(font_size * 1.45)
    total_height = len(lines) * line_height
    start_y = center_y - total_height // 2

    # Decorative line above text
    draw.rectangle([center_x - 30, start_y - 32, center_x + 30, start_y - 30], fill=(255, 255, 255, 180))

    # Draw story text with shadow
    for i, line in enumerate(lines):
        y = start_y + i * line_height
        bbox = draw.textbbox((0, 0), line, font=story_font)
        text_width = bbox[2] - bbox[0]
        x = center_x - text_width // 2
        draw.text((x + 2, y + 2), line, font=story_font, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=story_font, fill=(255, 255, 255, 255))

    end_y = start_y + len(lines) * line_height

    # Decorative line below text
    draw.rectangle([center_x - 30, end_y + 12, center_x + 30, end_y + 14], fill=(255, 255, 255, 180))

    # Story title at top
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text((center_x - title_width // 2 + 1, 41), title, font=title_font, fill=(0, 0, 0, 160))
    draw.text((center_x - title_width // 2, 40), title, font=title_font, fill=(255, 255, 255, 200))

    # Slide number indicator (e.g. "1 / 5")
    slide_text = f"{slide_number} / 5"
    slide_bbox = draw.textbbox((0, 0), slide_text, font=slide_font)
    slide_width = slide_bbox[2] - slide_bbox[0]
    draw.text((center_x - slide_width // 2, 75), slide_text, font=slide_font, fill=(255, 255, 255, 130))

    # Brand name at bottom
    brand_text = "SweetyStoryLab"
    brand_bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
    brand_width = brand_bbox[2] - brand_bbox[0]
    draw.text((center_x - brand_width // 2 + 1, 1046), brand_text, font=brand_font, fill=(0, 0, 0, 120))
    draw.text((center_x - brand_width // 2, 1045), brand_text, font=brand_font, fill=(255, 255, 255, 160))

    output = io.BytesIO()
    img = img.convert("RGB")
    img.save(output, format="JPEG", quality=95)
    print(f"✅ Overlay added for slide {slide_number}!")
    return output.getvalue()

# ============================================================
# STEP 4: UPLOAD IMAGE TO IMGBB
# ============================================================
def upload_image(image_bytes, slide_num):
    print(f"Uploading slide {slide_num} to ImgBB...")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    res = requests.post("https://api.imgbb.com/1/upload", data={
        "key": IMGBB_KEY,
        "image": b64,
    })
    res.raise_for_status()
    url = res.json()["data"]["url"]
    print(f"✅ Slide {slide_num} uploaded: {url}")
    return url

# ============================================================
# STEP 5: POST TO FACEBOOK AS CAROUSEL
# ============================================================
# Facebook carousel posting is a 3-step process:
#
# Step A — Upload each image as an unpublished photo:
#   Send each image URL to the /photos endpoint with
#   published=false. Get back a media_fbid for each.
#
# Step B — Create a multi-photo post:
#   Send all media_fbids together to the /feed endpoint
#   with attached_media array. This creates the carousel.
#
# Step C — Post goes live on SweetyStoryLab page.
# ============================================================
def post_to_facebook(image_urls, caption):
    print("Posting carousel to Facebook...")
    media_ids = []

    # Step A: Upload each slide as unpublished photo
    for i, img_url in enumerate(image_urls):
        time.sleep(3)
        print(f"Uploading photo {i+1} to Facebook...")
        res = requests.post(
            f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/photos",
            data={
                "url": img_url,
                "published": "false",
                "access_token": FB_ACCESS_TOKEN
            }
        )
        print(f"Photo {i+1} response: {res.status_code} - {res.text}")
        res.raise_for_status()
        media_id = res.json().get("id")
        media_ids.append({"media_fbid": media_id})
        print(f"✅ Photo {i+1} staged: {media_id}")

    time.sleep(5)

    # Step B: Publish all photos as a carousel post
    print("Publishing carousel post...")
    attached_media = json.dumps(media_ids)
    pub = requests.post(
        f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/feed",
        data={
            "message": caption,
            "attached_media": attached_media,
            "access_token": FB_ACCESS_TOKEN
        }
    )
    print(f"Publish response: {pub.status_code} - {pub.text}")
    pub.raise_for_status()
    print(f"🎉 Horror carousel posted! ID: {pub.json().get('id')}")

# ============================================================
# MAIN — Full pipeline
# ============================================================
def main():
    # Step 1: Generate horror story
    content = get_content()
    title = content["title"]
    slides = content["slides"]
    hashtags = content["hashtags"]
    image_prompt = content.get("image_prompt", "dark eerie Filipino province night fog abandoned house")

    print(f"\n👻 Story: {title}")
    print(f"📝 Slides: {len(slides)}")

    # Build Facebook caption
    caption = (
        f"{content['caption']}\n\n"
        f"Swipe to read the full story...\n\n"
        f"{hashtags}"
    )

    # Step 2-4: Generate image, add overlay, upload — for each slide
    image_urls = []
    for i, slide_text in enumerate(slides):
        slide_number = i + 1
        is_last = (i == len(slides) - 1)

        try:
            # Generate horror image (black slide for last)
            if is_last:
                image_bytes = b""  # Black slide — no image needed
            else:
                image_bytes = generate_horror_image(image_prompt, slide_number)
        except Exception as e:
            print(f"⚠️ Image generation failed for slide {slide_number}: {e}")
            # Fallback: dark gradient image using Pillow
            img = Image.new("RGBA", (1080, 1080), (10, 10, 15, 255))
            output = io.BytesIO()
            img.convert("RGB").save(output, format="JPEG", quality=95)
            image_bytes = output.getvalue()

        # Add text overlay
        final_image = add_text_overlay(image_bytes, slide_text, slide_number, title, is_last)

        # Upload to ImgBB
        url = upload_image(final_image, slide_number)
        image_urls.append(url)

        time.sleep(2)  # Be gentle with APIs

    # Step 5: Post to Facebook as carousel
    post_to_facebook(image_urls, caption)

if __name__ == "__main__":
    main()

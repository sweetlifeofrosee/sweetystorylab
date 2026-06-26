# SweetyStoryLab — Horror Reels Bot

Fully automated horror Reels for **Facebook** and **TikTok** *(TikTok pending API approval)*.
Posts 3x daily at 8AM / 2PM / 8PM PHT. Zero manual work after setup.

---

## What it produces

- 60–90 second vertical video (1080×1920)
- Horror story narrated by AI voice (ElevenLabs or Edge TTS)
- Creepy AI-generated horror image background (3 scenes)
- Smooth crossfade transitions between scenes
- Burned-in synced subtitles
- AI-generated suspense background music (MusicGen)
- Engagement question slide at the end
- Auto-posted as a Reel to **SweetyStoryLab**

---

## Stack (100% free)

| Tool | Purpose |
|------|---------|
| GitHub Actions | Free scheduler + runner |
| Groq (llama-3.1-8b) | Horror story + music prompt generation |
| Edge TTS / ElevenLabs | AI voice narration + subtitles |
| Pollinations.ai | Free AI image generation (3 per video) |
| MusicGen (Hugging Face) | AI-generated suspense background music |
| FFmpeg | Video assembly (built into Actions) |
| Facebook Graph API | Reel upload + publish |
| TikTok Content Posting API | Reel upload + publish *(pending approval)* |
| SQLite | Post logging |

---

## GitHub Secrets Required

Repo → Settings → Secrets and variables → Actions

### Facebook
| Secret | Where to get |
|--------|-------------|
| `FB_PAGE_ACCESS_TOKEN` | Meta Graph API → me/accounts → Sweety Story Lab token |
| `FB_PAGE_ID` | `1175342552326672` |
| `GROQ_API_KEY` | console.groq.com |

### TikTok *(add after API approval)*
| Secret | Where to get |
|--------|-------------|
| `TIKTOK_ACCESS_TOKEN` | TikTok Developer Portal → OAuth token for SweetyStoryLab account |
| `TIKTOK_OPEN_ID` | Returned during OAuth authorization |

### Optional
| Secret | Where to get |
|--------|-------------|
| `ELEVENLABS_API_KEY` | elevenlabs.io → Profile → API Keys (free tier: 10k chars/month) |

---

## Platform Status

| Platform | Status | API |
|----------|--------|-----|
| Facebook | ✅ Live | Graph API v21.0 |
| TikTok | ⏳ Pending API approval | Content Posting API |

---

## TikTok Setup *(after approval)*

1. Add `TIKTOK_ACCESS_TOKEN` and `TIKTOK_OPEN_ID` to GitHub Secrets
2. The bot will auto-post to both Facebook and TikTok on every run

### TikTok App Details
- **App:** SweetyStoryLab
- **Scopes:** `user.info.basic`, `video.publish`, `video.upload`
- **Direct Post:** Enabled
- **Redirect URI:** `https://sweetlifeofrosee.github.io/sweetystorylab/callback`

---

## Pipeline (per post)

```
Groq → horror story (3 scenes + image prompts + music prompt)
  ↓
Pollinations → 3 horror images
  ↓
ElevenLabs / Edge TTS → voice narration + subtitles
  ↓
MusicGen → AI suspense background music
  ↓
FFmpeg → 3-scene slideshow + crossfades + subtitles + music → MP4
  ↓
Facebook Graph API → upload + publish Reel
TikTok Content API → upload + publish Reel (pending)
  ↓
SQLite → log result
```

---

## To test manually

Actions tab → **Horror Reels Bot** → Run workflow

---

## Video specs

- Resolution: 1080×1920 (vertical Reels format)
- Codec: H.264 + AAC (Facebook & TikTok compatible)
- Duration: ~60–90 seconds (voice length) + 4s question slide
- Size: ~5–15MB per video
- Transitions: smooth crossfade between 3 scenes

---

## No longer needed vs carousel version

- ❌ IMGBB_API_KEY — video uploaded directly
- ❌ PEXELS_API_KEY — Pollinations.ai is free
- ❌ CLOUDFLARE tokens — not needed

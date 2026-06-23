# SweetyStoryLab — Horror Reels Bot

Fully automated Filipino horror Reels for Facebook.
Posts 3x daily at 8AM / 2PM / 8PM PHT. Zero manual work after setup.

## What it produces
- 60-90 second vertical video (1080x1920)
- Taglish horror story narrated by AI voice
- Creepy AI-generated horror image background
- Auto-posted as Facebook Reel to SweetyStoryLab

## Stack (100% free)
| Tool | Purpose |
|------|---------|
| GitHub Actions | Free scheduler + runner |
| Groq (llama-3.1-8b) | Horror story generation |
| Piper TTS | Offline AI voice narration |
| Pollinations.ai | Free AI image generation |
| FFmpeg | Video assembly (built into Actions) |
| Facebook Graph API | Reel upload + publish |
| SQLite | Post logging |

## GitHub Secrets Required
Repo → Settings → Secrets and variables → Actions

| Secret | Where to get |
|--------|-------------|
| `FB_PAGE_ACCESS_TOKEN` | Meta Graph API → me/accounts → Sweety Story Lab token |
| `FB_PAGE_ID` | `1175342552326672` |
| `GROQ_API_KEY` | console.groq.com (same as instagbot) |

## No longer needed vs carousel version
- ❌ IMGBB_API_KEY (not needed — video uploaded directly)
- ❌ PEXELS_API_KEY (not needed — Pollinations is free)
- ❌ CLOUDFLARE tokens (not needed)

## To test manually
Actions tab → Horror Reels Bot → Run workflow

## Video specs
- Resolution: 1080x1920 (vertical Reels format)
- Codec: H.264 + AAC (Facebook compatible)
- Duration: matches voice length (~60-90 seconds)
- Size: ~5-15MB per video

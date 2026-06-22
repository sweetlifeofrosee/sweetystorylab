# SweetyStoryLab Horror Bot

Daily Filipino horror story auto-poster for Facebook Page.
Same structure as @thesweetyjournal Instagram bot.

## What it does
- Runs every night at 7PM PHT automatically
- Generates a Taglish horror story using Groq AI
- Creates 5 creepy AI images using Pollinations.ai (free, no API key)
- Adds story text overlay on each image using Pillow
- Posts as a 5-slide carousel to SweetyStoryLab Facebook Page

## GitHub Secrets required
Go to repo → Settings → Secrets and variables → Actions → New repository secret

| Secret | Where to get it |
|--------|----------------|
| `FB_PAGE_ACCESS_TOKEN` | Meta Graph API Explorer → SweetyStoryLab token |
| `FB_PAGE_ID` | SweetyStoryLab page → About → Page ID |
| `GROQ_API_KEY` | console.groq.com (same as instagbot) |
| `IMGBB_API_KEY` | api.imgbb.com (same as instagbot) |

## To test manually
Go to Actions tab → Daily Horror Post → Run workflow

## Stack
- Groq (llama-3.1-8b-instant) — story generation
- Pollinations.ai — free AI image generation (no key needed)
- Pillow — text overlay
- ImgBB — image hosting
- Facebook Graph API v21.0 — carousel posting
- GitHub Actions — free daily scheduler

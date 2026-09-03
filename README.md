# HeroFX IB Agent

Automated social media agent for HeroFX Introducing Brokers.

## What It Does

1. **Checks @herofx_official Instagram** every 24 hours for new posts
2. **Analyzes posts with AI** (Gemini) — understands images, videos, and captions
3. **Generates native captions** in Kurdish Sorani and Modern Standard Arabic
4. **Sends you a preview** via Telegram DM with Approve/Reject/Edit buttons
5. **Posts to your channels** at 3:00 PM Slemani time after your approval
6. **On-demand mode**: send any Instagram URL for immediate processing

## Channels

- **PalawanFX** (@PalawanFX) — Kurdish Sorani audience
- **BatalFX** (@BatalFX) — Arabic audience

## Your IB Link

Every post includes your HeroFX IB link: `https://herofx.co/?partner_code=8591993`

## Quick Setup

### Prerequisites

- Python 3.11+
- Telegram Bot Tokens (from @BotFather)
- Gemini API key (free from https://aistudio.google.com/apikey)

### Installation

1. **Run setup.bat** (double-click it):
   ```
   setup.bat
   ```

2. **Set Gemini API key**:
   ```
   set GEMINI_API_KEY=your_key_here
   ```

3. **Update config.json** with your Telegram bot tokens

4. **Run the agent**:
   ```
   python main.py
   ```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Show bot menu |
| `/status` | Check bot status |
| `/post <url>` | Preview any Instagram post |
| `/check` | Manually check HeroFX Instagram |

## How Approval Works

```
Instagram Post Found
        ↓
AI Analyzes (image + caption)
        ↓
Sends You Preview (Kurdish + Arabic)
        ↓
You Approve / Edit / Reject
        ↓
Posts at 3:00 PM Slemani time
```

## Automation Roadmap

| Phase | Timeline | Behavior |
|-------|----------|----------|
| **Phase 1** | Months 1-3 | Every post needs your explicit approval. Free (Gemini free tier). |
| **Phase 2** | Month 4 | Auto-post with notification if approval pattern is consistent. |
| **Phase 3** | Month 5+ | Full auto for routine content. Flagged only for sensitive topics. |

## Tech Stack

- **Python 3.11** on your local Windows machine
- **Playwright** for Instagram monitoring
- **Google Gemini 1.5 Flash** for AI analysis (free tier)
- **python-telegram-bot** for Telegram integration
- **APScheduler** for 24h check + 3:00 PM posting schedule

## Cost

**$0 for first 3 months** — Gemini free tier handles the workload.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point with scheduler |
| `config.py` | Configuration management |
| `instagram_monitor.py` | Instagram checking and media download |
| `ai_analyzer.py` | Gemini AI analysis and caption generation |
| `telegram_bot.py` | Telegram bot with approval workflow |
| `config.json` | All settings and tokens |
| `requirements.txt` | Python dependencies |
| `setup.bat` | Windows setup script |

## After 3 Months

When you're ready for 24/7 uptime (even when PC is off), we can deploy to Railway for ~$5/month. Until then, this runs locally on your machine.

"""
HeroFX IB Agent - Main Entry Point
Runs the bot with 24h Instagram check scheduler
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import Config, PostedDB
from ai_analyzer import AIAnalyzer
from instagram_monitor import InstagramMonitor
from telegram_bot import TelegramBot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


class HeroFXAgent:
    def __init__(self):
        self.config = Config()
        self.posted_db = PostedDB()
        
        # Initialize AI
        gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_api_key:
            logger.warning("GEMINI_API_KEY not set! AI analysis will not work.")
            logger.warning("Set it with: set GEMINI_API_KEY=your_key (Windows) or export GEMINI_API_KEY=your_key (Linux/Mac)")
        
        self.ai = AIAnalyzer(
            api_key=gemini_api_key,
            model=self.config.ai_model,
            max_tokens=self.config.ai_max_tokens,
            temperature=self.config.ai_temperature
        )
        
        # Initialize Instagram monitor
        self.monitor = InstagramMonitor(self.config.instagram_username)
        
        # Initialize Telegram bot
        self.bot = TelegramBot(self.config, self.posted_db, self.ai)
        
        # Initialize scheduler
        self.scheduler = AsyncIOScheduler(timezone=self.config.timezone)
    
    async def start(self):
        """Start the agent."""
        logger.info("Starting HeroFX IB Agent...")
        
        # Setup scheduled jobs
        self._setup_scheduler()
        self.scheduler.start()
        
        # Start the bot (this blocks)
        await self.bot.start()
    
    def _setup_scheduler(self):
        """Setup scheduled jobs."""
        # 24h check for new posts
        self.scheduler.add_job(
            self._scheduled_check,
            trigger=CronTrigger(hour="9", minute="0"),  # 9:00 AM daily
            id="instagram_check",
            name="Check HeroFX Instagram for new posts"
        )
        
        # Post pending posts at 3:00 PM Slemani time
        self.scheduler.add_job(
            self._scheduled_post,
            trigger=CronTrigger(hour="15", minute="0"),  # 3:00 PM daily
            id="post_to_channels",
            name="Post approved content to Telegram channels"
        )
        
        logger.info("Scheduler setup complete:")
        logger.info("  - Instagram check: 9:00 AM daily")
        logger.info("  - Post to channels: 3:00 PM daily (Slemani time)")
    
    async def _scheduled_check(self):
        """Scheduled job: check Instagram for new posts."""
        logger.info("Running scheduled Instagram check...")
        
        try:
            # Get last posted shortcode
            last_shortcode = None
            if self.posted_db.data['posted_ids']:
                last_shortcode = self.posted_db.data['posted_ids'][-1]
            
            # Check for new posts
            posts = await self.monitor.check_new_posts(last_shortcode)
            
            if not posts:
                logger.info("No new posts found.")
                return
            
            logger.info(f"Found {len(posts)} new post(s). Processing...")
            
            for post in posts:
                await self._process_post_from_scheduler(post)
                
        except Exception as e:
            logger.error(f"Scheduled check failed: {e}")
    
    async def _process_post_from_scheduler(self, post):
        """Process a post detected by the scheduler."""
        try:
            # Download media
            media_paths = await self.monitor.download_media(post)
            if not media_paths:
                logger.error(f"Failed to download media for {post.shortcode}")
                return
            
            # Analyze with AI
            ai_result = self.ai.analyze_post(media_paths, post.caption)
            
            if not ai_result:
                logger.error(f"AI analysis failed for {post.shortcode}")
                return
            
            # Build preview
            ckb_caption = ai_result['ckb']
            ar_caption = ai_result['ar']
            
            ib_ckb = self.config.get_ib_footer(post.caption, "ckb")
            ib_ar = self.config.get_ib_footer(post.caption, "ar")
            
            preview_ckb = f"{ckb_caption}{ib_ckb}" if ckb_caption else ""
            preview_ar = f"{ar_caption}{ib_ar}" if ar_caption else ""
            
            # Store pending
            pending_id = f"post_{post.shortcode}"
            self.posted_db.add_pending(pending_id, {
                "shortcode": post.shortcode,
                "url": post.url,
                "original_caption": post.caption,
                "translated_ckb": ckb_caption,
                "translated_ar": ar_caption,
                "preview_ckb": preview_ckb,
                "preview_ar": preview_ar,
                "image_paths": [str(p) for p in media_paths],
                "has_video": "video" in post.media_types,
                "detected_at": datetime.now().isoformat()
            })
            
            # Send preview to admin
            await self.bot.send_preview_from_scheduler({
                "shortcode": pending_id,
                "url": post.url,
                "preview_ckb": preview_ckb,
                "preview_ar": preview_ar
            }, media_paths)
            
        except Exception as e:
            logger.error(f"Error processing post {post.shortcode}: {e}")
    
    async def _scheduled_post(self):
        """Scheduled job: post approved content at 3:00 PM."""
        logger.info("Running scheduled post job...")
        
        try:
            # Get all pending posts that were approved but not yet posted
            # (This is handled by the approve button in the bot)
            # This job is a fallback to post anything that's been approved
            # but not yet sent due to timing issues
            
            pending = self.posted_db.data.get("pending", {})
            if not pending:
                logger.info("No pending posts to send.")
                return
            
            logger.info(f"Found {len(pending)} pending post(s).")
            
            # Send reminder to admin about pending posts
            if self.bot.app:
                await self.bot.app.bot.send_message(
                    chat_id=self.config.admin_id,
                    text=f"⏰ Reminder: You have {len(pending)} pending post(s) waiting for approval.\n"
                         f"Use /post <url> or check your pending posts."
                )
                
        except Exception as e:
            logger.error(f"Scheduled post job failed: {e}")


def main():
    """Main entry point."""
    agent = HeroFXAgent()
    
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user.")
    except Exception as e:
        logger.error(f"Agent crashed: {e}", exc_info=True)


if __name__ == "__main__":
    main()

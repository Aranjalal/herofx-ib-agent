#!/usr/bin/env python3
"""
HeroFX IB Agent - Main Entry Point
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

from config import Config, PostedDB
from ai_analyzer import AIAnalyzer
from instagram_monitor import InstagramMonitor
from telegram_bot import TelegramBot

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
        
        gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_api_key:
            logger.warning("GEMINI_API_KEY not set!")
        
        self.ai = AIAnalyzer(
            api_key=gemini_api_key,
            model=self.config.ai_model,
            max_tokens=self.config.ai_max_tokens,
            temperature=self.config.ai_temperature
        )
        
        self.monitor = InstagramMonitor(self.config.instagram_username)
        self.bot = TelegramBot(self.config, self.posted_db, self.ai)
    
    async def start(self):
        """Start the agent."""
        logger.info("Starting HeroFX IB Agent...")
        
        # Start bot (this blocks)
        await self.bot.start()
    
    async def scheduled_check(self):
        """Check Instagram for new posts."""
        logger.info("Running scheduled Instagram check...")
        
        try:
            last_shortcode = None
            if self.posted_db.data['posted_ids']:
                last_shortcode = self.posted_db.data['posted_ids'][-1]
            
            posts = await self.monitor.check_new_posts(last_shortcode)
            
            if not posts:
                logger.info("No new posts found.")
                return
            
            logger.info(f"Found {len(posts)} new post(s). Processing...")
            
            for post in posts:
                await self.bot._process_post(post, None, None)
                
        except Exception as e:
            logger.error(f"Scheduled check failed: {e}")
    
    async def scheduled_post(self):
        """Post auto-detected pending posts at 3:00 PM."""
        logger.info("Running scheduled post job...")
        
        try:
            pending = self.posted_db.data.get("pending", {})
            if not pending:
                logger.info("No pending posts to send.")
                return
            
            # Only post auto-detected posts (those with detected_at)
            auto_detected = {
                k: v for k, v in pending.items() 
                if v.get("detected_at") is not None
            }
            
            if not auto_detected:
                logger.info("No auto-detected pending posts.")
                return
            
            logger.info(f"Posting {len(auto_detected)} auto-detected post(s)...")
            
            for pending_id, post_data in auto_detected.items():
                # Post to both channels
                for channel_key in ["palawanfx", "batalfx"]:
                    channel_config = self.config.get_channel(channel_key)
                    target_lang = channel_config["language"]
                    caption = post_data["preview_ckb"] if target_lang == "ckb" else post_data["preview_ar"]
                    
                    if not caption:
                        caption = post_data["original_caption"] or ""
                    
                    from pathlib import Path
                    media_paths = [Path(p) for p in post_data["image_paths"] if Path(p).exists()]
                    
                    success = await self.bot._post_to_telegram(
                        channel_config["bot_token"],
                        channel_config["channel_id"],
                        caption,
                        media_paths
                    )
                    
                    if success:
                        logger.info(f"Posted {pending_id} to {channel_key}")
                    else:
                        logger.error(f"Failed to post {pending_id} to {channel_key}")
                    
                    await asyncio.sleep(self.config.delay_between_posts)
                
                self.posted_db.mark_posted(pending_id)
                self.posted_db.remove_pending(pending_id)
                
                # Cleanup media
                for p in post_data.get("image_paths", []):
                    try:
                        Path(p).unlink()
                    except:
                        pass
            
        except Exception as e:
            logger.error(f"Scheduled post job failed: {e}")


def main():
    agent = HeroFXAgent()
    
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        logger.info("Agent stopped.")
    except Exception as e:
        logger.error(f"Agent crashed: {e}", exc_info=True)


if __name__ == "__main__":
    main()

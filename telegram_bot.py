"""
Telegram Bot - handles preview, approval, and posting
Uses polling locally, webhook on Railway
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import Config, PostedDB
from ai_analyzer import AIAnalyzer
from instagram_monitor import InstagramMonitor, InstagramPost

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, config: Config, posted_db: PostedDB, ai_analyzer: AIAnalyzer):
        self.config = config
        self.posted_db = posted_db
        self.ai = ai_analyzer
        self.app = None
        self.bot_token = config.get_channel("palawanfx")["bot_token"]
    
    async def start(self):
        """Start the bot."""
        self.app = Application.builder().token(self.bot_token).build()
        
        # Add handlers
        self.app.add_handler(CommandHandler("start", self.handle_start))
        self.app.add_handler(CommandHandler("status", self.handle_status))
        self.app.add_handler(CommandHandler("post", self.handle_post_command))
        self.app.add_handler(CommandHandler("check", self.handle_check_command))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        # Send startup message
        try:
            await self.app.bot.send_message(
                chat_id=self.config.admin_id,
                text="🤖 HeroFX IB Agent is Online!\n\n"
                     "Commands:\n"
                     "/status - Check bot status\n"
                     "/post <instagram_url> - Preview any Instagram post\n"
                     "/check - Manually check HeroFX Instagram\n\n"
                     "The bot will also check automatically every 24 hours."
            )
        except Exception as e:
            logger.error(f"Startup message failed: {e}")
        
        logger.info("Bot is running!")
        
        # Use webhook if WEBHOOK_URL is set, otherwise polling
        webhook_url = os.environ.get("WEBHOOK_URL")
        if webhook_url:
            logger.info(f"Starting with webhook: {webhook_url}")
            # Delete any existing webhook first
            await self.app.bot.delete_webhook()
            # Set webhook
            await self.app.bot.set_webhook(url=webhook_url)
            logger.info("Webhook set successfully")
            # Start webhook server
            await self.app.run_webhook(
                listen="0.0.0.0",
                port=int(os.environ.get("PORT", 8080)),
                webhook_url=webhook_url
            )
        else:
            logger.info("Starting with polling")
            await self.app.run_polling(allowed_updates=Update.ALL_TYPES)
    
    async def send_preview_from_scheduler(self, post_data: Dict[str, Any], media_paths: List[Path]):
        """Send preview from scheduler (no update/context available)."""
        try:
            preview_text = (
                f"📸 New Instagram Post Detected\n"
                f"🔗 {post_data['url']}\n\n"
                f"--- 📝 Kurdish Sorani (PalawanFX) ---\n"
                f"{post_data['preview_ckb'][:800]}\n\n"
                f"--- 📝 Arabic (BatalFX) ---\n"
                f"{post_data['preview_ar'][:800]}\n\n"
                f"⏰ Will be posted at {self.config.posting_time} Slemani time"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve Both", callback_data=f"approve_{post_data['shortcode']}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_{post_data['shortcode']}"),
                ],
                [
                    InlineKeyboardButton("✏️ Edit Kurdish", callback_data=f"edit_ckb_{post_data['shortcode']}"),
                    InlineKeyboardButton("✏️ Edit Arabic", callback_data=f"edit_ar_{post_data['shortcode']}"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if media_paths:
                with open(media_paths[0], "rb") as photo:
                    await self.app.bot.send_photo(
                        chat_id=self.config.admin_id,
                        photo=photo,
                        caption=preview_text[:1024],
                        reply_markup=reply_markup
                    )
        except Exception as e:
            logger.error(f"Failed to send preview from scheduler: {e}")
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if update.effective_user.id != self.config.admin_id:
            await update.message.reply_text("Access denied.")
            return
        
        await update.message.reply_text(
            "🤖 HeroFX IB Agent\n\n"
            "Commands:\n"
            "/status - Check bot status\n"
            "/post <instagram_url> - Preview any Instagram post for approval\n"
            "/check - Manually check HeroFX Instagram\n\n"
            "Auto-check runs every 24 hours.\n"
            "Posts are scheduled for 3:00 PM Slemani time."
        )
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if update.effective_user.id != self.config.admin_id:
            await update.message.reply_text("Access denied.")
            return
        
        text = (
            f"📊 Bot Status\n\n"
            f"Total posted: {len(self.posted_db.data['posted_ids'])}\n"
            f"Pending reviews: {self.posted_db.pending_count}\n"
            f"AI Model: {self.config.ai_model}\n"
            f"Check interval: {self.config.check_interval_hours}h\n"
            f"Posting time: {self.config.posting_time} ({self.config.timezone})"
        )
        await update.message.reply_text(text)
    
    async def handle_post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /post <instagram_url> command - on-demand mode."""
        if update.effective_user.id != self.config.admin_id:
            await update.message.reply_text("Access denied.")
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /post <instagram_url>")
            return
        
        url = context.args[0]
        if "instagram.com" not in url:
            await update.message.reply_text("Please provide a valid Instagram URL.")
            return
        
        status_msg = await update.message.reply_text("🔄 Processing your link...")
        await self._process_instagram_post(url, status_msg, update, context)
    
    async def handle_check_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /check command - manual check."""
        if update.effective_user.id != self.config.admin_id:
            await update.message.reply_text("Access denied.")
            return
        
        await update.message.reply_text("🔍 Checking HeroFX Instagram for new posts...")
        
        monitor = InstagramMonitor(self.config.instagram_username)
        
        last_shortcode = None
        if self.posted_db.data['posted_ids']:
            last_shortcode = self.posted_db.data['posted_ids'][-1]
        
        posts = await monitor.check_new_posts(last_shortcode)
        
        if not posts:
            await update.message.reply_text("No new posts found.")
            return
        
        await update.message.reply_text(f"Found {len(posts)} new post(s). Processing...")
        
        for post in posts:
            await self._process_post(post, update, context)
    
    async def _process_instagram_post(self, url: str, status_msg, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process a single Instagram post from URL."""
        monitor = InstagramMonitor(self.config.instagram_username)
        
        post = await monitor.get_post_by_url(url)
        if not post:
            await status_msg.edit_text("❌ Failed to get post details. Check the URL.")
            return
        
        await status_msg.edit_text(f"📸 Post found! Downloading {len(post.media_urls)} media file(s)...")
        
        media_paths = await monitor.download_media(post)
        if not media_paths:
            await status_msg.edit_text("❌ Failed to download media.")
            return
        
        await status_msg.edit_text("🤖 Analyzing with AI...")
        
        ai_result = self.ai.analyze_post(media_paths, post.caption)
        
        if not ai_result:
            await status_msg.edit_text("❌ AI analysis failed.")
            return
        
        ckb_caption = ai_result['ckb']
        ar_caption = ai_result['ar']
        
        ib_ckb = self.config.get_ib_footer(post.caption, "ckb")
        ib_ar = self.config.get_ib_footer(post.caption, "ar")
        
        preview_ckb = f"{ckb_caption}{ib_ckb}" if ckb_caption else ""
        preview_ar = f"{ar_caption}{ib_ar}" if ar_caption else ""
        
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
        
        await status_msg.delete()
        
        preview_text = (
            f"📸 New Instagram Post Detected\n"
            f"🔗 {post.url}\n\n"
            f"--- 📝 Kurdish Sorani (PalawanFX) ---\n"
            f"{preview_ckb[:800]}\n\n"
            f"--- 📝 Arabic (BatalFX) ---\n"
            f"{preview_ar[:800]}\n\n"
            f"⏰ Will be posted at {self.config.posting_time} Slemani time"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve Both", callback_data=f"approve_{pending_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{pending_id}"),
            ],
            [
                InlineKeyboardButton("✏️ Edit Kurdish", callback_data=f"edit_ckb_{pending_id}"),
                InlineKeyboardButton("✏️ Edit Arabic", callback_data=f"edit_ar_{pending_id}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if media_paths:
            with open(media_paths[0], "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=preview_text[:1024],
                    reply_markup=reply_markup
                )
    
    async def _process_post(self, post: InstagramPost, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process a post from auto-check."""
        monitor = InstagramMonitor(self.config.instagram_username)
        
        media_paths = await monitor.download_media(post)
        if not media_paths:
            logger.error(f"Failed to download media for {post.shortcode}")
            return
        
        ai_result = self.ai.analyze_post(media_paths, post.caption)
        
        if not ai_result:
            logger.error(f"AI analysis failed for {post.shortcode}")
            return
        
        ckb_caption = ai_result['ckb']
        ar_caption = ai_result['ar']
        
        ib_ckb = self.config.get_ib_footer(post.caption, "ckb")
        ib_ar = self.config.get_ib_footer(post.caption, "ar")
        
        preview_ckb = f"{ckb_caption}{ib_ckb}" if ckb_caption else ""
        preview_ar = f"{ar_caption}{ib_ar}" if ar_caption else ""
        
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
        
        preview_text = (
            f"📸 New Instagram Post Detected\n"
            f"🔗 {post.url}\n\n"
            f"--- 📝 Kurdish Sorani (PalawanFX) ---\n"
            f"{preview_ckb[:800]}\n\n"
            f"--- 📝 Arabic (BatalFX) ---\n"
            f"{preview_ar[:800]}\n\n"
            f"⏰ Will be posted at {self.config.posting_time} Slemani time"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve Both", callback_data=f"approve_{pending_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{pending_id}"),
            ],
            [
                InlineKeyboardButton("✏️ Edit Kurdish", callback_data=f"edit_ckb_{pending_id}"),
                InlineKeyboardButton("✏️ Edit Arabic", callback_data=f"edit_ar_{pending_id}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if media_paths:
            with open(media_paths[0], "rb") as photo:
                await context.bot.send_photo(
                    chat_id=self.config.admin_id,
                    photo=photo,
                    caption=preview_text[:1024],
                    reply_markup=reply_markup
                )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        
        if update.effective_user.id != self.config.admin_id:
            await query.answer("Not authorized.", show_alert=True)
            return
        
        data = query.data
        
        if data.startswith("approve_"):
            await self._handle_approve(data.replace("approve_", ""), query, context)
        elif data.startswith("reject_"):
            await self._handle_reject(data.replace("reject_", ""), query, context)
        elif data.startswith("edit_ckb_"):
            await self._handle_edit_start(data.replace("edit_ckb_", ""), "ckb", query, context)
        elif data.startswith("edit_ar_"):
            await self._handle_edit_start(data.replace("edit_ar_", ""), "ar", query, context)
    
    async def _handle_approve(self, pending_id: str, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle approve button."""
        post_data = self.posted_db.get_pending(pending_id)
        if not post_data:
            await query.answer("Post expired.", show_alert=True)
            return
        
        # Determine if this was auto-detected or manual
        is_auto_detected = post_data.get("detected_at") is not None
        
        if is_auto_detected:
            await query.answer("Scheduled for 3:00 PM posting...")
            await query.message.reply_text("⏰ Post approved! It will be posted at 3:00 PM Slemani time.")
            # Keep in pending - the 3:00 PM scheduler will pick it up
            await query.edit_message_reply_markup(reply_markup=None)
        else:
            await query.answer("Posting immediately...")
            # Post immediately
            await self._post_pending(pending_id, query, context)
    
    async def _post_pending(self, pending_id: str, query, context: ContextTypes.DEFAULT_TYPE):
        """Post a pending post to both channels."""
        post_data = self.posted_db.get_pending(pending_id)
        if not post_data:
            return
        
        for channel_key in ["palawanfx", "batalfx"]:
            channel_config = self.config.get_channel(channel_key)
            target_lang = channel_config["language"]
            caption = post_data["preview_ckb"] if target_lang == "ckb" else post_data["preview_ar"]
            
            if not caption:
                caption = post_data["original_caption"] or ""
            
            media_paths = [Path(p) for p in post_data["image_paths"] if Path(p).exists()]
            
            success = await self._post_to_telegram(
                channel_config["bot_token"],
                channel_config["channel_id"],
                caption,
                media_paths
            )
            
            if success:
                logger.info(f"Posted to {channel_key}")
            else:
                logger.error(f"Failed to post to {channel_key}")
            
            await asyncio.sleep(self.config.delay_between_posts)
        
        self.posted_db.mark_posted(pending_id)
        self.posted_db.remove_pending(pending_id)
        
        for p in post_data.get("image_paths", []):
            try:
                Path(p).unlink()
            except:
                pass
        
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Posted to both channels!")
    
    async def _handle_reject(self, pending_id: str, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle reject button."""
        post_data = self.posted_db.get_pending(pending_id)
        if post_data:
            for p in post_data.get("image_paths", []):
                try:
                    Path(p).unlink()
                except:
                    pass
            self.posted_db.remove_pending(pending_id)
        
        await query.answer("Rejected.", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
    
    async def _handle_edit_start(self, pending_id: str, lang: str, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle edit button - ask user to send new text."""
        post_data = self.posted_db.get_pending(pending_id)
        if not post_data:
            await query.answer("Post expired.", show_alert=True)
            return
        
        await query.answer()
        await query.message.reply_text(f"Send the new {lang.upper()} text:")
        context.user_data["editing"] = {"pending_id": pending_id, "lang": lang}
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (for editing)."""
        if update.effective_user.id != self.config.admin_id:
            return
        
        if "editing" not in context.user_data:
            return
        
        editing = context.user_data.pop("editing")
        pending_id = editing["pending_id"]
        lang = editing["lang"]
        
        post_data = self.posted_db.get_pending(pending_id)
        if not post_data:
            await update.message.reply_text("Post expired.")
            return
        
        new_text = update.message.text
        
        ib_footer = self.config.get_ib_footer(post_data["original_caption"], lang)
        if lang == "ckb":
            post_data["translated_ckb"] = new_text
            post_data["preview_ckb"] = f"{new_text}{ib_footer}"
        else:
            post_data["translated_ar"] = new_text
            post_data["preview_ar"] = f"{new_text}{ib_footer}"
        
        self.posted_db.add_pending(pending_id, post_data)
        
        preview_text = (
            f"📸 Updated Preview\n\n"
            f"--- 📝 Kurdish Sorani (PalawanFX) ---\n"
            f"{post_data['preview_ckb'][:800]}\n\n"
            f"--- 📝 Arabic (BatalFX) ---\n"
            f"{post_data['preview_ar'][:800]}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve Both", callback_data=f"approve_{pending_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{pending_id}"),
            ],
            [
                InlineKeyboardButton("✏️ Edit Kurdish", callback_data=f"edit_ckb_{pending_id}"),
                InlineKeyboardButton("✏️ Edit Arabic", callback_data=f"edit_ar_{pending_id}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(preview_text[:4096], reply_markup=reply_markup)
    
    async def _post_to_telegram(self, bot_token: str, channel_id: str, caption: str, media_paths: List[Path]) -> bool:
        """Post to a Telegram channel."""
        try:
            bot = Bot(token=bot_token)
            
            if media_paths:
                if len(media_paths) == 1:
                    with open(media_paths[0], "rb") as f:
                        if media_paths[0].suffix == ".mp4":
                            await bot.send_video(chat_id=channel_id, video=f, caption=caption[:1024])
                        else:
                            await bot.send_photo(chat_id=channel_id, photo=f, caption=caption[:1024])
                else:
                    media_group = []
                    for i, mp in enumerate(media_paths[:10]):
                        with open(mp, "rb") as f:
                            data = f.read()
                        if i == 0:
                            if mp.suffix == ".mp4":
                                media_group.append(InputMediaVideo(media=data, caption=caption[:1024]))
                            else:
                                media_group.append(InputMediaPhoto(media=data, caption=caption[:1024]))
                        else:
                            if mp.suffix == ".mp4":
                                media_group.append(InputMediaVideo(media=data))
                            else:
                                media_group.append(InputMediaPhoto(media=data))
                    
                    if media_group:
                        await bot.send_media_group(chat_id=channel_id, media=media_group)
            else:
                await bot.send_message(chat_id=channel_id, text=caption[:4096])
            
            return True
        except Exception as e:
            logger.error(f"Failed to post to {channel_id}: {e}")
            return False
